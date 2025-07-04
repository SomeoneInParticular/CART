from pathlib import Path
from typing import Optional

import slicer
from slicer.ScriptedLoadableModule import *
from slicer.i18n import tr as _

from .core.DataUnitBase import DataUnitBase


class VolumeOnlyDataUnit(DataUnitBase, ScriptedLoadableModuleLogic):

    def __init__(
            self,
            data: dict,
            data_path: Path,
            # TMP: Until 5.9 (w/ Python 3.10+ support) is released, Optional is needed
            scene: Optional[slicer.vtkMRMLScene] = None
    ):
        """
        Initialize the VolumeOnlyDataIO with optional initial data.

        Args:
            data (dict, optional): Initial data to populate the instance.
        """

        if scene is None:
            # Use the default MRML scene if none is provided
            scene = slicer.mrmlScene
        self.base_path = data_path
        print(data_path)
        super().__init__(
            data=data,
            data_path=data_path
        )
        self._initialize_resources()


    def _validate(self):
        """
        Validate the data in this instance.

        Raises:
            ValueError: If the data is invalid.
        """
        if not self.uid:
            raise ValueError(_("UID is required for VolumeOnlyDataIO."))

        key: str
        value: str | Path
        for key, value in self.data.items():
            if key == "uid":
                continue
            else:
                file_path = self._parse_path(value)
                if not file_path.exists():
                    raise ValueError(
                        f"Invalid data for key '{key}': file does not exist at {value}."
                    )

                if not file_path.name.endswith(".nrrd"):
                    raise ValueError(
                        f"Invalid data for key '{key}': value must be a .nrrd file."
                    )

        self.validated = True

    def _parse_path(self, path_str: str):
        # TODO: Make this reference a user-specified value instead
        if self.base_path is None:
            return Path(path_str)
        elif not isinstance(self.base_path, Path):
            raise ValueError(_("Base path must be a Path object."))
        elif not self.base_path.is_dir() or not self.base_path.exists():
            raise ValueError(_("Base path is not a valid directory."))
        else:
            return self.base_path / path_str


    def _initialize_resources(self):
        """
        Initialize the resources for this VolumeOnlyDataIO instance.

        This method should be called after validation to set up the resources.
        """
        if not self.validated:
            raise ValueError(_("Data must be validated before initializing resources."))

        # Example of how to initialize resources, assuming the data is a file path
        for key, value in self.data.items():
            if key != "uid":
                file_path = self._parse_path(value)
                node = slicer.util.loadVolume(file_path)
                if node:
                    print(f"Loaded volume from {file_path} into node {node.GetName()} with {node=}")
                    node.SetName(key)
                    self.resources[key] = node
                else:
                    raise ValueError(f"Failed to load volume from {value}")


    def to_dict(self) -> dict:
        """
        Convert the data from the associated MRML nodes to a dictionary representation.

        Returns:
            dict: A dictionary representation of the data.
        """
        # THIS IS NOT A COMMMON USE CASE, BUT BC THERE IS NO DATA IN THE MRML SCENE ONLY FILES WE ARE GOOD
        return self.data