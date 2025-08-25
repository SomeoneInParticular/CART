from CARTLib.utils.config import UserConfig


class MultiContrastSegmentationConfig:
    """
    Configuration manager for the MultiContrast task
    """
    def __init__(self, backing_dict: dict, parent_config: UserConfig):
        self._backing_dict = backing_dict
        self.parent_config = parent_config

    @property
    def backing_dict(self) -> dict:
        return self._backing_dict.copy()

    @backing_dict.setter
    def backing_dict(self, new_dict: dict):
        self._backing_dict.clear()
        for k, v in new_dict.values():
            self._backing_dict[k] = v

    ## Configuration Options ##
    SHOW_ON_LOAD_KEY = "show_on_load"

    @property
    def show_on_load(self) -> bool:
        return self._backing_dict.get(self.SHOW_ON_LOAD_KEY, False)

    @show_on_load.setter
    def show_on_load(self, new_state: bool):
        self._backing_dict[self.SHOW_ON_LOAD_KEY] = new_state
