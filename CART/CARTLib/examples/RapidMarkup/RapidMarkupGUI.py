from contextlib import contextmanager
from pathlib import Path
from typing import Optional

import ctk
import qt
import slicer
from slicer.i18n import tr as _

from RapidMarkupUnit import RapidMarkupUnit


# Type hint guard; only risk the cyclic import if type hints are running
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    # noinspection PyUnusedImports
    from RapidMarkupTask import RapidMarkupTask


## WIDGETS ##
class MarkupListWidget(qt.QWidget):

    COMPLETED_BRUSH = qt.QBrush(
        qt.QColor(0, 255, 0, 100)
    )
    HIGHLIGHTED_BRUSH = qt.QBrush(
        qt.QColor(0, 0, 255, 100)
    )
    SKIPPED_BRUSH = qt.QBrush(
        qt.QColor(255, 0, 0, 100)
    )
    BLANK_BRUSH = qt.QBrush(
        qt.QColor(0, 0, 0, 0)
    )

    def __init__(self, task: "RapidMarkupTask"):
        super().__init__()

        # Create the layout to hold everything in
        layout = qt.QVBoxLayout()
        self.setLayout(layout)

        self._addMarkupList(layout)

        self._addButtonPanel(layout)

        # Synchronize ourselves with the loaded task
        self.syncStateWithTask(task)

        # Track it for later
        self.bound_task = task

    ## GUI Construction ##
    def _addMarkupList(self, layout):
        # Create a list widget
        markupList = qt.QListWidget()
        markupListLabel = qt.QLabel("Markup Labels")

        # When the selected item changes, update our state to match
        markupList.itemSelectionChanged.connect(
            self._onSelectionChanged
        )

        # Track it for later and add it to the layout
        layout.addWidget(markupListLabel)
        layout.addWidget(markupList)
        self.markupList = markupList

    def _addButtonPanel(self, layout):
        # Add a button to add items to the list
        addButton = qt.QPushButton("Add")
        addButton.clicked.connect(self._addNewMarkup)

        # Add a button to remove items from the list
        removeButton = qt.QPushButton("Remove")
        removeButton.clicked.connect(self.remove_selected_markups)

        # Make them side-by-side and add them to the layout
        buttonLayout = qt.QHBoxLayout()
        buttonLayout.addWidget(addButton)
        buttonLayout.addWidget(removeButton)
        layout.addLayout(buttonLayout)

        # Track them for later
        self.addButton = addButton
        self.removeButton = removeButton

    ## Properties ##
    @property
    def count(self) -> int:
        # Alias for the underlying list widget's count
        return self.markupList.count

    @property
    def rowsInserted(self):
        # Alias to easily expose the function for connections
        return self.markupList.model().rowsInserted

    @property
    def rowsRemoved(self):
        # Alias to easily expose the function for connections
        return self.markupList.model().rowsRemoved

    ## Signal Functions ##
    def _onSelectionChanged(self):
        # Make it so we can only remove items when there are items
        #  selected to be removed
        self.removeButton.setEnabled(
            len(self.markupList.selectedItems()) > 0
        )

    def _addNewMarkup(self):
        # Start the Add Markup dialog
        dialog = AddMarkupDialog()

        # Exec it to show it to the user
        dialog_return = dialog.exec()

        # If the user closed the dialog, just end as-is
        if not dialog_return:
            return

        # Otherwise, get the text from the markup
        new_markup_str = dialog.getMarkup().strip()
        # If the markup string exists, add it to the list
        if new_markup_str:
            newItem = qt.QListWidgetItem(new_markup_str)
            self.markupList.addItem(newItem)
        # Otherwise, notify the user it was blank and not added
        else:
            slicer.util.warningDisplay(_(
                "Label was blank, no markup was added."
            ))

    ## Utils ##
    def remove_selected_markups(self):
        for item in self.markupList.selectedItems():
            # Why "removeItemWidget" doesn't do this, only god knows
            self.markupList.takeItem(self.markupList.row(item))

    def itemAt(self, idx: int) -> qt.QListWidgetItem:
        return self.markupList.item(idx)

    @contextmanager
    def noUpdateSignals(self):
        self.markupList.blockSignals(True)
        self.markupList.model().blockSignals(True)

        yield

        self.markupList.blockSignals(False)
        self.markupList.model().blockSignals(False)

    def syncStateWithTask(self, task: "RapidMarkupTask"):
        # Re-assess the markup list state based on the logic
        with self.noUpdateSignals():
            self.markupList.clear()

            for i, label in enumerate(task.markup_labels):
                listItem = qt.QListWidgetItem(label)
                markup_completed = task.markup_placed[i]
                if markup_completed:
                    listItem.setBackground(self.COMPLETED_BRUSH)
                elif markup_completed is False:
                    listItem.setBackground(self.SKIPPED_BRUSH)
                else:
                    listItem.setBackground(self.BLANK_BRUSH)
                self.markupList.addItem(listItem)

        # Disable the remove button, as there is no longer any selection
        self.removeButton.setEnabled(False)


