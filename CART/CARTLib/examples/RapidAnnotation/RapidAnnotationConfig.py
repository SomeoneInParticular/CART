from pathlib import Path
from typing import Optional

from CARTLib.utils.config import DictBackedConfig, ProfileConfig


class RapidAnnotationConfig(DictBackedConfig):

    CONFIG_KEY = "rapid_annotation"

    @classmethod
    def default_config_label(cls) -> str:
        return cls.CONFIG_KEY

    ## Configuration Options ##
    LAST_USED_MARKUPS = "last_used_markup_labels"

    @property
    def last_used_markups(self) -> Optional[list[str]]:
        return self._backing_dict.get(self.LAST_USED_MARKUPS, None)

    @last_used_markups.setter
    def last_used_markups(self, new_markups: list[str]):
        self._backing_dict[self.LAST_USED_MARKUPS] = new_markups
        self.has_changed = True

    LAST_USED_OUTPUT = "last_used_output"

    @property
    def last_used_output(self) -> Optional[Path]:
        path_str = self._backing_dict.get(self.LAST_USED_OUTPUT, None)
        if path_str is None:
            return None
        return Path(path_str)

    @last_used_output.setter
    def last_used_output(self, new_path: Path):
        self._backing_dict[self.LAST_USED_OUTPUT] = str(new_path.resolve())
        self.has_changed = True

    ## Utils ##
    def show_gui(self) -> None:
        pass

