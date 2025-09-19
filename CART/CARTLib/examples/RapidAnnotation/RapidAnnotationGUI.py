from pathlib import Path
from typing import Optional

import ctk
import qt
import slicer
from slicer.i18n import tr as _

from RapidAnnotationUnit import RapidAnnotationUnit


# Type hint guard; only risk the cyclic import if type hints are running
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    # noinspection PyUnusedImports
    from RapidAnnotationTask import RapidAnnotationTask


## WIDGETS ##
class MarkupListWidget(qt.QWidget):
    def __init__(self, task: "RapidAnnotationTask"):
        super().__init__()

        # Create the layout to hold everything in
        layout = qt.QVBoxLayout()
        self.setLayout(layout)

        self._addMarkupList(layout)

        self._addButtonPanel(layout)

        # Synchronize ourselves with the loaded task
        self._loadStateFromTask(task)

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

    ## Signal Functions ##
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

    def remove_selected_markups(self):
        for item in self.markupList.selectedItems():
            # Why "removeItemWidget" doesn't do this, only god knows
            self.markupList.takeItem(self.markupList.row(item))

    def _loadStateFromTask(self, task: "RapidAnnotationTask"):
        # Re-assess the markup list state based on the logic
        self.markupList.clear()
        self.markupList.addItems(task.tracked_annotations)

        # Disable the remove button, as there is no longer any selection
        self.removeButton.setEnabled(False)

    def get_markups(self):
        # Need to do this, as the signature for `items` is too ambiguous
        annotations = []
        for i in range(self.markupList.count):
            item = self.markupList.item(i)
            annotations.append(item.text())
        return annotations


## PROMPTS ##
class RapidAnnotationSetupPrompt(qt.QDialog):
    def __init__(self, bound_logic: "RapidAnnotationTask"):
        super().__init__()

        self.setWindowTitle("Set Up Annotations")

        self.bound_logic = bound_logic

        self._build_ui()

    def _build_ui(self):
        """
        Build the GUI elements into this prompt
        """
        # Create the layout to actually place everything in
        layout = qt.QFormLayout(self)

        # Initialize a copy of the Markup list to the config
        self.markupWidget = MarkupListWidget(self.bound_logic)
        layout.addWidget(self.markupWidget)

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

        # Add a dropdown to select the output format
        formatLabel = qt.QLabel("Format: ")
        formatBox = qt.QComboBox()

        # TODO; fill this from an enum instead
        formatBox.addItems(["json", "csv"])

        # Update the layout and track it for later
        layout.addRow(formatLabel, formatBox)
        self.formatBox = formatBox

    def _buildButtons(self, layout: qt.QFormLayout):
        # Button box for confirming/rejecting the current use
        buttonBox = qt.QDialogButtonBox()
        buttonBox.addButton(_("Confirm"), qt.QDialogButtonBox.AcceptRole)
        buttonBox.addButton(_("Cancel"), qt.QDialogButtonBox.RejectRole)
        layout.addRow(buttonBox)

        # Connect signals
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)

    def get_annotations(self) -> list[str]:
        # For some reason, `items()` doesn't work
        return self.markupWidget.get_markups()

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
class RapidAnnotationGUI:

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
        qt.QColor(0, 0, 0, 255)
    )

    def __init__(self, bound_task: "RapidAnnotationTask"):
        self.bound_task = bound_task
        self.data_unit: Optional[RapidAnnotationUnit] = None

        # Widget displaying the data unit
        self.annotationList = None

        # Observer IDs; need to be tracked here to avoid cyclic referencing
        self.anot_observer_id: Optional[str] = None
        self.backout_observer_id: Optional[str] = None

    def setup(self) -> qt.QFormLayout:
        # Initialize a layout we'll insert everything into
        formLayout = qt.QFormLayout()

        self._initAnnotationList(formLayout)

        return formLayout

    def _initAnnotationList(self, formLayout: qt.QFormLayout):
        # Create a list widget w/ drag and drop capabilities
        annotationList = qt.QListWidget()
        annotationListLabel = qt.QLabel("Registered Annotations")

        # Insert all attributes tracked by the logic into the annotation list
        annotationList.addItems(self.bound_task.tracked_annotations)

        # Add it to the layout and track it for later
        formLayout.addRow(annotationListLabel)
        formLayout.addRow(annotationList)
        self.annotationList = annotationList

    def update(self, data_unit: RapidAnnotationUnit):
        # Track the new data unit
        self.data_unit = data_unit

        # Update the layout to use its contents
        self.data_unit.layout_handler.apply_layout()

        # Synchronize with our logic's state
        self._syncAnnotationList()

        # Start node placement
        # TODO: make this automated start configurable
        self.initAnnotationPlacement()

    def _syncAnnotationList(self):
        for i in range(self.annotationList.count):
            listItem = self.annotationList.item(i)
            label = listItem.text()
            if self.bound_task.annotation_complete_map.get(label, False):
                listItem.setBackground(self.COMPLETED_BRUSH)
            else:
                listItem.setBackground(self.BLANK_BRUSH)

    def initAnnotationPlacement(self):
        # Ensure the data unit's annotation node the selected one
        selectionNode = slicer.app.applicationLogic().GetSelectionNode()
        selectionNode.SetActivePlaceNodeID(self.data_unit.annotation_node.GetID())

        # Start by getting the user to place the first node
        self._userPlacePoint()

    # TODO: Rewrite this, this is cursed beyond belief
    def _userPlacePoint(self, prior_idx: int = -1):
        # Remove the previous observer callbacks
        anot_node = self.bound_task.data_unit.annotation_node
        if self.anot_observer_id:
            anot_node.RemoveObserver(self.anot_observer_id)

        interactionNode = slicer.app.applicationLogic().GetInteractionNode()
        if self.backout_observer_id:
            interactionNode.RemoveObserver(self.backout_observer_id)

        # Move the starting point up 1
        start_index = prior_idx + 1

        # Find the next valid index in the remaining range
        for i in range(start_index, self.annotationList.count):
            anot_item = self.annotationList.item(i)
            anot_label = anot_item.text()
            # If this annotation isn't completed, get the user to try and place it
            if not self.bound_task.annotation_complete_map.get(anot_label, False):
                # Enter placement mode for the user
                interactionNode.SetCurrentInteractionMode(interactionNode.Place)
                interactionNode.SetPlaceModePersistence(True)

                # Highlight the corresponding entry in our list
                anot_item.setBackground(self.HIGHLIGHTED_BRUSH)

                # Register a callback for when a new point is placed!
                def _onAnotAdded(caller, _):
                    # Change the name of the newly added node to its proper name
                    newest_point_idx = caller.GetNumberOfControlPoints() - 1
                    caller.SetNthControlPointLabel(newest_point_idx, anot_label)

                    # Mark this annotation as complete
                    anot_item.setBackground(self.COMPLETED_BRUSH)
                    self.bound_task.annotation_complete_map[anot_label] = True

                    # Try to prompt the user for the next node
                    self._userPlacePoint(i)

                self.anot_observer_id = anot_node.AddObserver(
                    anot_node.PointPositionDefinedEvent, _onAnotAdded
                )

                # Register a callback for when the user exits placement mode (indicating they backed out)
                def _onBackOut(_, __):
                    # Highlight the entry in "skipped" colors
                    anot_item.setBackground(self.SKIPPED_BRUSH)

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
