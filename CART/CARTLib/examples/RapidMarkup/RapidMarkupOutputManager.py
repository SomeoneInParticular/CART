import csv
from datetime import datetime
from pathlib import Path
from typing import Optional

from CARTLib.utils.config import ProfileConfig
from CARTLib.utils.data import save_markups_to_json

from RapidMarkupUnit import RapidMarkupUnit

VERSION = "0.0.1"


class RapidMarkupOutputManager:

    UID_KEY = "uid"
    PROFILE_KEY = "profile"
    TIMESTAMP_KEY = "timestamp"
    OUTPUT_KEY = "output_path"
    VERSION_KEY = "version"

    LOG_HEADERS = [
        UID_KEY,
        PROFILE_KEY,
        TIMESTAMP_KEY,
        OUTPUT_KEY,
        VERSION_KEY
    ]

    def __init__(
        self,
        profile: ProfileConfig,
        output_dir: Path
    ):
        """
        Initialize the output manager.

        :param profile: The configuration for the current profile
        :param output_dir: Root path where all output should be placed
        """
        if not output_dir:
            raise ValueError("Cannot create a OutputManager without an output directory!")

        self.profile = profile
        self.output_dir = output_dir

        # CSV logging parameters
        self._csv_log_file: Optional[Path] = None
        self._csv_log: Optional[dict[tuple[str, str], dict[str, str]]] = None

        # Markup output path
        self._markup_output_dir: Optional[Path] = None

    ## PROPERTIES ##
    @property
    def profile_label(self) -> str:
        # Simple alias to sidestep a common argument chain
        return self.profile.label

    @property
    def csv_log_file(self) -> Path:
        """
        This is a property for two reasons:
         * Ensures that it cannot be re-written post-initialization, and
         * Ensure the folders on the filesystem are only created once,
           the first time they're needed
        """
        # If we don't have a path yet, determine where it should be
        if self._csv_log_file is None:
            # The log is just placed within the output directory
            csv_path = self.output_dir / f"cart_markup.csv"
            self._csv_log_file = csv_path
        return self._csv_log_file

    @property
    def csv_log(self) -> dict[tuple[str, str], dict[str, str]]:
        """
        Same reasons as above; defer loading the data from the CSV until we
        need to
        """
        # If we already have contents loaded into memory, just use that
        if self._csv_log is not None:
            return self._csv_log

        # If not, initialize a blank CSV file
        self._csv_log = dict()

        # If a CSV file already exists, load it into memory
        if self.csv_log_file.exists():
            with open(self.csv_log_file) as fp:
                reader = csv.DictReader(fp)
                for i, row in enumerate(reader):
                    # Skip rows w/o a CSV
                    uid = row.get(self.UID_KEY, None)
                    if not uid:
                        print(f"Skipped entry #{i} in {self.csv_log_file}, as it lacks a UID")
                        continue
                    # Generate a UID + profile pair to act as our key
                    profile = row.get(self.PROFILE_KEY, None)
                    self._csv_log[(uid, profile)] = row

        return self._csv_log

    @property
    def markup_output_dir(self) -> Path:
        # If we don't have an output for our markups yet, create one
        if self._markup_output_dir is None:
            # Determine the path and create the requisite folders
            self._markup_output_dir = self.output_dir / self.profile_label
            self._markup_output_dir.mkdir(parents=True, exist_ok=True)
        return self._markup_output_dir

    ## I/O ##
    def save_markups(self, data_unit: RapidMarkupUnit) -> str:
        # Get the markup node from the data unit
        markup_node = data_unit.markup_node

        # Save it to the Slicer JSON format
        markup_output_file = self.markup_output_dir / f"{data_unit.uid}.mrk.json"
        save_markups_to_json(markup_node, markup_output_file)

        # Add/replace the entry in our CSV log with one representing this file
        new_entry_key = (data_unit.uid, self.profile_label)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.csv_log[new_entry_key] = {
            self.UID_KEY: data_unit.uid,
            self.PROFILE_KEY: self.profile_label,
            self.TIMESTAMP_KEY: timestamp,
            self.OUTPUT_KEY: str(self.output_dir.resolve()),
            self.VERSION_KEY: VERSION
        }

        # Save the new contents to file
        with open(self.csv_log_file, "w") as fp:
            writer = csv.DictWriter(fp, fieldnames=self.LOG_HEADERS)
            writer.writeheader()
            writer.writerows(self.csv_log.values())

        # Return a success message
        result_msg = (
            f"Markups saved to {str(markup_output_file.resolve())}."
            f"\n\n"
            f"Status logged to {str(self.csv_log_file.resolve())}."
        )
        return result_msg
