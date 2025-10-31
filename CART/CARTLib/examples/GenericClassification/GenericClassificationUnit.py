from pathlib import Path

import slicer

from CARTLib.utils.data import CARTStandardUnit


VERSION = 0.01


class GenericClassificationUnit(CARTStandardUnit):
    """
    A data unit for the Generic Classification task.

    Manages the volumes, segmentations, and markups associated with a given case,
    as well as the current classification of the case (if any).
    """
    def __init__(
        self,
        case_data: dict[str, str],
        data_path: Path,
        scene: slicer.vtkMRMLScene = slicer.mrmlScene,
    ):
        super().__init__(case_data, data_path, scene)

        # Current classifications for this case
        self._classes: set[str] = set()

        # Other remarks for this case
        self.remarks: str = ""

    @property
    def classes(self):
        return self._classes

    def add_class(self, new_class: str):
        self._classes.add(new_class)

    def drop_class(self, drop_class: str):
        if drop_class not in self._classes:
            print(f"Case was not class '{drop_class}' already, not removed.")
            return
        self._classes.remove(drop_class)