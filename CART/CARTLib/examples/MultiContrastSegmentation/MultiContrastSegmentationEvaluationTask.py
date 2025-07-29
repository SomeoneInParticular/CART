import json
from datetime import datetime
from pathlib import Path
from typing import Optional
from enum import Enum

import ctk
import qt
import slicer
from slicer.i18n import tr as _
from .MultiContrastSegmentationEvaluationDataUnit import (
    MultiContrastSegmentationEvaluationDataUnit,
)
from CARTLib.core.TaskBaseClass import TaskBaseClass, DataUnitFactory
from CARTLib.utils.widgets import CARTSegmentationEditorWidget
from CARTLib.utils.data import save_segmentation_to_nifti
from CARTLib.utils.layout import LayoutHandler, Orientation

VERSION = 0.01


class OutputMode(Enum):
    PARALLEL_DIRECTORY = "parallel"
    OVERWRITE_ORIGINAL = "overwrite"


class MultiContrastSegmentationEvaluationGUI:
    def __init__(self, bound_task: "MultiContrastSegmentationEvaluationTask"):
        self.bound_task = bound_task
        self.data_unit: Optional[MultiContrastSegmentationEvaluationDataUnit] = None

        # The currently selected orientation in the GUI; determine our viewer layout
        self.currentOrientation: Orientation = Orientation.AXIAL

        # Widgets we'll need to reference later:
        self.segmentEditorWidget: Optional[CARTSegmentationEditorWidget] = None

    def setup(self) -> qt.QFormLayout:
        """
        Build the GUI's contents, returning the resulting layout for use.
        """
        # Initialize the layout we'll insert everything into
        formLayout = qt.QFormLayout()

        # 2) Orientation buttons
        self._addOrientationButtons(formLayout)

        # 3) Segmentation editor
        self.segmentEditorWidget = CARTSegmentationEditorWidget()
        formLayout.addRow(self.segmentEditorWidget)

        # 4) Save controls
        self._addOutputSelectionButton(formLayout)

        # Prompt for initial output setup
        self.promptSelectOutputMode()

        return formLayout

    def _addOrientationButtons(self, layout: qt.QFormLayout) -> None:
        """
        Buttons to set Axial/Sagittal/Coronal for all slice views.
        """
        hbox = qt.QHBoxLayout()
        for ori in Orientation.TRIO:
            label = ori.slicer_node_label()
            btn = qt.QPushButton(label)
            btn.clicked.connect(lambda _, o=ori: self.onOrientationChanged(o))
            hbox.addWidget(btn)
        layout.addRow(qt.QLabel("View Orientation:"), hbox)

    def _addOutputSelectionButton(self, layout: qt.QFormLayout) -> None:
        btn = qt.QPushButton("Change Output Settings")
        btn.clicked.connect(self.promptSelectOutputMode)
        layout.addRow(btn)

    #
    # Handlers
    #

    def onOrientationChanged(self, orientation: Orientation) -> None:
        # Update our currently tracked orientation
        self.currentOrientation = orientation

        # If we don't have a data unit at this point, end here
        if not self.data_unit:
            return

        # Update the data unit's orientation to match
        self.data_unit.set_orientation(orientation)

        # Apply the (likely updated) layout
        self.data_unit.layout_handler.apply_layout()

    ## USER PROMPTS ##
    def promptSelectOutputMode(self):
        """
        Prompt the user to select output mode and location.
        """
        # Initialize the prompt
        prompt = self._buildOutputModePrompt()

        # Show the prompt with "exec", blocking the main window until resolved
        result = prompt.exec()

        # If the user cancelled out of the prompt, notify them
        if result == 0:
            notif = qt.QErrorMessage()
            if self.bound_task.can_save():
                notif.setWindowTitle(_("REVERTING!"))
                notif.showMessage(
                    _("Cancelled out of window; keeping previous output settings.")
                )
                notif.exec()
            else:
                notif.setWindowTitle(_("NO OUTPUT!"))
                notif.showMessage(
                    _(
                        "No output settings selected! You will need to "
                        "specify this before segmentations can be saved."
                    )
                )
                notif.exec()

    def _buildOutputModePrompt(self):
        """Build the output mode selection dialog."""
        prompt = qt.QDialog()
        prompt.setWindowTitle("Select Output Mode")
        layout = qt.QVBoxLayout()
        prompt.setLayout(layout)

        # Add description
        description = qt.QLabel("Choose how to save your segmentations:")
        layout.addWidget(description)

        # Radio buttons for output mode
        self.outputModeGroup = qt.QButtonGroup()

        # Parallel directory option
        parallelRadio = qt.QRadioButton("Save to parallel directory structure")
        parallelRadio.setToolTip("Creates organized output in a separate directory")
        self.outputModeGroup.addButton(parallelRadio, 0)
        layout.addWidget(parallelRadio)

        # Overwrite original option
        overwriteRadio = qt.QRadioButton("Overwrite original segmentation files")
        overwriteRadio.setToolTip("Saves directly over the input segmentation files")
        self.outputModeGroup.addButton(overwriteRadio, 1)
        layout.addWidget(overwriteRadio)

        # Set default selection based on current mode
        if hasattr(self.bound_task, "output_mode"):
            if self.bound_task.output_mode == OutputMode.PARALLEL_DIRECTORY:
                parallelRadio.setChecked(True)
            else:
                overwriteRadio.setChecked(True)
        else:
            parallelRadio.setChecked(True)  # Default to parallel

        # Directory selection widget (only shown for parallel mode)
        dirLabel = qt.QLabel("Output directory:")
        self.outputFileEdit = ctk.ctkPathLineEdit()
        self.outputFileEdit.setToolTip(
            _("The directory where modified segmentations will be placed.")
        )
        self.outputFileEdit.filters = ctk.ctkPathLineEdit.Dirs

        # Set current directory if available
        if hasattr(self.bound_task, "output_dir") and self.bound_task.output_dir:
            self.outputFileEdit.currentPath = str(self.bound_task.output_dir)

        layout.addWidget(dirLabel)
        layout.addWidget(self.outputFileEdit)

        # Store references for enabling/disabling
        self.dirLabel = dirLabel

        # Connect radio button changes to update UI
        parallelRadio.toggled.connect(self._onOutputModeChanged)

        # Initial UI state
        self._onOutputModeChanged(parallelRadio.isChecked())

        # Button box
        buttonBox = qt.QDialogButtonBox()
        buttonBox.addButton(_("Confirm"), qt.QDialogButtonBox.AcceptRole)
        buttonBox.addButton(_("Cancel"), qt.QDialogButtonBox.RejectRole)
        layout.addWidget(buttonBox)

        # Connect acceptance
        buttonBox.accepted.connect(lambda: self._attemptOutputModeUpdate(prompt))
        buttonBox.rejected.connect(prompt.reject)

        # Resize for better appearance
        prompt.resize(500, prompt.minimumHeight)

        return prompt

    def _onOutputModeChanged(self, parallel_selected: bool):
        """Enable/disable directory selection based on mode."""
        self.dirLabel.setEnabled(parallel_selected)
        self.outputFileEdit.setEnabled(parallel_selected)

    def _linkedPathErrorPrompt(self, err_msg, prompt):
        """
        Prompt the user with an error message
        """
        failurePrompt = qt.QErrorMessage(prompt)
        failurePrompt.setWindowTitle("ERROR!")
        failurePrompt.showMessage(err_msg)
        failurePrompt.exec()

    def _attemptOutputModeUpdate(self, prompt: qt.QDialog):
        """
        Validates and applies the selected output mode and path.
        """
        # Get the selected mode
        selected_id = self.outputModeGroup.checkedId()
        if selected_id == 0:
            selected_mode = OutputMode.PARALLEL_DIRECTORY
        elif selected_id == 1:
            selected_mode = OutputMode.OVERWRITE_ORIGINAL
        else:
            self._linkedPathErrorPrompt("Please select an output mode", prompt)
            return

        # Handle parallel directory mode
        if selected_mode == OutputMode.PARALLEL_DIRECTORY:
            output_path_str = self.outputFileEdit.currentPath.strip()

            if not output_path_str:
                err_msg = "Output path was empty"
                self._linkedPathErrorPrompt(err_msg, prompt)
                return

            output_path = Path(output_path_str)
            err_msg = self.bound_task.set_output_mode(selected_mode, output_path)
        else:
            # Overwrite original mode
            err_msg = self.bound_task.set_output_mode(selected_mode)

        # Check for errors
        if err_msg:
            self._linkedPathErrorPrompt(err_msg, prompt)
            return

        # Success - close the prompt
        prompt.accept()

    def update(self, data_unit: MultiContrastSegmentationEvaluationDataUnit) -> None:
        """
        Called whenever a new data-unit is in focus.
        Populate the volume combo, select primary, and fire off initial layers.
        """
        self.data_unit = data_unit
        # sync segmentation editor
        self.segmentEditorWidget.setSegmentationNode(
            self.data_unit.primary_segmentation_node
        )
        print(f"Orientation: {self.currentOrientation}")
        print(
            f"list(data_unit.volume_nodes.values()) = {list(self.data_unit.volume_nodes.values())}"
        )

        # Apply the data unit's layout to our viewer
        self.data_unit.layout_handler.apply_layout()

        # Refresh the SegmentEditor Widget immediately
        self.segmentEditorWidget.refresh()

    def _save(self) -> None:
        err = self.bound_task.save()
        self.saveCompletePrompt(err)

    def saveCompletePrompt(self, err_msg: Optional[str]) -> None:
        if err_msg is None:
            msg = qt.QMessageBox()
            msg.setWindowTitle("Success!")

            # Get success message from the output manager
            success_message = self.bound_task.output_manager.get_success_message(
                self.bound_task.data_unit
            )
            msg.setText(success_message)

            msg.addButton(_("Confirm"), qt.QMessageBox.AcceptRole)
            msg.exec()
        else:
            errBox = qt.QErrorMessage()
            errBox.setWindowTitle("ERROR!")
            errBox.showMessage(err_msg)
            errBox.exec()

    ## GUI SYNCHRONIZATION ##
    def enter(self) -> None:
        # Ensure the segmentation editor widget it set up correctly
        if self.segmentEditorWidget:
            self.segmentEditorWidget.enter()

    def exit(self) -> None:
        # Ensure the segmentation editor widget handles itself before hiding
        if self.segmentEditorWidget:
            self.segmentEditorWidget.exit()


