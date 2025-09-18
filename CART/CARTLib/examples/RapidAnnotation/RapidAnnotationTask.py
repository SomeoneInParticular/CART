from pathlib import Path
from typing import Optional

import ctk
import qt
import slicer
from CARTLib.core.TaskBaseClass import TaskBaseClass, DataUnitFactory
from CARTLib.utils.config import ProfileConfig
from CARTLib.utils.task import cart_task
from slicer.i18n import tr as _

from RapidAnnotationConfig import RapidAnnotationConfig
from RapidAnnotationGUI import RapidAnnotationGUI
from RapidAnnotationOutputManager import RapidAnnotationOutputManager
from RapidAnnotationUnit import RapidAnnotationUnit


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
        self._output_manager: Optional[RapidAnnotationOutputManager] = None

        # Config management
        self.config = RapidAnnotationConfig(parent_config=self.profile)

    def setup(self, container: qt.QWidget) -> None:
        print(f"Running {self.__class__.__name__} setup!")

        if self.config.last_used_output and self.config.last_used_markups:
            if slicer.util.confirmYesNoDisplay(
                "A previous run of this task was found; would you like to load it?"
            ):
                self.tracked_annotations = self.config.last_used_markups
                self.output_dir = self.config.last_used_output

        if self.tracked_annotations is None or self.output_dir is None:
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

        if self.output_dir is None:
            raise ValueError("Cannot initialize task without an output directory!")

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

        # Build the output manager
        self._output_manager = None

        # Update our config with this annotation set and save it
        self.config.last_used_markups = self.tracked_annotations
        self.config.last_used_output = self.output_dir
        self.config.save()


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
            self._output_manager = None
            return
        # Otherwise, update the user so that they may respond appropriately
        self.on_bad_output()

    @property
    def output_manager(self):
        # If the output manager hasn't been generated yet or was reset,
        # and we have an output directory, create a new one
        if not self._output_manager:
            self._output_manager = RapidAnnotationOutputManager(
                self.profile,
                self.output_dir
            )

        return self._output_manager

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
        if not self.data_unit:
            raise ValueError("Cannot save, nothing to save!")
        self.output_manager.save_markups(self.data_unit)

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
