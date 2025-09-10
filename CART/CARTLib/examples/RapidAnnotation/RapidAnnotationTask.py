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

        # TODO: Actually add some working GUI
        dummyButton = qt.QPushButton("Dummy")

        formLayout.addRow(dummyButton)

        return formLayout

    def update(self, data_unit: RapidAnnotationUnit):
        self.data_unit = data_unit
        self.data_unit.layout_handler.apply_layout()

    ## GUI SYNCHRONIZATION ##
    def enter(self) -> None:
        pass

    def exit(self) -> None:
        pass



@cart_task("Rapid Annotation")
class RapidAnnotationTask(TaskBaseClass[RapidAnnotationUnit]):
    def __init__(self, profile: ProfileConfig):
        super().__init__(profile)

        # Local attributes
        self.gui: Optional[RapidAnnotationGUI] = None
        self.output_dir: Optional[Path] = None
        self.data_unit: Optional[RapidAnnotationUnit] = None
        self.csv_log_path: Optional[Path] = None

    def setup(self, container: qt.QWidget) -> None:
        print(f"Running {self.__class__.__name__} setup!")

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

    @classmethod
    def getDataUnitFactories(cls) -> dict[str, DataUnitFactory]:
        return {
            "Default": RapidAnnotationUnit
        }