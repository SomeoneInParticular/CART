from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from typing import Optional, List, Dict

from .DataUnitBase import DataUnitBase
# TODO: Remove this for a configurable method
from ..VolumeOnlyDataIO import VolumeOnlyDataUnit


class DataManager:
    """
    Manages a CSV-based cohort and provides a cache of DataUnit objects for
      efficient forward/backward traversal.

    # TODO: Implement way to indicate if a whole list was traversed.

    Attributes:
        cohort_csv: Path to the cohort CSV file currently selected.
        case_data: List of row dictionaries loaded from CSV.
        cache_size: Maximum number of Data Unit objects held in memory at once.
    """

    def __init__(
        self,
        cohort_file: Optional[Path] = None,
        data_source: Optional[Path] = None,
        cache_size: int = 2
    ):
        """
        Initialize DataManager with optional configuration and window size.

        We employ limited caching to help streamline the task process; namely,
          the most recently used Data Units are kept in memory until they fall
          out of scope, allowing the user to return to them without needing to
          load their data from file again.

        # TODO Add pre-fetching as well.
        """
        # The cohort data, and the file from which it was pulled
        self.cohort_csv: Path = cohort_file
        self.data_source: Path = data_source
        self.case_data: List[Dict[str, str]] = []

        # Current index in the
        self.current_case_index: int = 0

        # Dynamically sized cached version of "_get_data_unit"
        lru_cache_wrapper = lru_cache(maxsize=cache_size)
        old_method = self._get_data_unit
        self._get_data_unit = lru_cache_wrapper(old_method)

    def get_cache_size(self):
        return self._get_data_unit.cache_info().maxsize

    def set_data_source(self, source: Path):
        # TODO: Validate the input before running
        self.data_source = source

        # Clear our cache, as its almost certainly no longer valid
        self._get_data_unit.cache_clear()

        # Reset to the beginning, as everything is
        self.current_case_index = 0

        # Begin re-building the pre-fetch cache, if it exists
        self._pre_fetch_elements()

        # TODO: Notify the Task that this has been updated as well somehow.

    def get_data_source(self):
        return self.data_source

    def load_cases(self) -> None:
        """
        Load the cases designated in a cohort CSV into memory, ready to be used
          to generate DataUnit instances.

        Raises:
            ValueError: If no path is provided/configured, or if CSV is invalid.
        """
        # Notify the user we're loading data
        print(f"Loading cohort from '{self.cohort_csv}'")

        # If no path is present, raise an error
        if self.cohort_csv is None:
            raise ValueError("No CSV has been given to load data from.")

        # Try to read the data
        rows = DataManager._read_csv(self.cohort_csv)

        # If we succeeded, update everything to match and reset the queue
        self.case_data = rows
        self.current_case_index = 0  # Start at beginning
        print(f"Loaded {len(rows)} rows!")

    def _get_data_unit(self, idx: int):
        """
        Gets the current DataUnit at our index. This method implicitly caches
         and does NOT update the state of the DataManager!

        Unless you know what you're doing, you should use `select_unit_at`
         instead!
        """
        current_case_data = self.case_data[idx]
        # TODO: replace this with a user-selectable data unit type
        return VolumeOnlyDataUnit(
            case_data=current_case_data,
            data_path=self.data_source
        )

    def current_uid(self):
        return self.case_data[self.current_case_index]['uid']

    def current_case(self):
        """
        Return the case information for the current index
        """
        return self.case_data[self.current_case_index]

    def current_data_unit(self) -> DataUnitBase:
        """
        Return the current DataUnit in the queue without changing the index.
        """
        return self._get_data_unit(self.current_case_index)

    def select_current_unit(self):
        """
        Selects the current data unit again, bringing it into focus if it was
         not already
        """
        current_unit = self._get_data_unit(self.current_case_index)
        current_unit.focus_gained()

        return current_unit

    def has_next_case(self) -> bool:
        return self.current_case_index+1 < len(self.case_data)

    def has_previous_case(self) -> bool:
        return self.current_case_index > 0

    def select_unit_at(self, idx: int) -> DataUnitBase:
        """
        Update the current selection index + loaded data unit. This involves:

        * Revoking focus to the previously selected data unit
        * Granting focus to the new data unit
        * Updating our currently selected index

        In that order; how the first steps are managed depends on the DataUnit's
         specific implementation.
        """
        # Check that the new index is valid before proceeding
        if idx < 0:
            raise ValueError("Index cannot be less than 0.")
        elif idx >= len(self.case_data):
            raise ValueError("Index cannot be greater than the number of loaded cases.")

        # Keep tabs on the prior data unit for later
        prior_unit = self.current_data_unit()

        # Attempt to grab the next data unit
        new_unit = self._get_data_unit(idx)

        # Try to transfer focus from one unit to the other
        if prior_unit:
            prior_unit.focus_lost()
        new_unit.focus_gained()

        # Set the current index to that of the new unit
        self.current_case_index = idx

        # Return the new unit
        return new_unit

    def next(self) -> DataUnitBase:
        """
        Advance to the next case, and get its corresponding DataUnit.

        :return: The previous data unit; None if it doesn't exist/is invalid
        """
        new_index = self.current_case_index + 1
        return self.select_unit_at(new_index)

    def previous(self) -> DataUnitBase:
        """
        Advance to the next case, and get its corresponding DataUnit.

        :return: The previous data unit; None if it doesn't exist/is invalid
        """
        new_index = self.current_case_index - 1
        return self.select_unit_at(new_index)
    
    @staticmethod
    def _read_csv(csv_path: Path) -> List[Dict[str, str]]:
        """
        Reads the contents of the CSV into a list of str->str dictionaries
        """
        with csv_path.open(newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            if reader.fieldnames is None:
                raise ValueError("CSV file has no header row")
            return list(reader)

    # TODO Change rows to rows and define row typing at the definition of rows
    @staticmethod
    def _validate_columns(rows: List[Dict[str, str]]) -> None:
        if not rows:
            raise ValueError("CSV file contains no data rows")
        cols = rows[0].keys()
        if 'uid' not in cols:
            raise ValueError("CSV must contain 'uid' column")
        if len(cols) < 2:
            raise ValueError(
                "CSV must contain at least one resource column besides 'uid'"
            )

    @staticmethod
    def _validate_unique_uids(rows: List[Dict[str, str]]) -> None:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for row in rows:
            uid = row['uid']
            if uid in seen:
                duplicates.add(uid)
            seen.add(uid)
        if duplicates:
            raise ValueError(f"Duplicate uid values found in file: {duplicates}")

    def _pre_fetch_elements(self):
        """
        Rebuild the cache of pre-fetched DataUnits.

        Run via `async` in the background, allowing the user to continue
          completing their tasks while pre-fetching is run.
        """
        # TODO
        pass
