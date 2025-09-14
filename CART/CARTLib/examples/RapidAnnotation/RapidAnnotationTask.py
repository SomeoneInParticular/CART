from pathlib import Path
from typing import Optional

import ctk
import qt
import slicer
from CARTLib.core.TaskBaseClass import TaskBaseClass, DataUnitFactory
from CARTLib.examples.RapidAnnotation.RapidAnnotationUnit import RapidAnnotationUnit
from CARTLib.utils.config import ProfileConfig
from CARTLib.utils.task import cart_task
from slicer.i18n import tr as _


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

        # Create a list widget w/ drag and drop capabilities
        annotationList = qt.QListWidget()
        annotationListLabel = qt.QLabel("Registered Annotations")

        # Insert all attributes tracked by the logic into the annotation list
        annotationList.addItems(self.bound_task.tracked_annotations)

        # Add it to the layout and track it for later
        formLayout.addRow(annotationListLabel)
        formLayout.addRow(annotationList)
        self.annotationList = annotationList

        return formLayout

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

        self._buildAnnotationGUI(layout)

        self._buildOutputGUI(layout)

        self._buildButtons(layout)

    def _buildAnnotationGUI(self, layout: qt.QFormLayout):
        # Create a list widget w/ drag and drop capabilities
        annotationList = qt.QListWidget()
        annotationListLabel = qt.QLabel("Registered Annotations")

        # Add a button to add items to the list
        addButton = qt.QPushButton("Add")
        addButton.clicked.connect(self.add_new_annotation)

        # Add it to the layout and track it for later
        layout.addRow(annotationListLabel, addButton)
        layout.addRow(annotationList)
        self.annotationList = annotationList

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

    # Annotation management
    def add_new_annotation(self):
        # Add a blank item
        newItem = qt.QListWidgetItem("")
        # Make it editable
        newItem.setFlags(
            newItem.flags() | qt.Qt.ItemIsEditable
        )
        # Add it to the list
        self.annotationList.addItem(newItem)
        # Set it as the current active item
        self.annotationList.setCurrentItem(newItem)
        # Immediately start editing it
        self.annotationList.editItem(newItem)

    def get_annotations(self) -> list[str]:
        # For some reason, `items()` doesn't work
        annotations = []
        for i in range(self.annotationList.count):
            item = self.annotationList.item(i)
            annotations.append(item.text())
        return annotations

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

@cart_task("Rapid Annotation")
class RapidAnnotationTask(TaskBaseClass[RapidAnnotationUnit]):
    def __init__(self, profile: ProfileConfig):
        super().__init__(profile)

        # GUI and data
        self.gui: Optional[RapidAnnotationGUI] = None
        self.data_unit: Optional[RapidAnnotationUnit] = None

        # Annotation tracking
        self.tracked_annotations: list[str] = []
        self.annotation_complete_map: dict[str, bool] = {}

        # Output management
        self._output_dir: Optional[Path] = None
        self.csv_log_path: Optional[Path] = None

    def setup(self, container: qt.QWidget) -> None:
        print(f"Running {self.__class__.__name__} setup!")

        # Prompt the user with the setup GUI
        prompt = RapidAnnotationSetupPrompt(self)
        setup_successful = prompt.exec()

        # If the setup failed, error out to prevent further task init
        if not setup_successful:
            raise AssertionError(
                f"Failed to set up for {self.__class__.__name__}")

        # Pull the relevant information out of the setup prompt
        self.tracked_annotations = prompt.get_annotations()
        self.output_dir = prompt.get_output()

        # Initialize our GUI
        self.gui = RapidAnnotationGUI(self)
        layout = self.gui.setup()

        # Insert it into CART's GUI
        container.setLayout(layout)

        # If we have a data unit at this point, synchronize the GUI to it
        if self.data_unit:
            self.gui.update(self.data_unit)

        # Enter the GUI
        self.gui.enter()

    @property
    def output_dir(self) -> Path:
        return self._output_dir

    @output_dir.setter
    def output_dir(self, new_path: Path):
        """
        Made this a property to ensure that it isn't overridden by an
        invalid directory; also notifies the user that this occurred
        (via GUI prompt if available) so that they can respond
        appropriately
        """
        # If the path exists and is valid, set it and end
        if new_path and new_path.exists() and new_path.is_dir():
            self._output_dir = new_path
            return
        # Otherwise, update the user so that they may respond appropriately
        self.on_bad_output()

    def on_bad_output(self):
        # Determine which error message to show
        if not self.output_dir:
            msg = _("No valid output provided! Will not be able to save your results!")
        else:
            msg = _("No output provided, falling back to previous output directory.")
        # Log it to the console for later reference
        print(msg)
        # If we have a GUI, prompt the user as well
        if self.gui:
            prompt = qt.QErrorMessage()
            prompt.setWindowTitle("Bad Output!")
            prompt.showMessage(msg)
            prompt.exec()

    def receive(self, data_unit: RapidAnnotationUnit):
        # Track the data unit for later
        self.data_unit = data_unit

        # Display the data unit's contents
        slicer.util.setSliceViewerLayers(
            background=self.data_unit.primary_volume_node,
            fit=True
        )

        # Re-build our set of to-be-placed of fiducials
        self.annotation_complete_map.clear()
        self.annotation_complete_map = {k: False for k in self.tracked_annotations}
        # Mark those the data unit already has as already being annotated
        for i in range(data_unit.annotation_node.GetNumberOfControlPoints()):
            fiducial_label = data_unit.annotation_node.GetNthControlPointLabel(i)
            if fiducial_label in self.annotation_complete_map.keys():
                self.annotation_complete_map[fiducial_label] = True

        # If we have a GUI, update it as well
        if self.gui:
            self.gui.update(data_unit)

    def save(self) -> Optional[str]:
        # TODO
        pass

    def enter(self):
        if self.gui:
            self.gui.enter()

    def exit(self):
        if self.gui:
            self.gui.exit()

    @classmethod
    def getDataUnitFactories(cls) -> dict[str, DataUnitFactory]:
        return {
            "Default": RapidAnnotationUnit
        }
