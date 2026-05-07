import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

import numpy as np
import slicer.util

from CARTLib.utils.config import JobProfileConfig, MasterProfileConfig
from CARTLib.utils.data import (
    save_segmentation_to_nifti,
    save_json_sidecar,
    load_json_sidecar,
    find_json_sidecar_path,
)

from SegmentationConfig import SegmentationConfig, SegmentationFileFormat
from SegmentationUnit import (
    SegmentationUnit,
    ReferenceSegmentationResource,
    EditableSegmentationResource,
)

if TYPE_CHECKING:
    # Avoid a cyclic reference
    from SegmentationConfig import SegmentationConfig, SegmentationFileFormat

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
                nifti_path = self._generate_output_paths_for(uid, seg_name)
                if not nifti_path.exists():
                    return False
                # If it's a NIfTI file, check for the sidecar as well
                if self.task_config.file_format == SegmentationFileFormat.NIFTI:
                    json_path = find_json_sidecar_path(nifti_path)
                    if not json_path.exists():
                        return False

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
            nifti_path = self._generate_output_paths_for(uid, seg_name)
            if not nifti_path.is_file():
                continue
            # Track the file within the dictionary
            segment_key = EditableSegmentationResource.format_for_csv(seg_name)
            segmentation_paths[segment_key] = nifti_path

        return segmentation_paths

    def _generate_output_paths_for(self, uid: str, seg_name: str):
        # TODO: Allow user-configurable file structure

        # Determine the output file destinations
        stem_path = self.job_config.output_path / uid
        file_name = f"{uid}_{seg_name}"

        # Define the NIfTI file paths
        if self.task_config.file_format == SegmentationFileFormat.NIFTI:
            output_path = stem_path / f"{file_name}.nii.gz"
        elif self.task_config.file_format == SegmentationFileFormat.NRRD:
            output_path = stem_path / f"{file_name}.nrrd"
        else:
            raise ValueError("Invalid output format detected for the Segmentation Task!")

        return output_path

    def save_unit(self, unit: SegmentationUnit):
        # Save each segmentation that was marked as "to-edit" during Job config
        saved_records = list()
        failed_records = list()
        exceptions = list()
        for segmentation_id, segmentation_node in unit.segmentation_nodes.items():
            # If this segmentation is "view-only", skip it
            if ReferenceSegmentationResource.is_type(segmentation_id):
                continue

            # If we're not saving blanks, check if this segmentation is blank
            if not self.task_config.save_blank_segmentations:
                # Iterate through each segment in turn
                segmentation = segmentation_node.GetSegmentation()
                for segment_id in segmentation.GetSegmentIDs():
                    try:
                        # If any segment has a non-zero value, break to skip the "else" below.
                        arr = slicer.util.arrayFromSegmentInternalBinaryLabelmap(segmentation_node, segment_id)
                        if np.count_nonzero(arr) > 0:
                            break
                    except AttributeError:
                        # When there is no label map in the segment, its either corrupt or lacks any segments.
                        continue
                else:
                    # If no segments had a non-zero value, skip the segmentation
                    logging.info(
                        f"Skipped segmentation {segmentation_node.GetName()}, as it was blank."
                    )
                    continue

            # Try to save this segmentation
            segmentation_name = EditableSegmentationResource.get_short_name(segmentation_id)
            try:
                self._save_segmentation(segmentation_node, unit, segmentation_name)
                saved_records.append(segmentation_name)
            except Exception as e:
                failed_records.append(segmentation_name)
                exceptions.append(e)
        # Create a new log entry detailing these changes
        log_entry = {
            self.UID_KEY: unit.uid,
            self.AUTHOR_KEY: self.master_config.author,
            self.TIMESTAMP_KEY: datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            self.SAVED_KEY: ", ".join(saved_records),
            self.FAILED_KEY: ", ".join(failed_records),
            self.VERSION_KEY: VERSION,
        }
        self.log_data[unit.uid] = log_entry
        # Save the updated log data to file
        with open(self.log_path, mode='w') as fp:
            writer = csv.DictWriter(fp, fieldnames=self.HEADERS, delimiter='\t')
            writer.writeheader()
            writer.writerows(self.log_data.values())

        # If we had any errors, log a message and raise the first
        no_exceptions = len(exceptions)
        if no_exceptions > 0:
            logging.error(
                f"While saving a the segmentations for data unit '{unit.uid}', "
                f"{no_exceptions} error(s) occurred! "
                f"See the critical stack trace for details "
                f"on the first of these.")
            raise exceptions[0]

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
        # Determine the output file destinations
        output_path = self._generate_output_paths_for(unit.uid, seg_name)

        # Save everything
        if self.task_config.file_format == SegmentationFileFormat.NIFTI:
            # Only generate + update the sidecar if the output is NIfTI
            sidecar_data = dict()

            # Load the previous sidecar's contents as a "basis"
            storage_node = seg_node.GetStorageNode()
            if storage_node is not None:
                prior_path = Path(storage_node.GetFileName())
                sidecar_data = load_json_sidecar(prior_path)

            # Update its relevant contents
            generated_by = sidecar_data.get("GeneratedBy", [])
            generated_by.append(
                {
                    "Name": f"CART Segmentation Task [{self.job_config.name}]",
                    "Version": VERSION,
                    "Author": self.master_config.author,
                    "Position": self.master_config.position,
                    "Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
            sidecar_data["GeneratedBy"] = generated_by

            # Save everything
            save_segmentation_to_nifti(
                seg_node, unit.reference_volume_node, output_path
            )
            save_json_sidecar(output_path, sidecar_data)
        else:
            # Delegate to Slicer for our other formats
            slicer.util.saveNode(seg_node, str(output_path))

        # Report the output path for upstream use
        return output_path.resolve()
