from pathlib import Path
from typing import TYPE_CHECKING

import ctk
import qt
from CARTLib.utils.config import JobProfileConfig
from slicer.i18n import tr as _

from CARTLib.utils.widgets import CARTSegmentationEditorWidget

from SegmentationConfig import SegmentationConfig
from SegmentationIO import SegmentationIO

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
                self.bound_task.local_config,
                self.bound_task.job_profile,
                ref_uid
            )
            # If the user confirms the changes, add the custom seg.
            if prompt.exec():
                # Register the new custom segmentation
                self.bound_task.new_custom_segmentation(prompt.name, prompt.save_path, prompt.color_hex)
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

    # Default to a gold-ish color
    DEFAULT_COLOR = "#fadd00"

    def __init__(
        self,
        task_config: SegmentationConfig,
        job_config: JobProfileConfig,
        reference_uid: str = "sub-abc123",
        parent: qt.QObject = None,
    ):
        super().__init__(parent)

        # Track the parameters for later
        self.output_path: Path = job_config.output_path
        self.task_config: SegmentationConfig = task_config
        self.job_config: JobProfileConfig = job_config
        self.reference_uid: str = reference_uid

        # Initial setup
        self.setWindowTitle(_("Custom Segmentation"))
        layout = qt.QFormLayout(self)
        self.setMinimumSize(400, self.minimumHeight)

        # Make all labels bold
        labelFont = qt.QFont()
        labelFont.setBold(True)

        # Name to give the new segmentation
        nameLabel = qt.QLabel(_("Name: "))
        nameLabel.setFont(labelFont)
        nameEdit = qt.QLineEdit()
        nameToolTip = _("The name this segmentation should be labelled with.")
        nameLabel.setToolTip(nameToolTip)
        nameEdit.setToolTip(nameToolTip)
        layout.addRow(nameLabel, nameEdit)
        self._nameEdit = nameEdit

        # Where it should be saved
        savePathLabel = qt.QLabel(_("Output: "))
        savePathLabel.setFont(labelFont)
        savePathEdit = qt.QLineEdit()
        savePathToolTip = _("Where the segmentation should be saved.")
        savePathLabel.setToolTip(savePathToolTip)
        savePathEdit.setToolTip(savePathToolTip)
        layout.addRow(savePathLabel, savePathEdit)
        self.savePath = savePathEdit

        # Color picker
        colorLabel = qt.QLabel(_("Color: "))
        colorLabel.setFont(labelFont)
        colorPicker = ctk.ctkColorPickerButton()
        colorPicker.setColor(qt.QColor(self.DEFAULT_COLOR))
        colorToolTip = _(
            "The color the segmentation will display as in the editor."
        )
        colorLabel.setToolTip(colorToolTip)
        colorPicker.setToolTip(colorToolTip)
        layout.addRow(colorLabel, colorPicker)
        self.colorPicker = colorPicker

        colorPicker.colorChanged.connect(
            lambda c: print(c.name())
        )

        # Collapsible descriptions of the placeholder characters
        placeholderGroupBox = ctk.ctkCollapsibleGroupBox()
        placeholderGroupBox.setTitle(_("Placeholder Characters"))
        placeholderLayout = qt.QFormLayout(placeholderGroupBox)
        monoFont = qt.QFont("Monospace")
        monoFont.setBold(True)
        monoFont.setStyleHint(qt.QFont.TypeWriter)
        for k, v in SegmentationIO.REPLACEMENT_MAP_DESCRIPTIONS.items():
            characterLabel = qt.QLabel(k)
            characterLabel.setFont(monoFont)
            descriptionLabel = qt.QLabel(_(v))
            descriptionLabel.setWordWrap(True)
            placeholderLayout.addRow(characterLabel, descriptionLabel)
        for v in sorted(dir(placeholderGroupBox)):
            if callable(getattr(placeholderGroupBox, v)):
                print(f"{v}()")
            else:
                print(v)
        placeholderGroupBox.collapsed = True
        layout.addRow(placeholderGroupBox)

        # Preview of the full output path
        previewLabel = qt.QLabel(_("Preview: "))
        previewLabel.setFont(labelFont)
        previewOutput = qt.QLabel()
        previewToolTip = _(
            "A preview of the full output after processing will appear here."
        )
        previewLabel.setToolTip(previewToolTip)
        previewOutput.setToolTip(previewToolTip)
        previewOutput.setWordWrap(True)
        layout.addRow(previewLabel, previewOutput)

        # "Pseudo-Stretch" to push the buttons to the bottom
        stretch = qt.QWidget(None)
        policy = stretch.sizePolicy
        policy.setVerticalStretch(1)
        stretch.setSizePolicy(policy)
        layout.addRow(stretch)

        # Preview updating functions
        nameEdit.textChanged.connect(
            lambda __: previewOutput.setText(self._update_preview())
        )
        savePathEdit.textChanged.connect(
            lambda __: previewOutput.setText(self._update_preview())
        )
        previewOutput.setText(self._update_preview())

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
            applyButton.setEnabled(name not in self.task_config.custom_segmentations)
        nameEdit.textChanged.connect(validateName)

    @property
    def name(self) -> str:
        return self._nameEdit.text

    @property
    def save_path(self) -> str:
        return self.savePath.text

    @property
    def color_hex(self):
        return self.colorPicker.color.name()

    def _update_preview(self) -> str:
        formatted_text = SegmentationIO.format_output_str(
            self.save_path,
            SegmentationIO.build_placeholder_map(
                uid=self.reference_uid,
                segmentation_name=self.name,
                job_name=self.job_config.name
            ),
            self.job_config.output_path
        )

        # If formatting failed, mark this as invalid
        if formatted_text is None:
            return "[INVALID]"
        # Otherwise, return the string as-is
        return formatted_text
