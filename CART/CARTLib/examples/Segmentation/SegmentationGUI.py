from typing import TYPE_CHECKING

import qt
from slicer.i18n import tr as _

from CARTLib.utils.widgets import CARTSegmentationEditorWidget

if TYPE_CHECKING:
    # Provide some type references for QT, even if they're not
    #  perfectly useful.
    import PyQt5.Qt as qt
    # Avoid a cyclic reference
    from SegmentationTask import SegmentationTask


class SegmentationGUI:
    def __init__(self, bound_task: "SegmentationTask"):
        self.bound_task = bound_task

        # Segment editor; tracked so it can be refreshed
        self.segmentEditorWidget: CARTSegmentationEditorWidget = None

    def setup(self) -> qt.QFormLayout:
        # Initialize the layout we'll insert everything into
        formLayout = qt.QFormLayout(None)

        # Segmentation editor
        segmentEditorWidget = CARTSegmentationEditorWidget()
        formLayout.addRow(segmentEditorWidget)
        self.segmentEditorWidget = segmentEditorWidget

        # Interpolation toggle
        interpToggle = qt.QCheckBox()
        interpLabel = qt.QLabel(_("Interpolate Volumes:"))
        interpToolTip = _(
            "Whether volumes should be visualized with interpolation (smoothing)."
        )
        interpLabel.setToolTip(interpToolTip)
        interpToggle.setToolTip(interpToolTip)
        def setInterp():
            self.bound_task.should_interpolate = interpToggle.isChecked()
            self.bound_task.apply_interp()
        interpToggle.setChecked(self.bound_task.should_interpolate)
        interpToggle.toggled.connect(setInterp)
        formLayout.addRow(interpLabel, interpToggle)

        # TMP: Add Button
        # TODO: Move this to an on-init prompt instead
        addButton = qt.QPushButton("[TMP] ADD!")
        def addCustomSeg():
            # Delegate to the task
            self.bound_task.new_custom_segmentation("Test!")
            # Refresh our editor widget
            segmentEditorWidget.refresh()
        addButton.clicked.connect(addCustomSeg)
        formLayout.addRow(addButton)

        return formLayout

    def enter(self):
        self.segmentEditorWidget.enter()

    def exit(self):
        self.segmentEditorWidget.exit()

    def refresh(self):
        self.segmentEditorWidget.refresh()
        pass