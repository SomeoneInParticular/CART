from pathlib import Path
from typing import Optional

import qt

from CARTLib.core.TaskBaseClass import TaskBaseClass, DataUnitFactory
from CARTLib.utils.config import ProfileConfig
from CARTLib.utils.task import cart_task

from GenericClassificationGUI import GenericClassificationGUI
from GenericClassificationUnit import GenericClassificationUnit


VERSION = 0.01


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

        # Currently registered classes, including their description
        self.class_map: dict[str, str] = dict()

        # TMP
        for i in range(50):
            self.class_map[str(i)] = f"Dummy Text for {i}"

    @property
    def classes(self) -> list[str]:
        return list(self.class_map.keys())

    def setup(self, container: qt.QWidget):
        # Create and track the GUI
        self.gui = GenericClassificationGUI(self)
        gui_layout = self.gui.setup()
        container.setLayout(gui_layout)

    def receive(self, data_unit: GenericClassificationUnit):
        # Track the data unit for later
        self.current_unit = data_unit

        # Refresh the GUI to match the new data unit's contents
        if self.gui:
            self.gui.syncWithDataUnit()

    def save(self) -> Optional[str]:
        pass

    @classmethod
    def getDataUnitFactories(cls) -> dict[str, DataUnitFactory]:
        return {
            "Default": GenericClassificationUnit
        }
