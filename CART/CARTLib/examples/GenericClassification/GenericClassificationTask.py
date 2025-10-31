from pathlib import Path
from typing import Optional

import qt
from CARTLib.core.TaskBaseClass import TaskBaseClass, DataUnitFactory, D
from CARTLib.examples.GenericClassification.GenericClassificationUnit import GenericClassificationUnit
from CARTLib.utils.config import ProfileConfig
from CARTLib.utils.task import cart_task


class GenericClassificationGUI:
    def __init__(self, bound_task: "GenericClassificationTask"):
        # The task (logic) this GUI should be bound too
        self.bound_task = bound_task

    @property
    def current_unit(self) -> GenericClassificationUnit:
        return self.bound_task.current_unit

    def syncWithTask(self):
        # TODO
        pass

@cart_task("Generic Classification")
class GenericClassificationTask(TaskBaseClass[GenericClassificationUnit]):
    """
    Task for classifying cases.

    Can be run in two modes:
    * Single Class: Only one classification can be selected per case
    * Multi-class: Multiple classifications can be selected per case

    Saves the classification(s) into a CSV folder
    """
    def __init__(self, profile: ProfileConfig):
        super().__init__(profile)

        # Track the active GUI instance, if any
        self.gui: Optional[GenericClassificationGUI] = None

        # CSV Log (path + contents)
        self.csv_log_path: Optional[Path] = None
        self.csv_log = None

        # Currently managed data unit
        self.current_unit: Optional[GenericClassificationUnit] = None

    def setup(self, container: qt.QWidget):
        pass

    def receive(self, data_unit: GenericClassificationUnit):
        # Track the data unit for later
        self.current_unit = data_unit

        # Refresh the GUI to match the new data unit's contents
        if self.gui:
            self.gui.syncWithTask()


    def save(self) -> Optional[str]:
        pass

    @classmethod
    def getDataUnitFactories(cls) -> dict[str, DataUnitFactory]:
        return {
            "Default": GenericClassificationUnit
        }