## PROMPTS ##
class RapidMarkupSetupPrompt(qt.QDialog):
    def __init__(self, bound_logic: "RapidMarkupTask"):
        super().__init__()

        self.setWindowTitle("Set Up Rapid Markup")

        self.bound_logic = bound_logic

        self._build_ui()

    def _build_ui(self):
        """
        Build the GUI elements into this prompt
        """
        # Create the layout to actually place everything in
        layout = qt.QFormLayout(self)

        self._buildOutputGUI(layout)

        self._buildButtons(layout)

    def _buildOutputGUI(self, layout: qt.QFormLayout):
        # Add a label clarifying the next widget's purpose
        description = qt.QLabel("Output Directory:")
        layout.addRow(description)

        # Ensure only directories are chosen
        outputFileEdit = ctk.ctkPathLineEdit()
        outputFileEdit.setToolTip(
            _("The directory where the saved markups will be placed.")
        )
        outputFileEdit.filters = ctk.ctkPathLineEdit.Dirs

        # Set its state to match the task's if it has one
        if self.bound_logic._output_dir:
            self.outputFileEdit.currentPath = str(self.bound_logic._output_dir)

        # Update the layout and track it for later
        layout.addRow(outputFileEdit)
        self.outputFileEdit = outputFileEdit

    def _buildButtons(self, layout: qt.QFormLayout):
        # Button box for confirming/rejecting the current use
        buttonBox = qt.QDialogButtonBox()
        buttonBox.addButton(_("Confirm"), qt.QDialogButtonBox.AcceptRole)
        buttonBox.addButton(_("Cancel"), qt.QDialogButtonBox.RejectRole)
        layout.addRow(buttonBox)

        # Connect signals
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)

    # Output management
    def get_output(self):
        new_path = self.outputFileEdit.currentPath
        if new_path is "":
            return None
        new_path = Path(new_path)
        if not new_path.exists():
            return None
        if not new_path.is_dir():
            return None
        return new_path


class AddMarkupDialog(qt.QDialog):
    def __init__(self):
        # Initialize the prompt itself
        super().__init__()

        # Update our basic attributes
        self.setWindowTitle(_("New Markup Label"))

        # Initialize our layout
        layout = qt.QFormLayout(self)

        # Set up our own GUI
        self._buildUI(layout)

    def _buildUI(self, layout: qt.QFormLayout):
        # Line edit + its label
        lineEditLabel = qt.QLabel(_("Markup Label"))
        lineEdit = qt.QLineEdit()

        # Add it to our layout
        layout.addRow(lineEditLabel, lineEdit)

        # Track the line edit for later
        self.lineEdit = lineEdit

        # Add a button box to confirm and cancel
        buttonBox = qt.QDialogButtonBox()
        buttonBox.setStandardButtons(
            qt.QDialogButtonBox.Cancel | qt.QDialogButtonBox.Ok
        )

        # Function to map button presses to corresponding actions
        def onButtonPressed(button: qt.QPushButton):
            button_role = buttonBox.buttonRole(button)
            if button_role == qt.QDialogButtonBox.RejectRole:
                self.reject()
            elif button_role == qt.QDialogButtonBox.AcceptRole:
                self.accept()
            else:
                raise ValueError("Pressed a button with an invalid role!")
        buttonBox.clicked.connect(onButtonPressed)

        # Add it to the layout
        layout.addRow(buttonBox)

    def getMarkup(self) -> str:
        return self.lineEdit.text

