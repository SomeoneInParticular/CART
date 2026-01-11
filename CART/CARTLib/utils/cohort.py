import json
from pathlib import Path
from typing import Optional, TYPE_CHECKING

import numpy as np
from numpy import typing as npt

import qt
from CARTLib.utils.widgets import CSVBackedTableModel, CSVBackedTableWidget
from slicer.i18n import tr as _


if TYPE_CHECKING:
    # NOTE: this isn't perfect (this only exposes Widgets, and Slicer's QT impl
    # isn't the same as PyQT5 itself), but it's a LOT better than constant
    # cross-referencing
    import PyQt5.Qt as qt


## Core ##
class Cohort:
    def __init__(self, csv_path: Path, data_path: Path, use_sidecar: bool = True):
        # Tracker for the model tracking the CSV data
        self._model: CohortTableModel = CohortTableModel(csv_path)

        # Track the data path for later
        self.data_path = data_path

        # JSON sidecar management
        self.save_sidecar = use_sidecar
        if use_sidecar:
            self.load_sidecar()
        else:
            # If no sidecar is to be used, generate blank cohort/filter entries
            self._search_paths: dict[str, list[Path]] = dict()
            self._filters: dict[str, list[str]] = dict()

    ## Attributes/Properties ##
    @property
    def model(self) -> "CohortTableModel":
        # Get-only to avoid desync
        return self._model

    @property
    def csv_path(self) -> Path:
        return self._model.csv_path

    @csv_path.setter
    def csv_path(self, new_path: Path):
        self._model.csv_path = new_path
        # Reset the filter data as well
        self.load_sidecar()

    @property
    def sidecar_path(self) -> Path:
        # Get-only to avoid desync
        return self.csv_path.with_stem(".json")

    @property
    def search_paths(self) -> dict[str, list[Path]]:
        """
        Search paths to
        """
        # Get-only; use the add/remove functions instead, or edit the returned dict directly
        return self._search_paths

    def reset_search_paths(self):
        self._search_paths = dict()

    @property
    def filters(self) -> dict[str, list[str]]:
        # Get-only; use the add/remove functions instead, or edit the returned dict directly
        return self._filters

    def reset_filters(self):
        self._filters = dict()

    @property
    def sidecar_data(self) -> dict:
        # Get only to avoid desync
        return self._sidecar_data

    ## Methods ##
    CASE_PATH_KEY = "case_paths"
    FILTERS_KEY = "filters"

    def save_sidecar(self):
        sidecar_data = {
            self.CASE_PATH_KEY: {k: str(v) for k, v in self.search_paths.items()},
            self.FILTERS_KEY: {k: str(v) for k, v in self.filters.items()},
        }

        with open(self.sidecar_path, "w") as fp:
            json.dump(sidecar_data, fp, indent=2)

    def load_sidecar(self):
        # If this is for a not-yet-created cohort, or for one without a sidecar, reset
        if not self.csv_path or not self.sidecar_path.exists():
            self.reset_search_paths()
            self.reset_filters()
            return
        # Otherwise, use the sidecar's contents to update our values
        with open(self.sidecar_path, "r") as fp:
            case_path_data = json.load(fp)
        # Update the case search paths
        case_data = case_path_data.get(self.CASE_PATH_KEY)
        if not type(case_data) == dict:
            raise ValueError(
                f"Cannot load sidecar, '{self.CASE_PATH_KEY}' was malformed!"
            )
        self._search_paths = {k: [Path(x) for x in v] for k, v in case_data.items()}
        # Update the filters
        filter_data = case_path_data.get(self.FILTERS_KEY)
        if not type(filter_data) == dict:
            raise ValueError(
                f"Cannot load sidecar, '{self.FILTERS_KEY}' was malformed!"
            )
        self._filters = {k: v for k, v in filter_data.items()}

    def editorWidget(self, parent: qt.QObject = None) -> "CohortTableWidget":
        return CohortTableWidget(self.model, parent)

    def find_valid_files(self, uid: str, column: str):
        # Use a black list for the given entry if it doesn't have one yet
        search_paths = self.search_paths.get(uid, [])
        filters = self.filters.get(column, [])
        valid_paths = []
        for sp in search_paths:
            # TODO: Replace with pathlib.walk when it becomes available
            for p in sp.rglob("*"):
                # Skip directories
                if not p.is_dir() and all([f in str(p) for f in filters]):
                    valid_paths.append(p)


