from pathlib import Path
from typing import TYPE_CHECKING

import qt
from slicer.i18n import tr as _

from CARTLib.utils.widgets import CARTSegmentationEditorWidget

from SegmentationConfig import SegmentationConfig

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
        self._segmentEditorWidget: CARTSegmentationEditorWidget = None

    def setup(self) -> qt.QFormLayout:
        # Initialize the layout we'll insert everything into
        formLayout = qt.QFormLayout(None)

        # Segmentation editor
        segmentEditorWidget = CARTSegmentationEditorWidget()
        formLayout.addRow(segmentEditorWidget)
        self._segmentEditorWidget = segmentEditorWidget

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

        # Add Custom Button
        # TODO: Move this to an on-init prompt instead
        addButton = qt.QPushButton("Add Custom Segmentation")
        def addCustomSeg():
            # Prompt the user with details
            ref_uid = (
                "sub-abc123"
                if self.bound_task.data_unit is None
                else self.bound_task.data_unit.uid
            )
            prompt = CustomSegmentationDialog(
                self.bound_task.job_profile.output_path,
                self.bound_task.local_config,
                ref_uid
            )
            # If the user confirms the changes, add the custom seg.
            if prompt.exec():
                # Register the new custom segmentation
                self.bound_task.new_custom_segmentation(prompt.name)

        addButton.clicked.connect(addCustomSeg)
        formLayout.addRow(addButton)

        return formLayout

    def selectSegmentationNode(self, node):
        self._segmentEditorWidget.setSegmentationNode(node)

    def enter(self):
        self._segmentEditorWidget.enter()

    def exit(self):
        self._segmentEditorWidget.exit()

    def refresh(self):
        self._segmentEditorWidget.refresh()


class CustomSegmentationDialog(qt.QDialog):
    """
    Prompt the user to created/edit a custom segmentation.
    """

    def __init__(
        self,
        output_path: Path,
        config: SegmentationConfig,
        reference_uid: str = "sub-abc123",
        parent: qt.QObject = None,
    ):
        super().__init__(parent)

        # Track the parameters for later
        self.output_path: Path = output_path
        self.config: SegmentationConfig = config
        self.reference_uid: str = reference_uid

        # Initial setup
        self.setWindowTitle(_("Custom Segmentation"))
        layout = qt.QFormLayout(self)

        # Name to give the new segmentation
        nameLabel = qt.QLabel(_("Name: "))
        nameEdit = qt.QLineEdit()
        nameToolTip = _("The name this segmentation should be labelled with.")
        nameLabel.setToolTip(nameToolTip)
        nameEdit.setToolTip(nameToolTip)
        layout.addRow(nameLabel, nameEdit)
        self._nameEdit = nameEdit

        # # Where it should be saved
        # outputLabel = qt.QLabel(_("Output: "))
        # outputEdit = qt.QLineEdit()
        # outputToolTip = _("Where the segmentation should be saved.")
        # outputLabel.setToolTip(outputToolTip)
        # outputEdit.setToolTip(outputToolTip)
        # layout.addRow(outputLabel, outputEdit)
        # self.outputEdit = outputEdit
        #
        # # Preview of the full output path
        # previewLabel = qt.QLabel(_("Preview: "))
        # previewOutput = qt.QLabel("[N/A]")
        # previewFont = qt.QFont()
        # previewFont.setBold(True)
        # previewOutput.setFont(previewFont)
        # previewToolTip = _(
        #     "A preview of the full output after processing will appear here."
        # )
        # previewLabel.setToolTip(previewToolTip)
        # previewOutput.setToolTip(previewToolTip)
        #
        # # Preview updating functions
        # nameEdit.textChanged.connect(
        #     lambda __: previewLabel.setText(self._update_preview())
        # )
        # outputEdit.textChanged.connect(
        #     lambda __: previewLabel.setText(self._update_preview())
        # )

        # Ok/Cancel Buttons
        buttonBox = qt.QDialogButtonBox()
        buttonBox.setStandardButtons(
            qt.QDialogButtonBox.Apply | qt.QDialogButtonBox.Cancel
        )
        def onButtonClicked(button: qt.QPushButton):
            button_role = buttonBox.buttonRole(button)
            if button_role == qt.QDialogButtonBox.RejectRole:
                self.reject()
            elif button_role == qt.QDialogButtonBox.ApplyRole:
                self.accept()
            else:
                raise ValueError("Pressed a button with an invalid role!")
        buttonBox.clicked.connect(onButtonClicked)
        layout.addRow(buttonBox)

        # Ensure the user can only confirm if the name is valid
        applyButton: qt.QPushButton = buttonBox.button(qt.QDialogButtonBox.Apply)
        def validateName(name: str):
            applyButton.setEnabled(name not in self.config.custom_segmentations)
        nameEdit.textChanged.connect(validateName)

    @property
    def name(self) -> str:
        return self._nameEdit.text

    # @property
    # def output(self) -> str:
    #     return self.outputEdit.text

    # def _update_preview(self) -> str:
    #     replacement_map = {
    #         "%u": self.reference_uid,
    #         "%n": self.name
    #     }
    #
    #     formatted_text = self.output
    #     for k, v in replacement_map:
    #         formatted_text.replace(k, v)
    #
    #     result_path = Path(formatted_text)
    #     if result_path.is_absolute():
    #         return str(result_path)
    #     else:
    #         return str(self.output_path / result_path)
