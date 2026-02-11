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

    CUSTOM_SEGMENTATIONS = "custom_segmentations"

    @property
    def custom_segmentations(self) -> list[str]:
        return self.get_or_default(self.CUSTOM_SEGMENTATIONS, list())

    @custom_segmentations.setter
    def custom_segmentations(self, new_vals: list[str]):
        self.backing_dict[self.CUSTOM_SEGMENTATIONS] = new_vals

    def add_custom_segmentation(self, new_name):
        self.custom_segmentations.append(new_name)
        self._has_changed = True
