import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from CARTLib.examples.MultiContrastSegmentation.MultiContrastSegmentationEvaluationDataUnit import (
    MultiContrastSegmentationEvaluationDataUnit,
)
from CARTLib.utils.data import save_segmentation_to_nifti

VERSION = 0.01


class OutputMode(Enum):
    PARALLEL_DIRECTORY = "parallel"
    OVERWRITE_ORIGINAL = "overwrite"


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