class MultiContrastSegmentationEvaluationTask(
    TaskBaseClass[MultiContrastSegmentationEvaluationDataUnit]
):
    def __init__(self, user: str):
        super().__init__(user)
        self.gui: Optional[MultiContrastSegmentationEvaluationGUI] = None
        self.output_mode: OutputMode = OutputMode.PARALLEL_DIRECTORY
        self.output_dir: Optional[Path] = None
        self.output_manager: Optional[MultiContrastOutputManager] = None
        self.data_unit: Optional[MultiContrastSegmentationEvaluationDataUnit] = None

    def setup(self, container: qt.QWidget) -> None:
        print(f"Running {self.__class__.__name__} setup!")
        self.gui = MultiContrastSegmentationEvaluationGUI(self)
        layout = self.gui.setup()
        container.setLayout(layout)
        if self.data_unit:
            self.gui.update(self.data_unit)
        self.gui.enter()

    def receive(self, data_unit: MultiContrastSegmentationEvaluationDataUnit) -> None:
        # Track the data unit for later
        self.data_unit = data_unit
        # Display primary volume + segmentation overlay
        slicer.util.setSliceViewerLayers(
            background=data_unit.primary_volume_node,
            foreground=data_unit.primary_segmentation_node,
            fit=True,
        )
        # If we have GUI, update it as well
        if self.gui:
            self.gui.update(data_unit)

    def cleanup(self) -> None:
        # Break the cyclical link with our GUI so garbage collection can run
        self.gui = None

    def _promptForSaveLocation(self) -> Optional[str]:
        """
        Prompt user for save location when original file doesn't exist.
        """
        prompt = qt.QFileDialog()
        prompt.setWindowTitle("Select Save Location")
        prompt.setAcceptMode(qt.QFileDialog.AcceptSave)
        prompt.setFileMode(qt.QFileDialog.AnyFile)
        prompt.setNameFilter("NIfTI files (*.nii.gz *.nii)")

        # Set default filename based on data unit
        default_name = f"{self.data_unit.uid}_seg.nii.gz"
        prompt.selectFile(default_name)

        if prompt.exec():
            selected_files = prompt.selectedFiles()
            if selected_files:
                save_path = Path(selected_files[0])
                try:
                    # Save directly to selected location
                    save_segmentation_to_nifti(
                        self.data_unit.primary_segmentation_node,
                        self.data_unit.primary_volume_node,
                        save_path,
                    )

                    # Also save sidecar if possible
                    sidecar_path = save_path.with_suffix(".json")
                    self._save_sidecar_to_path(sidecar_path)

                    return None  # Success
                except Exception as e:
                    return str(e)

        return "Save cancelled by user"

    def _save_sidecar_to_path(self, sidecar_path: Path):
        """Save sidecar file to a specific path."""
        sidecar_data = {}

        # Try to read existing sidecar from original location
        original_sidecar = self.data_unit.get_primary_segmentation_path().with_suffix(
            ".json"
        )
        if original_sidecar.exists():

            with open(original_sidecar) as fp:
                sidecar_data = json.load(fp)

        # Add new entry
        entry_time = datetime.now()
        new_entry = {
            "Name": "Segmentation Review [CART]",
            "Author": self.user,
            "Version": VERSION,
            "Date": entry_time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        generated_by = sidecar_data.get("GeneratedBy", [])
        generated_by.append(new_entry)
        sidecar_data["GeneratedBy"] = generated_by

        # Write sidecar
        with open(sidecar_path, "w") as fp:
            json.dump(sidecar_data, fp, indent=2)

    def can_save(self) -> bool:
        """
        Check whether we can save the current segmentation.
        """
        if self.output_manager:
            return self.output_manager.can_save(self.data_unit)
        return False

    def save(self) -> Optional[str]:
        """
        Save the current segmentation using the output manager.
        """
        if self.can_save():
            # Have the output manager save the result
            result = self.output_manager.save_segmentation(self.data_unit)
            # If we have a GUI, have it provide the appropriate response to the user
            if self.gui:
                self.gui.saveCompletePrompt(result)
            # Return the result for further use
            return result
        else:
            # Handle case where we need to prompt for file location
            if self.output_mode == OutputMode.OVERWRITE_ORIGINAL:
                if not self.data_unit.get_primary_segmentation_path().exists():
                    return self._promptForSaveLocation()
            return "Could not save!"

    def enter(self) -> None:
        if self.gui:
            self.gui.enter()

    def exit(self) -> None:
        if self.gui:
            self.gui.exit()

    @classmethod
    def getDataUnitFactories(cls) -> dict[str, DataUnitFactory]:
        """
        We currently only support one data unit type, so we only provide it to
         the user
        """
        return {"Segmentation": MultiContrastSegmentationEvaluationDataUnit}

    ## Utils ##
    def set_output_mode(
        self, mode: OutputMode, output_path: Optional[Path] = None
    ) -> Optional[str]:
        """
        Set the output mode and path if needed.
        Returns error message if failed, None if successful.
        """
        self.output_mode = mode

        if mode == OutputMode.PARALLEL_DIRECTORY:
            if not output_path:
                return "Output path required for parallel directory mode"

            # Validate the directory
            if not output_path.exists():
                return f"Error: Output path does not exist: {output_path}"

            if not output_path.is_dir():
                return f"Error: Output path is not a directory: {output_path}"

            # Set up the consolidated output manager
            self.output_dir = output_path
            self.output_manager = MultiContrastOutputManager(
                user=self.user, output_mode=mode, output_dir=output_path
            )
            print(f"Output mode set to parallel directory: {self.output_dir}")

        elif mode == OutputMode.OVERWRITE_ORIGINAL:
            # Set up the consolidated output manager
            self.output_dir = None
            self.output_manager = MultiContrastOutputManager(
                user=self.user, output_mode=mode
            )
            print("Output mode set to overwrite original")

        return None

    # Backward compatibility
    def set_output_dir(self, new_path: Path) -> Optional[str]:
        """
        Update the output directory (legacy method for backward compatibility).
        """
        return self.set_output_mode(OutputMode.PARALLEL_DIRECTORY, new_path)


class MultiContrastOutputManager:
    """
    Unified output manager that handles both parallel directory and overwrite original modes.
    """

    def __init__(
        self, user: str, output_mode: OutputMode, output_dir: Optional[Path] = None
    ):
        """
        Initialize the output manager.

        Args:
            user: Username for the author field in sidecar files
            output_mode: OutputMode enum value (PARALLEL_DIRECTORY or OVERWRITE_ORIGINAL)
            output_dir: Required for PARALLEL_DIRECTORY mode, ignored for OVERWRITE_ORIGINAL
        """
        self.user = user
        self.output_mode = output_mode
        self.output_dir = output_dir

        # Validate configuration
        if output_mode == OutputMode.PARALLEL_DIRECTORY and not output_dir:
            raise ValueError("output_dir is required for PARALLEL_DIRECTORY mode")

    def save_segmentation(
        self, data_unit: MultiContrastSegmentationEvaluationDataUnit
    ) -> Optional[str]:
        """
        Save segmentation according to the configured output mode.

        Returns:
            None if successful, error message string if failed
        """
        try:
            # Get output destinations based on mode
            segmentation_out, sidecar_out = self.get_output_destinations(data_unit)

            # Create directories if needed (only for parallel mode)
            if self.output_mode == OutputMode.PARALLEL_DIRECTORY:
                segmentation_out.parent.mkdir(parents=True, exist_ok=True)
                sidecar_out.parent.mkdir(parents=True, exist_ok=True)

            # Save the segmentation file
            self._save_segmentation(data_unit, segmentation_out)

            # Save/update the sidecar file
            self._save_sidecar(data_unit, sidecar_out)

            return None  # Success
        except Exception as e:
            return str(e)

    def get_output_destinations(
        self, data_unit: MultiContrastSegmentationEvaluationDataUnit
    ) -> tuple[Path, Path]:
        """
        Get output paths for segmentation and sidecar files based on the current mode.

        Returns:
            Tuple of (segmentation_path, sidecar_path)
        """
        if self.output_mode == OutputMode.PARALLEL_DIRECTORY:
            return self._get_parallel_destinations(data_unit)
        elif self.output_mode == OutputMode.OVERWRITE_ORIGINAL:
            return self._get_overwrite_destinations(data_unit)
        else:
            raise ValueError(f"Unknown output mode: {self.output_mode}")

    def _get_parallel_destinations(
        self, data_unit: MultiContrastSegmentationEvaluationDataUnit
    ) -> tuple[Path, Path]:
        """Get destinations for parallel directory mode."""
        # Define the target output directory
        target_dir = self.output_dir / f"{data_unit.uid}/anat/"

        # File name, before extensions
        fname = f"{data_unit.uid}_{self.user}_seg"

        # Define the target output file paths
        segmentation_out = target_dir / f"{fname}.nii.gz"
        sidecar_out = target_dir / f"{fname}.json"

        return segmentation_out, sidecar_out

    def _get_overwrite_destinations(
        self, data_unit: MultiContrastSegmentationEvaluationDataUnit
    ) -> tuple[Path, Path]:
        """Get destinations for overwrite original mode."""
        segmentation_path = data_unit.get_primary_segmentation_path()
        sidecar_path = segmentation_path.with_suffix(".json")
        return segmentation_path, sidecar_path

    @staticmethod
    def _save_segmentation(
        data_unit: MultiContrastSegmentationEvaluationDataUnit, target_file: Path
    ):
        """
        Save the data unit's segmentation to the designated output file.
        """
        # Extract the relevant node data from the data unit
        seg_node = data_unit.primary_segmentation_node
        vol_node = data_unit.primary_volume_node

        # Save the segmentation using the utility function
        save_segmentation_to_nifti(seg_node, vol_node, target_file)

    def _save_sidecar(
        self, data_unit: MultiContrastSegmentationEvaluationDataUnit, target_file: Path
    ):
        """
        Save or update the sidecar JSON file with processing metadata.
        """
        sidecar_data = {}

        # Try to read existing sidecar data
        if self.output_mode == OutputMode.OVERWRITE_ORIGINAL:
            # For overwrite mode, read from the target location if it exists
            if target_file.exists():
                with open(target_file) as fp:
                    sidecar_data = json.load(fp)
        else:
            # For parallel mode, read from the original location
            original_sidecar = self._get_original_sidecar_path(data_unit)
            if original_sidecar and original_sidecar.exists():
                with open(original_sidecar) as fp:
                    sidecar_data = json.load(fp)

        # Create new entry for this processing step
        entry_time = datetime.now()
        new_entry = {
            "Name": "Segmentation Review [CART]",
            "Author": self.user,
            "Version": VERSION,
            "Date": entry_time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        # Add the new entry to the GeneratedBy list
        generated_by = sidecar_data.get("GeneratedBy", [])
        generated_by.append(new_entry)
        sidecar_data["GeneratedBy"] = generated_by

        # Write the updated sidecar file
        with open(target_file, "w") as fp:
            json.dump(sidecar_data, fp, indent=2)

    def _get_original_sidecar_path(
        self, data_unit: MultiContrastSegmentationEvaluationDataUnit
    ) -> Optional[Path]:
        """
        Get the path to the original sidecar file for reading existing metadata.
        """
        # Get the base filename without extension from the segmentation path
        fname = str(data_unit.get_primary_segmentation_path()).split(".")[0]
        return Path(f"{fname}.json")

    def can_save(
        self, data_unit: Optional[MultiContrastSegmentationEvaluationDataUnit]
    ) -> bool:
        """
        Check whether we can save with the current configuration.

        Args:
            data_unit: The data unit to potentially save (can be None)

        Returns:
            True if saving is possible, False otherwise
        """
        if not data_unit:
            return False

        if self.output_mode == OutputMode.PARALLEL_DIRECTORY:
            return (
                self.output_dir
                and self.output_dir.exists()
                and self.output_dir.is_dir()
            )
        elif self.output_mode == OutputMode.OVERWRITE_ORIGINAL:
            return (
                True  # Can always attempt to overwrite (file will be created if needed)
            )

        return False

    def get_success_message(
        self, data_unit: MultiContrastSegmentationEvaluationDataUnit
    ) -> str:
        """
        Get an appropriate success message based on the output mode.
        """
        if self.output_mode == OutputMode.PARALLEL_DIRECTORY:
            seg_out, _ = self.get_output_destinations(data_unit)
            return f"Segmentation '{data_unit.uid}' saved to:\n{seg_out.resolve()}"
        else:
            return f"Segmentation '{data_unit.uid}' saved over original file."
