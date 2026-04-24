import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

import slicer.util

from CARTLib.utils.config import JobProfileConfig, MasterProfileConfig
from CARTLib.utils.data import (
    load_segmentation,
    save_segmentation_to_nifti,
    save_json_sidecar,
)

from SegmentationUnit import (
    SegmentationUnit,
    ReferenceSegmentationResource,
    EditableSegmentationResource,
)

if TYPE_CHECKING:
    # Avoid a cyclic reference
    from SegmentationConfig import SegmentationConfig

VERSION = 0.04


class SegmentationIO:
    """
    Managed saving (and, if requested, loading) segmentation files for the
    Segmentation task
    """

    ## LOGGING CONSTANTS ##
    # Key Columns
    UID_KEY = "uid"
    SEG_KEY = "segmentation_name"
    # Value Columns
    AUTHOR_KEY = "author"
    TIMESTAMP_KEY = "timestamp"
    SAVED_KEY = "saved_segmentations"
    FAILED_KEY = "failed_segmentations"
    VERSION_KEY = "version"

    HEADERS = [
        UID_KEY,
        AUTHOR_KEY,
        TIMESTAMP_KEY,
        SAVED_KEY,
        FAILED_KEY,
        VERSION_KEY,
    ]

    ## Constructor ##
    def __init__(self, master_config: MasterProfileConfig, job_config: JobProfileConfig, task_config: "SegmentationConfig"):
        self.master_config: MasterProfileConfig = master_config
        self.job_config: JobProfileConfig = job_config
        self.task_config: "SegmentationConfig" = task_config

        # Map of previous CSV log entries
        self._log_data: Optional[dict[str, dict[str, str]]] = None

    ## Log Management ##
    @property
    def log_path(self) -> Path:
        """
        Path to where the logs for this owning IO's Job should be saved.

        Returns a TSV file which may or may not exist yet!
        """
        return self.job_config.output_path / f"{self.job_config.name}_log.tsv"

    @property
    def log_data(self) -> Optional[dict[str, dict[str, str]]]:
        """
        The data currently stored within the TSV-based log file

        Get-only, as the log file and its contents are tightly bound to
        the output directory.
        """

        # If the data has already been cached, use it instead
        if self._log_data is not None:
            return self._log_data

        # If there's no CSV log path to load, do nothing
        if self.log_path is None:
            return None

        # Otherwise, try to (re-)build the CSV log
        log_data = dict()
        self._log_data = log_data

        # If there's not existing TSV file to pull from, end here
        if not self.log_path.exists():
            return log_data

        # If the CSV file already exists, load its contents
        with open(self.log_path, newline="") as csvfile:
            reader = csv.DictReader(csvfile, delimiter='\t')
            for i, row in enumerate(reader):
                # Confirm the row has a UID; if not, skip it
                uid = row.get(self.UID_KEY, None)
                if uid is None:
                    logging.warning(
                        f"Skipping entry #{i} in {self.log_path}, lacked a valid UID."
                    )
                    continue
                # Update CSV log dictionary
                log_data[uid] = row

        # Track and return the result
        self._log_data = log_data
        return log_data

    ## Save/Load Management ##
    def is_case_done(self, uid: str):
        """
        Check whether the expected output files for the given case
        UID exist or not.
        """
        # If our log file doesn't have an entry, return None
        log_entry = self.log_data.get(uid)
        if log_entry is None:
            return None

        # Check if there were any failures last time
        failed_keys = log_entry.get(self.FAILED_KEY)
        if failed_keys != '':
            failed_keys = failed_keys.split(", ")
            if len(failed_keys) > 0:
                return False

        # Iterate through the saved keys and confirm they're there
        saved_keys = log_entry.get(self.SAVED_KEY)
        if saved_keys != "":
            for seg_id in saved_keys.split(", "):
                # Get the "final" name for this segmentation
                seg_name = EditableSegmentationResource.get_short_name(seg_id)
                nifti_path, json_path = self._generate_output_paths_for(uid, seg_name)
                if not nifti_path.exists() or not json_path.exists():
                    return False

        # TODO: Also check the case contents for missing files as a fallback
        return True

    def get_saved_segmentation_paths(self, uid: str):
        """
        Get the case name -> output path map for this case
        """
        unit_data = self.log_data.get(uid, {})
        saved_keys = unit_data.get(self.SAVED_KEY, '')

        if saved_keys == '':
            return {}

        # Iteratively find each segment within the path
        segmentation_paths = {}
        for seg_name in saved_keys.split(", "):
            # Find where the file should be, skipping it if one does not exist
            nifti_file, __ = self._generate_output_paths_for(uid, seg_name)
            if not nifti_file.is_file():
                continue
            # Track the file within the dictionary
            segment_key = EditableSegmentationResource.format_for_csv(seg_name)
            segmentation_paths[segment_key] = nifti_file

        return segmentation_paths

    def _generate_output_paths_for(self, uid: str, seg_name: str):
        # TODO: Allow user-configurable file structure/format

        # Determine the output file destinations
        stem_path = self.job_config.output_path / uid
        file_name = f"{uid}_{seg_name}"

        # Define the NIfTI + JSON file paths
        nifti_path = stem_path / f"{file_name}.nii.gz"
        json_path = stem_path / f"{file_name}.json"

        return nifti_path, json_path

    def save_unit(self, unit: SegmentationUnit):
        # Save each segmentation that was marked as "to-edit" during Job config
        saved = dict()  # Name: Destination Path
        failed = dict()  # Name: Reason
        for seg_id, seg_node in unit.segmentation_nodes.items():
            # If this segmentation is "view-only", skip it
            if ReferenceSegmentationResource.is_type(seg_id):
                continue

            # Try to save this segmentation
            try:
                seg_name = EditableSegmentationResource.get_short_name(seg_id)
                result = self._save_segmentation(seg_node, unit, seg_name)
                saved[seg_name] = str(result)
            except Exception as e:
                failed[seg_id] = str(e)
        # Create a new log entry detailing these changes
        log_entry = {
            self.UID_KEY: unit.uid,
            self.AUTHOR_KEY: self.master_config.author,
            self.TIMESTAMP_KEY: datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            self.SAVED_KEY: ", ".join(saved.keys()),
            self.FAILED_KEY: ", ".join(failed.keys()),
            self.VERSION_KEY: VERSION,
        }
        self.log_data[unit.uid] = log_entry
        # Save the updated log data to file
        with open(self.log_path, mode='w') as fp:
            writer = csv.DictWriter(fp, fieldnames=self.HEADERS, delimiter='\t')
            writer.writeheader()
            writer.writerows(self.log_data.values())
        # Return the result for upstream use
        return saved, failed

    def _save_segmentation(
        self,
        seg_node: "slicer.vtkMRMLSegmentationNode",
        unit: SegmentationUnit,
        seg_name: str,
    ) -> Path:
        """
        Save the specified segmentation node, referencing the given data
        unit and segmentation ID to fill in the resulting files w/ additional
        details.

        :param seg_node: The segmentation node that should be saved
        :param unit: The data unit the segmentation node is part of
        :param seg_name: The identifier used by the segmentation within the data unit
        :return: The output path of the MAIN (.nii.gz) saved file
        :raises ValueError: If the values provided would result in a corrupted save file.
        """
        # TODO: Allow users to "skip" blank segmentations

        # Determine the output file destinations
        nifti_path, json_path = self._generate_output_paths_for(unit.uid, seg_name)

        # Build the corresponding sidecar
        # TODO: Only create this if outputting to BIDS-like format
        sidecar_data = {
            "SpatialReference": "orig",
            "GeneratedBy": [
                {
                    "Name": f"CART Segmentation Task [{self.job_config.name}]",
                    "Version": VERSION,
                    "Author": self.master_config.author,
                    "Position": self.master_config.position,
                    "Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            ],
        }

        # Save everything
        save_segmentation_to_nifti(seg_node, unit.primary_volume_node, nifti_path)
        save_json_sidecar(json_path, sidecar_data)

        # Report the output path for upstream use
        return nifti_path.resolve()
