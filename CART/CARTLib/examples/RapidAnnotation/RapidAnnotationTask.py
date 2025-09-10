from pathlib import Path
from typing import Optional

import qt
import slicer
from CARTLib.core.TaskBaseClass import TaskBaseClass, DataUnitFactory, D
from CARTLib.examples.RapidAnnotation.RapidAnnotationUnit import RapidAnnotationUnit
from CARTLib.utils.config import ProfileConfig
from CARTLib.utils.task import cart_task


class RapidAnnotationGUI:
    def __init__(self, bound_task: "RapidAnnotationTask"):
        self.bound_task = bound_task
        self.data_unit: Optional[RapidAnnotationUnit] = None

    def setup(self) -> qt.QFormLayout:
        # Initialize a layout we'll insert everything into
        formLayout = qt.QFormLayout()

        # Create a list widget w/ drag and drop capabilities
        annotationList = qt.QListWidget()
        annotationListLabel = qt.QLabel("Registered Annotations")

        # Add it to the layout and track it for later
        formLayout.addRow(annotationListLabel)
        formLayout.addRow(annotationList)

        # Insert all attributes tracked by the logic to the list
        annotationList.addItems(self.bound_task.tracked_annotations)

        return formLayout

    def update(self, data_unit: RapidAnnotationUnit):
        self.data_unit = data_unit
        self.data_unit.layout_handler.apply_layout()

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

        # Local attributes
        self.gui: Optional[RapidAnnotationGUI] = None
        self.tracked_annotations: list[str] = []
        self.output_dir: Optional[Path] = None
        self.data_unit: Optional[RapidAnnotationUnit] = None
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