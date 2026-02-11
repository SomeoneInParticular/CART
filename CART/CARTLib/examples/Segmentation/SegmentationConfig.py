from CARTLib.utils.config import DictBackedConfig, JobProfileConfig


class SegmentationConfig(DictBackedConfig):
    """
    Configuration manager for the MultiContrast task
    """

    CONFIG_KEY = "multi_contrast_segmentation"

    def __init__(self, parent_config: JobProfileConfig):
        super().__init__(parent_config=parent_config)

    @classmethod
    def default_config_label(cls) -> str:
        return cls.CONFIG_KEY

    def show_gui(self) -> None:
        pass

    ## CONFIG ENTRIES ##
    SHOULD_INTERPOLATE_KEY = "should_interpolate"

    @property
    def should_interpolate(self) -> bool:
        return self.get_or_default(self.SHOULD_INTERPOLATE_KEY, True)

    @should_interpolate.setter
    def should_interpolate(self, new_val: bool):
        self.backing_dict[self.SHOULD_INTERPOLATE_KEY] = new_val
        self._has_changed = True

    CUSTOM_SEGMENTATIONS_KEY = "custom_segmentations"
    CUSTOM_SEG_PATH_KEY = "path_string"
    CUSTOM_SEG_COLOR_KEY = "color"

    @property
    def custom_segmentations(self) -> dict[str, dict]:
        return self.get_or_default(self.CUSTOM_SEGMENTATIONS_KEY, dict())

    @custom_segmentations.setter
    def custom_segmentations(self, new_vals: dict[str, dict]):
        self.backing_dict[self.CUSTOM_SEGMENTATIONS_KEY] = new_vals
        self.has_changed = True

    def add_custom_segmentation(self, new_name: str, output_str: str, color_hex: str):
        sub_dict = {
            self.CUSTOM_SEG_PATH_KEY: output_str,
            self.CUSTOM_SEG_COLOR_KEY: color_hex
        }
        self.custom_segmentations[new_name] = sub_dict
        self.has_changed = True