## Related Widgets ##
class CohortTableModel(CSVBackedTableModel):
    """
    More specialized version of the CSV-backed model w/ additional checks
    and features specific to cohort editing
    """
    def __init__(self, csv_path: Optional[Path], editable: bool = True, parent: qt.QObject = None):
        super().__init__(csv_path, editable, parent)

        # Try to move the UID column to the front of the array
        if self._csv_path is not None:
            if not self._move_uid_to_index():
                raise ValueError("No UID column found, cannot set up Cohort model!")

    def _move_uid_to_index(self) -> bool:
        # If the UID is already in the index position, do nothing
        if self._csv_data[0, 0].lower() == "uid":
            return True
        # Otherwise, find and move the UID column to the front
        for i, c in enumerate(self.header):
            if c.lower() == "uid":
                # Model "reset", as this changes more than just one column's pos
                self.beginResetModel()
                uid_arr = self._csv_data[:, i]
                np.delete(self._csv_data, i, axis=1)
                np.insert(self._csv_data, 0, uid_arr, axis=1)
                self.endResetModel()
                return True
        # If that fails (there's no UID column), return False for handling
        return False

    @property
    def csv_data(self) -> "Optional[npt.NDArray]":
        if self._csv_data is None:
            return None
        # Suppressed because PyCharm went mad for some reason here
        # noinspection PyTypeChecker
        return self._csv_data[1:, 1:]

    @property
    def header(self) -> "npt.NDArray[str]":
        return self._csv_data[0, 1:]

    @property
    def indices(self) -> "npt.NDArray[str]":
        data = self._csv_data[1:, 0]
        return data

    def headerData(self, section: int, orientation: qt.Qt.Orientation, role: int = ...):
        # Note; "section" -> column for Horizontal, row for Vertical
        if role == qt.Qt.DisplayRole:
            if orientation == qt.Qt.Horizontal:
                return self.header[section]
            elif orientation == qt.Qt.Vertical:
                return self.indices[section]
        return None


class CohortTableWidget(CSVBackedTableWidget):
    """
    Simple implementation for viewing the contents of a CSV file in Qt.

    Shows an error message when the backing CSV cannot be read.
    """
    def __init__(self, model: CohortTableModel, parent: qt.QWidget = None):
        super().__init__(model, parent)

    @classmethod
    def from_path(cls, csv_path):
        model = CohortTableModel(csv_path, editable=False)
        return cls(model)


## Related Dialogues ##
class CohortEditorDialog(qt.QDialog):
    """
    GUI Dialog for editing a given cohort file.

    Can search for files associated with each case based on a search bar,
    allowing for automated creation of the table columns.

    Alternatively, the user can manually add, remove, edit the rows/columns
    within the table widget itself.
    """

    def __init__(
        self,
        csv_path: Path,
        data_path: Path,
        parent: qt.QObject = None,
    ):
        super().__init__(parent)

        # Backing IO Manager
        self._io = Cohort(csv_path, data_path)

        # Initial setup
        self.setWindowTitle(_("Cohort Editor"))
        self.setMinimumSize(900, 700)
        layout = qt.QVBoxLayout(self)

        # Main table widget
        cohortWidget = CohortTableWidget(self._io.model)
        cohortWidget.setFrameShape(qt.QFrame.Panel)
        cohortWidget.setFrameShadow(qt.QFrame.Sunken)
        cohortWidget.setLineWidth(3)
        layout.addWidget(cohortWidget)

        # Ok/Cancel Buttons
        buttonBox = qt.QDialogButtonBox()
        buttonBox.setStandardButtons(
            qt.QDialogButtonBox.Ok | qt.QDialogButtonBox.Cancel
        )

        def onButtonClicked(button: qt.QPushButton):
            button_role = buttonBox.buttonRole(button)
            if button_role == qt.QDialogButtonBox.RejectRole:
                self.reject()
            elif button_role == qt.QDialogButtonBox.AcceptRole:
                self.accept()
            else:
                raise ValueError("Pressed a button with an invalid role!")

        buttonBox.clicked.connect(onButtonClicked)
        layout.addWidget(buttonBox)
