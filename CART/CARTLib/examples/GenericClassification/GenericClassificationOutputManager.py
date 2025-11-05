import csv
from datetime import datetime
from functools import cached_property
from pathlib import Path

from CARTLib.utils.config import ProfileConfig

from GenericClassificationUnit import GenericClassificationUnit


VERSION = 0.01


class GenericClassificationOutputManager:

    UID_KEY = "uid"
    PROFILE_KEY = "profile"
    TIMESTAMP_KEY = "timestamp"
    VERSION_KEY = "version"
    CLASSES_KEY = "classifications"

    LOG_HEADERS = [
        UID_KEY,
        PROFILE_KEY,
        TIMESTAMP_KEY,
        VERSION_KEY,
        CLASSES_KEY
    ]

    def __init__(
        self,
        config: ProfileConfig,
        output_dir: Path
    ):
        # We must have an output dir to work with
        if not output_dir:
            raise ValueError("Cannot place output in a non-existent path!")

        # Core attributes
        self.config = config
        self.output_dir = output_dir

    @property
    def profile_config(self) -> ProfileConfig:
        """
        Wrapper for accessing the parent (profile) config; allows us to
        suppress the "incorrect type" warning once, rather than everywhere
        this is needed.
        """
        # TODO: Make a config stuff
        return self.config

    @property
    def profile_label(self) -> str:
        # Simple alias to sidestep a common argument chain
        return self.profile_config.label

    @property
    def csv_data_file(self) -> Path:
        """
        Where the CSV log should be saved too.

        Read-only, as it's tightly associated with the output directory.
        """
        return self.output_dir / f"cart_classifications.csv"

    @cached_property
    def csv_data(self) -> dict[tuple[str, str], dict]:
        """
        Cached contents of the CSV data file currently monitored by this
        output manager.

        Cached and loaded lazily to prevent each and every change
        in the output directory from creating files all over the place
        (or, worse, loading large CSV logs immediately every single time)
        """
        # Initialize a blank CSV dict
        csv_data = dict()

        # If a CSV data file already exists, try to load its contents
        if self.csv_data_file.exists():
            with open(self.csv_data_file) as fp:
                reader = csv.DictReader(fp)
                for i, row in enumerate(reader):
                    # Skip rows w/o a valid UID entry
                    uid = row.get(self.UID_KEY, None)
                    if not uid:
                        print(f"Skipped entry #{i} in {self.csv_data_file}, as it lacks a UID.")
                        continue
                    # Skip rows w/o a valid profile label
                    uid = row.get(self.PROFILE_KEY, None)
                    if not uid:
                        print(f"Skipped entry #{i} in {self.csv_data_file}, as it lacks a Profile ID.")
                        continue
                    # Generate a UID + profile pair to act as our key
                    profile = row.get(self.PROFILE_KEY, None)
                    # Insert it into the data dict
                    csv_data[(uid, profile)] = row

        # Return the resulting data
        return csv_data

    def save_unit(self, data_unit: GenericClassificationUnit):
        # Generate the entry key and timestamp
        entry_key = (data_unit.uid, "test")

        # Add/replace the corresponding entry in our data dict
        self.csv_data[entry_key] = {
            self.UID_KEY: data_unit.uid,
            self.PROFILE_KEY: "test",
            self.TIMESTAMP_KEY: datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            self.VERSION_KEY: VERSION,
            self.CLASSES_KEY: data_unit.classes
        }

        # Save the results to file
        with open(self.csv_data_file, "w") as fp:
            writer = csv.DictWriter(fp, fieldnames=self.LOG_HEADERS)
            writer.writeheader()
            writer.writerows(self.csv_data.values())

        # Return a success message
        result_msg = (
            f"Classifications saved to {str(self.csv_data_file.resolve())}."
        )
        return result_msg
