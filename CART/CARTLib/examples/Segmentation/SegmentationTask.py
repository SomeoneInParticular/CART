from typing import Optional, TYPE_CHECKING

import qt
from slicer.i18n import tr as _

from CARTLib.examples.Segmentation.SegmentationConfig import SegmentationConfig
from CARTLib.examples.Segmentation.SegmentationUnit import SegmentationUnit
from CARTLib.utils.config import MasterProfileConfig, JobProfileConfig
from CARTLib.core.TaskBaseClass import TaskBaseClass, DataUnitFactory
from CARTLib.utils.task import cart_task
from CARTLib.utils.widgets import CARTSegmentationEditorWidget


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
        self.gui = None
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
        formLayout = qt.QFormLayout(None)
        container.setLayout(formLayout)

        # Segmentation editor
        segmentEditorWidget = CARTSegmentationEditorWidget()
        formLayout.addRow(segmentEditorWidget)

        # Interpolation toggle
        interpToggle = qt.QCheckBox()
        interpLabel = qt.QLabel(_("Interpolate Volumes:"))
        interpToolTip = _(
            "Whether volumes should be visualized with interpolation (smoothing)."
        )
        interpLabel.setToolTip(interpToolTip)
        interpToggle.setToolTip(interpToolTip)
        def setInterp():
            self.should_interpolate = interpToggle.isChecked()
            self.apply_interp()
            self._config.save()
        interpToggle.setChecked(self.should_interpolate)
        interpToggle.toggled.connect(setInterp)
        formLayout.addRow(interpLabel, interpToggle)

        # TMP: Add Button
        addButton = qt.QPushButton("[TMP] ADD!")
        def addCustomSeg():
            if self.data_unit:
                self.data_unit.add_custom_segmentation("Test!")
            segmentEditorWidget.refresh()
        addButton.clicked.connect(addCustomSeg)
        formLayout.addRow(addButton)

        self.logger.info("Segmentation Task set up successfully!")
        return formLayout

    def receive(self, data_unit: SegmentationUnit):
        self._data_unit = data_unit

        # Change the interpolation settings to match current setting
        self.apply_interp()

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
