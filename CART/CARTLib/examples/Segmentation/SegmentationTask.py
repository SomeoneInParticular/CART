from typing import Optional, TYPE_CHECKING

import qt
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
class SegmentationReviewTask(
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
        self, master_profile: MasterProfileConfig, job_profile: JobProfileConfig
    ):
        super().__init__(master_profile, job_profile)

        # Local Attributes
        self.gui = None
        self._data_unit: Optional[SegmentationUnit] = None
        self.segments_to_save: set[str] = set()

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
        self.segmentEditorWidget = CARTSegmentationEditorWidget()
        formLayout.addRow(self.segmentEditorWidget)

        # TMP: Add Button
        addButton = qt.QPushButton("[TMP] ADD!")
        def addCustomSeg():
            if self.data_unit:
                self.data_unit.add_custom_segmentation("Test!")
            self.segmentEditorWidget.refresh()
        addButton.clicked.connect(addCustomSeg)
        formLayout.addRow(addButton)

        self.logger.info("Segmentation Task set up successfully!")
        return formLayout

    def receive(self, data_unit: SegmentationUnit):
        self._data_unit = data_unit
        data_unit.layout_handler.apply_layout()

    def save(self) -> Optional[str]:
        pass

    @classmethod
    def getDataUnitFactories(cls) -> dict[str, DataUnitFactory]:
        return {
            "Default": SegmentationUnit
        }