## GUIs ##
class RapidMarkupGUI:
    def __init__(self, bound_task: "RapidMarkupTask"):
        self.bound_task = bound_task
        self.data_unit: Optional[RapidMarkupUnit] = None

        # Widget displaying the data unit
        self.markupList: MarkupListWidget = None

        # Observer IDs; need to be tracked here to avoid cyclic referencing
        self.markup_observer_id: Optional[str] = None
        self.backout_observer_id: Optional[str] = None

    def setup(self) -> qt.QFormLayout:
        # Initialize a layout we'll insert everything into
        formLayout = qt.QFormLayout()

        self._initMarkupList(formLayout)

        return formLayout

    def _initMarkupList(self, formLayout: qt.QFormLayout):
        # Create a markup list
        markupList = MarkupListWidget(self.bound_task)

        # Connect the row addition/removal signals to sync functions
        markupList.rowsInserted.connect(self.onMarkupAdded)
        markupList.rowsRemoved.connect(self.onMarkupRemoved)

        # Add it to the layout and track it for later
        formLayout.addWidget(markupList)
        self.markupList = markupList

    def update(self, data_unit: RapidMarkupUnit):
        # Track the new data unit
        self.data_unit = data_unit

        # Update the layout to use its contents
        self.data_unit.layout_handler.apply_layout()

        # Synchronize with our logic's state
        self.markupList.syncStateWithTask(self.bound_task)

        # Start node placement
        # TODO: make this automated start configurable
        self.initMarkupPlacement()

    def onMarkupAdded(self, _, start_idx, end_idx):
        # Add the new elements to our logic as well
        for i in range(start_idx, end_idx+1):
            item = self.markupList.itemAt(i)
            label = item.text()
            self.bound_task.add_markup_at(i, label)

    def onMarkupRemoved(self, _, start_idx, end_idx):
        # Remove the dropped elements from our logic as well
        for i in range(start_idx, end_idx+1):
            self.bound_task.remove_markup_at(i)

    def initMarkupPlacement(self):
        # Ensure the data unit's markup node is the selected one
        selectionNode = slicer.app.applicationLogic().GetSelectionNode()
        selectionNode.SetActivePlaceNodeID(self.data_unit.markup_node.GetID())

        # Start by getting the user to place the first node
        self._userPlacePoint()

    # TODO: Rewrite this, this is cursed beyond belief
    def _userPlacePoint(self, prior_idx: int = -1):
        # Remove the previous observer callbacks
        markup_node = self.bound_task.data_unit.markup_node
        if self.markup_observer_id:
            markup_node.RemoveObserver(self.markup_observer_id)

        interactionNode = slicer.app.applicationLogic().GetInteractionNode()
        if self.backout_observer_id:
            interactionNode.RemoveObserver(self.backout_observer_id)

        # Move the starting point up 1
        start_index = prior_idx + 1

        # Find the next valid index in the remaining range
        for i in range(start_index, self.markupList.count):
            markup_item = self.markupList.itemAt(i)
            markup_label = markup_item.text()
            # If this markup hasn't been placed, get the user to try and place it
            is_placed = self.bound_task.markup_placed[i]
            if not is_placed:
                # Enter placement mode for the user
                interactionNode.SetCurrentInteractionMode(interactionNode.Place)
                interactionNode.SetPlaceModePersistence(True)

                # Highlight the corresponding entry in our list
                markup_item.setBackground(self.markupList.HIGHLIGHTED_BRUSH)

                # Register a callback for when a new point is placed!
                def _onMarkupAdded(caller, _):
                    # Change the name of the newly added node to its proper name
                    newest_point_idx = caller.GetNumberOfControlPoints() - 1
                    caller.SetNthControlPointLabel(newest_point_idx, markup_label)

                    # Mark this markup as being placed visually
                    markup_item.setBackground(self.markupList.COMPLETED_BRUSH)

                    self.bound_task.markup_placed[i] = True

                    # Try to prompt the user for the next node
                    self._userPlacePoint(i)

                self.markup_observer_id = markup_node.AddObserver(
                    markup_node.PointPositionDefinedEvent, _onMarkupAdded
                )

                # Register a callback for when the user exits placement mode (indicating they backed out)
                def _onBackOut(_, __):
                    # Highlight the entry in "skipped" colors
                    markup_item.setBackground(self.markupList.SKIPPED_BRUSH)

                    # Proceed to the next point
                    self._userPlacePoint(i)

                self.backout_observer_id = interactionNode.AddObserver(
                    interactionNode.InteractionModeChangedEvent, _onBackOut
                )

                # Terminate
                break
        else:
            # If the loop ran to completion, exit persistent mode
            interactionNode.SetPlaceModePersistence(False)

    ## GUI SYNCHRONIZATION ##
    def enter(self) -> None:
        pass

    def exit(self) -> None:
        pass
