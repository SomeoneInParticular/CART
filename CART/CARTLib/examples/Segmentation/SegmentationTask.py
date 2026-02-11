import traceback
from typing import Optional, TYPE_CHECKING

import qt

from CARTLib.core.TaskBaseClass import TaskBaseClass, DataUnitFactory
from CARTLib.utils.config import MasterProfileConfig, JobProfileConfig
from CARTLib.utils.task import cart_task
from CARTLib.utils.widgets import showErrorPrompt

from SegmentationConfig import SegmentationConfig
from SegmentationGUI import SegmentationGUI
from SegmentationUnit import SegmentationUnit


if TYPE_CHECKING:
    # Provide some type references for QT, even if they're not
    #  perfectly useful.
    import PyQt5.Qt as qt


@cart_task("Segmentation")
class SegmentationTask(
    TaskBaseClass[SegmentationUnit]
):

    @classmethod
    def description(cls) -> str:
        return "WIP!"

    @classmethod
    def feature_types(cls, data_factory_label: str) -> dict[str, str]:
        # Delegate to the data unit's defaults
        return SegmentationUnit.feature_types()

    @classmethod
    def format_feature_label_for_type(
        cls, initial_label: str, data_unit_factory_type: str, feature_type: str
    ):
        # Apply default comma processing
        initial_label = super().format_feature_label_for_type(
            initial_label, data_unit_factory_type, feature_type
        )
        # Defer to the data unit itself for further processing
        duf = cls.getDataUnitFactories().get(data_unit_factory_type, None)
        if duf is SegmentationUnit:
            return SegmentationUnit.feature_label_for(initial_label, feature_type)
        return initial_label

    def __init__(
        self,
        master_profile: MasterProfileConfig,
        job_profile: JobProfileConfig,
        cohort_features: list[str],
    ):
        super().__init__(master_profile, job_profile, cohort_features)

        # Local Attributes
        self.gui: Optional[SegmentationGUI] = None
        self._data_unit: Optional[SegmentationUnit] = None

        # Config init
        self._config = SegmentationConfig(job_profile)

    @property
    def data_unit(self) -> SegmentationUnit:
        # Get-only; use "receive" instead
        return self._data_unit

    def setup(self, container: qt.QWidget):
        """
        Build the GUI's contents, returning the resulting layout for use.
        """
        self.logger.info("Setting up Segmentation Task!")

        # Initialize the layout we'll insert everything into
        self.gui = SegmentationGUI(self)
        container.setLayout(self.gui.setup())
        self.gui.enter()

        self.logger.info("Segmentation Task set up successfully!")

    def receive(self, data_unit: SegmentationUnit):
        self._data_unit = data_unit

        # Change the interpolation settings to match current setting
        self.apply_interp()

        # Add any custom segmentations configured by the user to the unit
        self._init_custom_segmentations()

        # If we have a GUI, refresh it
        if self.gui:
            self.gui.refresh()

    def save(self) -> Optional[str]:
        pass

    @classmethod
    def getDataUnitFactories(cls) -> dict[str, DataUnitFactory]:
        return {
            "Default": SegmentationUnit
        }

    ## Configurable Settings ##
    @property
    def should_interpolate(self):
        return self._config.should_interpolate

    @should_interpolate.setter
    def should_interpolate(self, new_val: bool):
        self._config.should_interpolate = new_val

    def apply_interp(self):
        # Apply interpolation settings to the volume
        if not self.data_unit:
            return
        for n in self.data_unit.volume_nodes.values():
            display_node = n.GetDisplayNode()
            display_node.SetInterpolate(self.should_interpolate)

    @property
    def custom_segmentations(self) -> list[str]:
        return self._config.custom_segmentations

    def new_custom_segmentation(self, new_name: str):
        """
        Register a new custom segmentation. Adds a (blank) segmentation
        with the corresponding name to the current data unit as well.
        """
        # Add it to our configuration and save
        self.custom_segmentations.append(new_name)
        self._config.save()

        # If this is a new custom segmentation for the data unit, add it as well
        if self.data_unit and new_name not in self.data_unit.custom_segmentations.keys():
            try:
                self.data_unit.add_custom_segmentation(new_name)
                if self.gui:
                    self.gui.refresh()
            except Exception as e:
                self.logger.error(traceback.format_exc())
                if self.gui:
                    showErrorPrompt(str(e), None)
                return

        # If we have a GUI, refresh it
        if self.gui:
            self.gui.refresh()

    ## Segmentation Management ##
    def _init_custom_segmentations(self):
        """
        Add a custom segmentation to the data unit
        """
        # If we don't have a data unit, end here w/ an error
        if not self.data_unit:
            msg = "Cannot add custom segmentation; no data unit has been loaded!"
            self.logger.error(msg)
            if self.gui:
                showErrorPrompt(msg, None)

        # Add each custom segmentation in turn
        for name in self.custom_segmentations:
            try:
                self.data_unit.add_custom_segmentation(name)
                if self.gui:
                    self.gui.refresh()
            # Skip duplicate key errors in this case
            except ValueError as e:
                if "already exists" in str(e):
                    continue
                raise e
            # All other errors should end the loop and notify the user
            except Exception as e:
                self.logger.error(traceback.format_exc())
                if self.gui:
                    showErrorPrompt(str(e), None)
                return

    def enter(self):
        if self.gui:
            self.gui.enter()

    def exit(self):
        if self.gui:
            self.gui.exit()
