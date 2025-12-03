import json
from pathlib import Path
from typing import Optional

from CARTLib.utils.config import DictBackedConfig
from . import CART_PATH

JOB_PROFILE_DIR = CART_PATH / "job_profiles"


class JobProfileConfig(DictBackedConfig):
    NAME_KEY = "name"

    def __init__(
            self,
            parent_config: Optional["DictBackedConfig"] = None,
            config_key_override: Optional[str] = None,
            file_path: Optional[Path] = None
    ):
        super().__init__(parent_config, config_key_override)

        self._file_path = file_path

    @property
    def name(self) -> Optional[str]:
        return self.backing_dict.get(self.NAME_KEY, None)

    @name.setter
    def name(self, new_name: str):
        self.backing_dict[self.NAME_KEY] = new_name
        self.has_changed = True

    DATA_PATH_KEY = "data_path"

    @property
    def data_path(self) -> Optional[Path]:
        path_str = self.backing_dict.get(self.DATA_PATH_KEY, None)
        if path_str is None:
            return None
        return Path(path_str)

    @data_path.setter
    def data_path(self, new_path: Path):
        path_str = str(new_path)
        self.backing_dict[self.DATA_PATH_KEY] = path_str
        self.has_changed = True

    OUTPUT_PATH_KEY = "output_path"

    @property
    def output_path(self) -> Optional[Path]:
        path_str = self.backing_dict.get(self.OUTPUT_PATH_KEY, None)
        if path_str is None:
            return None
        return Path(path_str)

    @output_path.setter
    def output_path(self, new_path: Path):
        path_str = str(new_path)
        self.backing_dict[self.OUTPUT_PATH_KEY] = path_str
        self.has_changed = True

    COHORT_FILE_KEY = "cohort_file"

    @property
    def cohort_path(self) -> Optional[Path]:
        path_str = self.backing_dict.get(self.COHORT_FILE_KEY, None)
        if path_str is None:
            return None
        return Path(path_str)

    @cohort_path.setter
    def cohort_path(self, new_path: Path):
        path_str = str(new_path)
        self.backing_dict[self.COHORT_FILE_KEY] = path_str
        self.has_changed = True

    ## Abstract Methods ##
    @classmethod
    def default_config_label(cls) -> str:
        return "job_profile"

    def show_gui(self) -> None:
        pass

    ## File I/O ##
    @property
    def file(self) -> Path:
        if self._file_path:
            return self._file_path
        else:
            # Format the job name to create our corresponding filename
            default_filename = self.name.lower().replace(" ", "_") + ".json"
            new_file = JOB_PROFILE_DIR / default_filename
            self._file_path = new_file
            return new_file

    def reload(self):
        """
        (Re-)loads config's contents into memory.
        """
        # If there's no config file yet, there's nothing to load
        if not self.file.exists():
            print("Nothing to load!")
            return
        # Otherwise,
        with open(self.file, 'r') as fp:
            new_data = json.load(fp)
            self.backing_dict = new_data

    def save_without_parent(self) -> None:
        # Save this config to file.
        self.file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.file, 'w') as fp:
            json.dump(self.backing_dict, fp, indent=2)
