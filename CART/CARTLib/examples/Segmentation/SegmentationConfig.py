from enum import Enum
from typing import Optional, TYPE_CHECKING

import qt
from slicer.i18n import tr as _

from CARTLib.utils.config import DictBackedConfig, JobProfileConfig

if TYPE_CHECKING:
    # Provide some type references for QT, even if they're not
    #  perfectly useful.
    import PyQt5.Qt as qt


class SegmentationFileStructure(Enum):
    BIDS = "BIDS"
    FolderPerCase = "Folder-per-Case"


class SegmentationFileFormat(Enum):
    NIFTI = "NiFTI"
    NRRD = "NRRD"


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

    ## CONFIG ENTRIES ##
    SHOULD_INTERPOLATE_KEY = "should_interpolate"

    @property
    def should_interpolate(self) -> bool:
        return self.get_or_default(self.SHOULD_INTERPOLATE_KEY, True)

    @should_interpolate.setter
    def should_interpolate(self, new_val: bool):
        self.backing_dict[self.SHOULD_INTERPOLATE_KEY] = new_val
        self.has_changed = True

    HIDE_EDITABLE_ON_START_KEY = "hide_editable_on_start"

    @property
    def hide_editable_on_start(self) -> bool:
        return self.get_or_default(self.HIDE_EDITABLE_ON_START_KEY, False)

    @hide_editable_on_start.setter
    def hide_editable_on_start(self, new_val: bool):
        self.backing_dict[self.HIDE_EDITABLE_ON_START_KEY] = new_val
        self.has_changed = True

    SAVE_BLANK_SEGMENTATIONS_KEY = "save_blanks"

    @property
    def save_blank_segmentations(self) -> bool:
        return self.get_or_default(self.SAVE_BLANK_SEGMENTATIONS_KEY, True)

    @save_blank_segmentations.setter
    def save_blank_segmentations(self, new_val: bool):
        self.backing_dict[self.SAVE_BLANK_SEGMENTATIONS_KEY] = new_val
        self.has_changed = True

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

    SEGMENTATIONS_TO_SAVE_KEY = "segmentations_to_save"

    @property
    def segmentations_to_save(self) -> list[str]:
        return self.get_or_default(self.SEGMENTATIONS_TO_SAVE_KEY, list())

    @segmentations_to_save.setter
    def segmentations_to_save(self, new_segs: list[str]):
        self._backing_dict[self.SEGMENTATIONS_TO_SAVE_KEY] = new_segs
        self.has_changed = True

    EDIT_OUTPUT_PATH_KEY = "edit_output_path"

    @property
    def edit_output_path(self) -> str:
        return self.get_or_default(self.EDIT_OUTPUT_PATH_KEY, "")

    @edit_output_path.setter
    def edit_output_path(self, new_val: str):
        self.backing_dict[self.EDIT_OUTPUT_PATH_KEY] = new_val
        self.has_changed = True

    DEFAULT_CUSTOM_OUTPUT_PATH_KEY = "default_custom_output_path"

    @property
    def default_custom_output_path(self) -> str:
        return self.get_or_default(self.DEFAULT_CUSTOM_OUTPUT_PATH_KEY, "")

    @default_custom_output_path.setter
    def default_custom_output_path(self, new_val: str):
        self.backing_dict[self.DEFAULT_CUSTOM_OUTPUT_PATH_KEY] = new_val
        self.has_changed = True

    def generateGUILayout(self) -> tuple[str, Optional[qt.QLayout]]:
        return "Segmentation Configuration", SegmentationConfigGUILayout(self)


class SegmentationConfigGUILayout(qt.QFormLayout):
    def __init__(self, config: SegmentationConfig, parent = None, ):
        super().__init__(parent)

        # Output folder structure selection
        fileStructureComboBox = qt.QComboBox(None)
        fileStructureComboBox.addItems([x.value for x in SegmentationFileStructure])
        fileStructureLabel = qt.QLabel(_("Output File Structure:"))
        self.addRow(fileStructureLabel, fileStructureComboBox)

        # Output file structure selection
        fileFormatComboBox = qt.QComboBox(None)
        fileFormatComboBox.addItems([x.value for x in SegmentationFileFormat])
        fileFormatLabel = qt.QLabel(_("Output File Format:"))
        self.addRow(fileFormatLabel, fileFormatComboBox)

        # Toggle-able options
        toggleLayout = qt.QFormLayout(None)
        self.addRow(toggleLayout)

        ## Segmentation Overlap
        segmentOverlapCheckBox = qt.QCheckBox()
        segmentOverlapLabel = qt.QLabel(_("Disallow Overlapping Segments"))
        toggleLayout.addRow(segmentOverlapCheckBox, segmentOverlapLabel)

        ## Hide To-Edit Segments on Load
        hideEditSegmentsInitiallyCheckBox = qt.QCheckBox()
        hideEditSegmentsInitiallyLabel = qt.QLabel(_("Initially Hide To-Edit Segmentations"))
        toggleLayout.addRow(hideEditSegmentsInitiallyCheckBox, hideEditSegmentsInitiallyLabel)

        ## Whether to save blank segmentations
        saveEmptySegmentsCheckBox = qt.QCheckBox()
        saveEmptySegmentsLabel = qt.QLabel(_("Save Empty Segmentations (will result in 'blank' files)"))
        toggleLayout.addRow(saveEmptySegmentsCheckBox, saveEmptySegmentsLabel)

        # Connections
        # TODO
