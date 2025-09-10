from pathlib import Path
from typing import Optional

import qt
import slicer
from CARTLib.core.TaskBaseClass import TaskBaseClass, DataUnitFactory, D
from CARTLib.examples.RapidAnnotation.RapidAnnotationUnit import RapidAnnotationUnit
from CARTLib.utils.config import ProfileConfig
from CARTLib.utils.task import cart_task


class RapidAnnotationGUI:

    COMPLETED_BRUSH = qt.QBrush(
        qt.QColor(0, 255, 0, 100)
    )

    def __init__(self, bound_task: "RapidAnnotationTask"):
        self.bound_task = bound_task
        self.data_unit: Optional[RapidAnnotationUnit] = None

        # Widget displaying the data unit
        self.annotationList = None

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
        self.startPlacements()

    def _syncAnnotationList(self):
        for i in range(self.annotationList.count):
            listItem = self.annotationList.item(i)
            label = listItem.text()
            if self.bound_task.annotation_complete_map.get(label, False):
                listItem.setBackground(self.COMPLETED_BRUSH)

    def startPlacements(self):
        # Ensure the data unit's annotation node the selected one
        selectionNode = slicer.app.applicationLogic().GetSelectionNode()
        selectionNode.SetActivePlaceNodeID(self.data_unit.annotation_node.GetID())

        # Iterate through our annotation list and start placing nodes in order
        for i in range(self.annotationList.count):
            listItem = self.annotationList.item(i)
            label = listItem.text()
            if not self.bound_task.annotation_complete_map.get(label, False):
                # TODO
                print(f"Label '{label}' still needs to be placed!")

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

    # noinspection PyAttributeOutsideInit
    def _build_ui(self):
        """
        Build the GUI elements into this prompt
        """
        # Create the layout to actually place everything in
        layout = qt.QFormLayout(self)

        # Create a list widget w/ drag and drop capabilities
        annotationList = qt.QListWidget()
        annotationListLabel = qt.QLabel("Registered Annotations")

        # Add it to the layout and track it for later
        layout.addRow(annotationListLabel)
        layout.addRow(annotationList)
        self.annotationList = annotationList

        # Add a button to add items to the list
        addButton = qt.QPushButton("Add")
        addButton.clicked.connect(self.add_new_annotation)

        # Add it to the layout
        layout.addRow(addButton)

        # Add a confirm button
        confirmButton = qt.QPushButton("Confirm")
        confirmButton.clicked.connect(lambda _: self.accept())

        # Add it to the layout
        layout.addRow(confirmButton)

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
        self.output_dir: Optional[Path] = None
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

        self.tracked_annotations = prompt.get_annotations()

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
            fiducial_label = data_unit.annotation_node.GetNthFiducialLabel(i)
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