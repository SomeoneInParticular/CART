import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

import slicer.util

from CARTLib.utils.config import JobProfileConfig, MasterProfileConfig
from CARTLib.utils.data import (
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
    UID_KEY = "uid"
    AUTHOR_KEY = "author"
    TIMESTAMP_KEY = "timestamp"
    INPUT_SEGMENTATION_KEY = "original_segmentation_path"
    SEGMENTATION_PATH_KEY = "segmentation_path"
    SIDECAR_PATH_KEY = "sidecar_path"
    VERSION_KEY = "version"

    HEADERS = [
        UID_KEY,
        AUTHOR_KEY,
        TIMESTAMP_KEY,
        SEGMENTATION_PATH_KEY,
        SIDECAR_PATH_KEY,
        INPUT_SEGMENTATION_KEY,
        VERSION_KEY,
    ]

    ## OUTPUT PARSING CONSTANTS ##
    UID_PLACEHOLDER = "%u"
    NAME_PLACEHOLDER = "%n"
    FULLNAME_PLACEHOLDER = "%N"
    JOBNAME_PLACEHOLDER = "%j"
    FILENAME_PLACEHOLDER = "%f"

    REPLACEMENT_MAP_DESCRIPTIONS = {
        UID_PLACEHOLDER: "The UID of the case, as specified in the Cohort file.",
        NAME_PLACEHOLDER: "The name of the segmentation, stripped of any 'Segmentation_' prefix.",
        FULLNAME_PLACEHOLDER: "The name of the segmentation, with 'Segmentation_' prefixes retained.",
        JOBNAME_PLACEHOLDER: "The name of the job, as defined during the job's initial creation.",
        FILENAME_PLACEHOLDER: "The original filename (without its extensions). Only valid for segmentations loaded from a file.",
    }

    @classmethod
    def build_placeholder_map(
        cls,
        uid: str = "sub-abc123",
        segmentation_name: str = "Segmentation_Example",
        job_name: str = "Job_Name",
        file_name: str = None,
    ) -> dict[str, str]:
        short_name = segmentation_name
        if short_name.lower().startswith("segmentation_"):
            short_name = short_name[13:]

        placeholder_map = {
            cls.UID_PLACEHOLDER: uid,
            cls.NAME_PLACEHOLDER: short_name,
            cls.FULLNAME_PLACEHOLDER: segmentation_name,
            cls.JOBNAME_PLACEHOLDER: job_name,
        }
        if file_name is not None:
            placeholder_map[cls.FILENAME_PLACEHOLDER] = file_name.split('.')[0]
        return placeholder_map

    @classmethod
    def format_output_str(
        cls,
        output_str: str,
        placeholder_map: dict[str, str],
        output_path: Path = Path("..."),
    ) -> Optional[str]:
        # Empty strings, and strings with trailing slashes, are invalid
        if len(output_str) < 1 or (output_str[-1] in {"/", "\\"}):
            return None

        # Format the string
        formatted_str = output_str
        for k, v in placeholder_map.items():
            formatted_str = formatted_str.replace(k, v)

        # Prepend the "output_path" if this isn't an absolute path
        if Path(formatted_str).is_absolute():
            return formatted_str
        else:
            return str(output_path / formatted_str)

    def __init__(self, master_config: MasterProfileConfig, job_config: JobProfileConfig, task_config: "SegmentationConfig"):
        self.master_config: MasterProfileConfig = master_config
        self.job_config: JobProfileConfig = job_config
        self.task_config: "SegmentationConfig" = task_config

        # Map of previous CSV log entries
        self._log_data: Optional[dict[tuple[str, str], dict[str, str]]] = None

    @property
    def log_path(self) -> Path:
        return self.job_config.output_path / f"{self.job_config.name}_log.csv"

    @property
    def log_data(self) -> Optional[dict[tuple[str, str], dict[str, str]]]:
        """
        The data currently stored within the CSV-based log file

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

        # If the CSV file already exists, load its contents
        if self.log_path.exists():
            with open(self.csv_log_path, newline="") as csvfile:
                reader = csv.DictReader(csvfile)
                for i, row in enumerate(reader):
                    # Confirm the row has a UID; if not, skip it
                    uid = row.get(self.UID_KEY, None)
                    if uid is None:
                        logging.warning(
                            f"Skipping entry #{i} in {self.csv_log_path}, lacked a valid UID."
                        )
                        continue
                    # Likewise, skip entries without an author
                    author = row.get(self.AUTHOR_KEY, None)
                    if author is None:
                        logging.warning(
                            f"Skipping entry #{i} in {self.csv_log_path}, lacked a valid author."
                        )
                        continue
                    # Update CSV log dictionary
                    log_data[(uid, author)] = row

        # Track and return the result
        self._log_data = log_data
        return log_data

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
                result = self._save_segmentation(seg_node, unit, seg_id)
                saved[seg_id] = str(result)
            except Exception as e:
                failed[seg_id] = str(e)
        return saved, failed

    def _save_segmentation(
        self,
        seg_node: "slicer.vtkMRMLSegmentationNode",
        unit: SegmentationUnit,
        seg_id: str,
    ) -> Path:
        """
        Save the specified segmentation node, referencing the given data
        unit and segmentation ID to fill in the resulting files w/ additional
        details.

        :param seg_node: The segmentation node that should be saved
        :param unit: The data unit the segmentation node is part of
        :param seg_id: The identifier used by the segmentation within the data unit
        :return: The output path of the MAIN (.nii.gz) saved file
        :raises ValueError: If the values provided would result in a corrupted save file.
        """
        # Get the "final" name for this segmentation
        seg_name = EditableSegmentationResource.get_short_name(seg_id)

        # TODO: Toggle skipping blank segmentations

        # Determine the output file destinations
        stem_path = self.job_config.output_path / unit.uid
        file_name = f"{unit.uid}_{seg_name}"

        # TODO: Allow user-customizable file format
        seg_out_path = stem_path / f"{file_name}.nii.gz"

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
        json_path = stem_path / f"{file_name}.json"

        # Save everything and report
        save_segmentation_to_nifti(seg_node, unit.primary_volume_node, seg_out_path)
        save_json_sidecar(json_path, sidecar_data)
        return seg_out_path.resolve()
