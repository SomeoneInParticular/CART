from typing import TYPE_CHECKING

import qt
from slicer.i18n import tr as _

from CARTLib.utils.formatting import FilePathFormatter
from CARTLib.utils.widgets import CARTSegmentationEditorWidget

if TYPE_CHECKING:
    # Provide some type references for QT, even if they're perfect
    import PyQt5.Qt as qt
    # Avoid a cyclic reference
    from SegmentationTask import SegmentationTask


class SegmentationGUI:
    def __init__(self, bound_task: "SegmentationTask"):
        self.bound_task = bound_task

        # Segment editor; tracked so it can be refreshed
        self._segmentEditorWidget: CARTSegmentationEditorWidget = None

    def setup(self) -> qt.QFormLayout:
        # Initialize the layout we'll insert everything into
        formLayout = qt.QFormLayout(None)

        # Segmentation editor
        segmentEditorWidget = CARTSegmentationEditorWidget()
        formLayout.addRow(segmentEditorWidget)
        self._segmentEditorWidget = segmentEditorWidget

        return formLayout

    def onSavePrompt(
        self,
        saved: dict[str, str],
        failed: dict[str, str]
    ):
        """
        Show the user a prompt notifying them that the data unit was saved.

        Provide (hidden by default) details if the user requests it.
        """
        # The core message box
        msgBox = qt.QMessageBox()
        msgBox.setWindowTitle(_("Saved!"))
        msgBox.setStandardButtons(qt.QMessageBox.Ok)

        # Build the "main" user message
        successes = len(saved)
        failures = len(failed)
        msg = f"Saved data unit {self.bound_task.data_unit.uid}! {successes} segmentations were saved"
        if failures > 0:
            msg += f", {failures} segmentations were not"
        msg += "."
        msgBox.setText(_(msg))

        # Detailed text w/ save paths + error causes
        bullet_txt = "\n  ○ "
        detailed_text_cmps = []
        if successes > 0:
            saved_custom_txt = f"Saved the following segmentations:"
            saved_custom_txt = bullet_txt.join([
                saved_custom_txt, *[f"{k}: {v}" for k, v in saved.items()]
            ])
            detailed_text_cmps.append(saved_custom_txt)
        if failures > 0:
            saved_custom_txt = f"Failed to save the following segmentations:"
            saved_custom_txt = bullet_txt.join([
                saved_custom_txt, *[f"{k}: {v}" for k, v in failed.items()]
            ])
            detailed_text_cmps.append(saved_custom_txt)
        separator = "\n" + "=" * 40 + "\n"
        detailed_text = separator.join(detailed_text_cmps)
        msgBox.setDetailedText(detailed_text)

        msgBox.exec()

    def enter(self):
        self._segmentEditorWidget.enter()

    def exit(self):
        self._segmentEditorWidget.exit()

    def refresh(self):
        self.editFileFormatter.update_placeholder(
            FilePathFormatter.DEFAULT_UID_PLACEHOLDER, self.bound_task.data_unit.uid
        )
        self._segmentEditorWidget.refresh()
