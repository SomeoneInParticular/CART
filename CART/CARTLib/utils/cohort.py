import csv
import json
import logging
import os
from pathlib import Path
from typing import Optional, Protocol, TYPE_CHECKING

import numpy as np
from numpy import typing as npt

import ctk
import qt
from slicer.i18n import tr as _

from .widgets import CSVBackedTableModel, CSVBackedTableWidget


## Type Utils ##
if TYPE_CHECKING:
    # NOTE: this isn't perfect (this only exposes Widgets, and Slicer's QT impl
    # isn't the same as PyQT5 itself), but it's a LOT better than constant
    # cross-referencing
    import PyQt5.Qt as qt

# Typing aliases for commonly used dictionary mappings
CaseMap = dict[str, list[Path]]
FilterEntry = dict[str, list[str]]
FilterMap = dict[str, FilterEntry]


# Current version of the cohort manager
COHORT_VERSION = "0.1.0"


## Core ##
class Cohort:
    def __init__(self, csv_path: Path, data_path: Path, use_sidecar: bool = True):
        # Tracker for the model tracking the CSV data
        self._model: CohortTableModel = CohortTableModel(csv_path)

        # Track the data path for later
        self.data_path = data_path

        # JSON sidecar management
        self.use_sidecar = use_sidecar
        if use_sidecar:
            self.load_sidecar()
        else:
            # If no sidecar is to be used, generate blank cohort/filter entries
            self._case_map: CaseMap = dict()
            self._filters: FilterMap = dict()

    @classmethod
    def from_case_map(cls, csv_path: Path, data_path: Path, case_map: CaseMap):
        # Exit immediately if the case-map is empty
        if len(case_map) < 1:
            raise ValueError("Cannot create a cohort from an empty case map!")
        # Generate the backing CSV immediately using the case map's contents
        row_data = [["uid"], *[[k] for k in case_map.keys()]]
        with open(csv_path, "w") as fp:
            csv.writer(fp).writerows(row_data)
        # Generate the cohort instance, backed by this new CSV file
        cohort = cls(csv_path, data_path, use_sidecar=True)
        # Manually update its case map to match
        cohort._case_map = case_map
        # Immediately save the sidecar as well, for parity
        cohort.save_sidecar()

        return cohort

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
        # Note: the model implicitly reloads itself when a new CSV is specified.
        self._model.csv_path = new_path
        # Reset the filter data as well.
        self.load_sidecar()

    @property
    def sidecar_path(self) -> Path:
        # Get-only to avoid desync
        return self.csv_path.with_suffix(".json")

    @property
    def case_map(self) -> CaseMap:
        """
        Search paths for each case in the cohort.
        """
        # Get-only; use the add/remove functions instead, or edit the returned dict directly
        return self._case_map

    def reset_case_map(self):
        self._case_map = dict()

    @property
    def filters(self) -> FilterMap:
        # Get-only; use the add/remove functions instead, or edit the returned dict directly
        return self._filters

    FILTER_INCLUDE_KEY = "include"
    FILTER_EXCLUDE_KEY = "exclude"

    def set_filter(self, filter_label: str, filter_entry: FilterEntry):
        """
        Set the filter associated with a given feature label in the cohort

        :param filter_label: The label of the filter.
            If a filter already exists with this label, replaces it; otherwise, a new filter is created
        :param filter_entry: The filter entry to associate with the given label.
        """
        # Validate the new filter entry
        keyset = set(filter_entry.keys())
        if len(keyset - {self.FILTER_INCLUDE_KEY, self.FILTER_EXCLUDE_KEY}) > 0:
            raise ValueError(
                "Filter maps can only have two entries: 'include' and 'exclude'"
            )

        # Find and process the list of paths associated with this filter
        new_paths = self.find_column_files(filter_entry)
        new_paths = np.array([str(k) if k is not None else "" for k in new_paths])

        # If this is a new feature, create a new column to match
        if filter_label not in self.filters.keys():
            col_idx = self.model.columnCount()
            self.model.addColumn(col_idx, new_paths)
            # Set the header to this new label
            self.model.setHeaderData(
                col_idx, qt.Qt.Horizontal, filter_label, qt.Qt.EditRole
            )
        # Otherwise, replace the column's values with the newly found paths
        else:
            # Find the column position which matches our feature label
            col_idx = np.argwhere(self.model.header == filter_label).flatten()[0]
            # Change the model's contents to our new list of paths
            self.model.setColumn(col_idx, new_paths)

        # Save the new filter for later
        self.filters[filter_label] = filter_entry

    def rename_filter(self, old_name: str, new_name: str):
        # Check that there's actually a filter to rename
        if old_name not in self.filters.keys():
            raise ValueError(f"Cannot rename filter '{old_name}'; it doesn't exist!")
        # Update the backing model
        col_idx = np.argwhere(self.model.header == old_name).flatten()[0]
        self.model.setHeaderData(col_idx, qt.Qt.Horizontal, new_name, qt.Qt.EditRole)
        # Update the filter map to reflect the change
        filter_map = self.filters.pop(old_name)
        self.filters[new_name] = filter_map

    def reset_filters(self):
        self._filters = dict()

    @property
    def sidecar_data(self) -> dict:
        # Get only to avoid desync
        return self._sidecar_data

    ## Methods ##
    VERSION_KEY = "cohort_version"
    CASE_PATH_KEY = "case_paths"
    FILTERS_KEY = "filters"

    def save(self):
        self.save_csv()
        self.save_sidecar()

    def save_csv(self):
        self._model.save()

    def save_sidecar(self):
        sidecar_data = {
            self.VERSION_KEY: COHORT_VERSION,
            self.CASE_PATH_KEY: {
                k: [str(x) for x in v] for k, v in self.case_map.items()
            },
            self.FILTERS_KEY: self.filters,
        }

        with open(self.sidecar_path, "w") as fp:
            json.dump(sidecar_data, fp, indent=2)

    def load(self):
        self.load_csv()
        self.load_sidecar()

    def load_csv(self):
        # Delegate to our backing model
        self._model.load()

    def load_sidecar(self):
        # If this is for a not-yet-created cohort...
        if not self.csv_path:
            # ... reset everything and end
            self._case_map = {}
            self._filters = {}
            self._model._csv_data = None
            return
        # If we're just missing the sidecar...
        elif not self.sidecar_path.exists():
            # ... just reset the relevant contents instead
            self._case_map = {}
            self._filters = {}
            return
        # Otherwise, use the sidecar's contents to update our values
        with open(self.sidecar_path, "r") as fp:
            case_path_data = json.load(fp)

        # Update the case search paths
        case_data = case_path_data.get(self.CASE_PATH_KEY)
        if type(case_data) is not dict:
            raise ValueError(
                f"Cannot load sidecar, '{self.CASE_PATH_KEY}' was malformed!"
            )
        self._case_map = {k: [Path(x) for x in v] for k, v in case_data.items()}

        # Update the filters
        filter_data = case_path_data.get(self.FILTERS_KEY, {})
        if type(filter_data) is not dict:
            raise ValueError(
                f"Cannot load sidecar, '{self.FILTERS_KEY}' was malformed!"
            )
        self._filters = {k: v for k, v in filter_data.items()}

    def editorWidget(self, parent: qt.QObject = None) -> "CohortTableWidget":
        return CohortTableWidget(self.model, parent)

    def find_first_valid_file(
        self, search_paths: list[Path], filters: FilterEntry
    ) -> Optional[Path]:
        # Isolate the filters from one another
        include_values = filters[self.FILTER_INCLUDE_KEY]
        exclude_values = filters[self.FILTER_EXCLUDE_KEY]
        # Search every path in turn
        result = None
        for p in search_paths:
            # If the path isn't absolute, root it to our data path
            if not p.is_absolute():
                p = self.data_path / p
            # Only look at files; directories (such as DICOM) are currently not supported for automated cohorts
            # TODO: Replace with path.walk when it becomes available
            for r, __, fs in os.walk(p, topdown=True):
                r = Path(r)
                for f in fs:
                    f = r / f
                    file_string = str(f)
                    all_includes = len(include_values) == 0 or all(
                        [i in file_string for i in include_values]
                    )
                    no_excludes = len(exclude_values) == 0 or not any(
                        [i in file_string for i in exclude_values]
                    )
                    if all_includes and no_excludes:
                        result = f
                        break
                # Else-continue-break chain, allowing for the break to chain up the loops
                else:
                    continue
                break
            else:
                continue

        # If no valid files were found, return empty-handed
        if result is None:
            return None
        # If the result is within the data dir, make it relative
        elif self.data_path in result.parents:
            return result.relative_to(self.data_path)
        else:
            return result

    def find_column_files(self, column_filters: FilterEntry) -> list[Optional[Path]]:
        result_map = {}
        for k, v in self.case_map.items():
            result_map[k] = self.find_first_valid_file(v, column_filters)
        sorted_pathlist = [result_map.get(k, None) for k in self.model.indices]
        return sorted_pathlist


## Generators ##
class CaseGenerator(Protocol):
    """
    Function-like Protocol class for generating an initial set of cases.

    Allows for type-hinting, aiding in the registration of custom case generators for future extensions.
    """

    def __call__(self, data_path: Path) -> CaseMap: ...


# Default generators; simple BIDS support + blank slate
def _bids_cases_by_subject(data_path: Path) -> CaseMap:
    # Identify the initial "source" paths
    case_map = {}
    for p in data_path.glob("sub*/"):
        # Add this path initially (the "source" path)
        case_map[p.name] = [p.relative_to(data_path)]
    # Add associated derivative paths, if a derivatives folder already exists
    derivative_path = data_path / "derivatives"
    if not derivative_path.exists():
        logging.warning("No derivatives path found for BIDS directory, skipping.")
    else:
        for s, v in case_map.items():
            v.extend(
                [p.relative_to(data_path) for p in derivative_path.glob(f"*/{s}/")]
            )
    # Sort the results to make them easier to work with
    case_map = {k: case_map[k] for k in sorted(case_map.keys())}
    return case_map


def _bids_cases_by_session(data_path: Path) -> CaseMap:
    # Identify the initial "source" paths
    data_map = {}
    for p in data_path.glob("sub*/ses*/"):
        # Add this path initially (the "source" path)
        name = tuple(p.parts[-2:])
        data_map[name] = [p.relative_to(data_path)]
    # Add associated derivative paths, if such a directory exists
    derivative_path = data_path / "derivatives"
    if not derivative_path.exists():
        logging.warning("No derivatives path found for BIDS directory, skipping.")
        case_map = {"_".join(k): v for k, v in data_map.items()}
    else:
        case_map = {}
        for (subject, session), val_list in data_map.items():
            val_list.extend([
                p.relative_to(data_path)
                for p in derivative_path.glob(f"*/{subject}/{session}/")
            ])
            case_map[f"{subject}_{session}"] = val_list
    # Sort the results to make them easier to work with
    case_map = {k: case_map[k] for k in sorted(case_map.keys())}
    return case_map


def _blank(__: Path) -> CaseMap:
    return dict()


# Registry for cases to be displayed during Cohort init
CASE_GENERATORS: dict[str, CaseGenerator] = {
    "BIDS (Case By Subject)": _bids_cases_by_subject,
    "BIDS (Case By Session)": _bids_cases_by_session,
    "Blank Slate": _blank,
}


def register_case_generator(label: str, generator: CaseGenerator):
    if label in CASE_GENERATORS.keys():
        raise ValueError(
            f"Cannot register generator '{label}', an existing generator with that label already exists!"
        )
    CASE_GENERATORS[label] = generator


def cohort_from_generator(
    cohort_name: str, data_path: Path, output_path: Path, generator: CaseGenerator
) -> Cohort:
    """
    Generate a cohort from scratch, using the provided generator and input dataset.

    :param cohort_name: The name the cohort (file) should have
    :param data_path: The data path to reference when finding cases
    :param output_path: The path the resulting cohort's files should be placed within
    :param generator: The generator to user.
    """
    case_map = generator(data_path)
    csv_path = output_path / f"{cohort_name}.csv"
    cohort = Cohort.from_case_map(csv_path, data_path, case_map)
    return cohort


## Related Widgets ##
class CohortTableModel(CSVBackedTableModel):
    """
    More specialized version of the CSV-backed model w/ additional checks
    and features specific to cohort editing
    """

    def __init__(
        self, csv_path: Optional[Path], editable: bool = True, parent: qt.QObject = None
    ):
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

    def setHeaderData(self, section, orientation, value, role=...):
        if role == qt.Qt.EditRole:
            if orientation == qt.Qt.Horizontal:
                self.header[section] = value
            elif orientation == qt.Qt.Vertical:
                self.indices[section] = value
            self.headerDataChanged(orientation, section, section)


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
class NewCohortDialog(qt.QDialog):
    def __init__(
        self,
        data_path: Path,
        parent: qt.QObject = None,
    ):
        super().__init__(parent)

        # Track the data path for later
        self.data_path = data_path

        # Initial setup
        self.setWindowTitle(_("New Cohort"))
        layout = qt.QFormLayout(self)

        # Name to give the cohort
        cohortNameLabel = qt.QLabel(_("Name: "))
        cohortNameTooltip = _(
            "The name the cohort should have. Should follow your OS's file naming conventions."
        )
        cohortNameLabel.setToolTip(cohortNameTooltip)
        cohortNameEdit = qt.QLineEdit()
        cohortNameEdit.setToolTip(cohortNameTooltip)
        self.cohortNameEdit = cohortNameEdit
        layout.addRow(cohortNameLabel, cohortNameEdit)

        # Type of cohort to generate
        cohortTypeComboBox = qt.QComboBox()
        cohortTypeLabel = qt.QLabel(_("Cohort Type: "))
        cohortTypeComboBox.addItems(list(CASE_GENERATORS.keys()))
        self.cohortTypeComboBox = cohortTypeComboBox
        layout.addRow(cohortTypeLabel, cohortTypeComboBox)

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

    @property
    def cohort_name(self):
        return self.cohortNameEdit.text

    @property
    def current_generator(self) -> CaseGenerator:
        return CASE_GENERATORS[self.cohortTypeComboBox.currentText]


class CohortEditorDialog(qt.QDialog):
    """
    GUI Dialog for editing a given cohort file.

    Using the button panel, users can add, edit, or delete rows/columns within the cohort.

    The user can manually add, remove, edit the rows/columns within the table widget itself.
    """

    def __init__(
        self,
        cohort: Cohort,
        parent: qt.QObject = None,
    ):
        super().__init__(parent)

        # Backing cohort manager
        self._cohort = cohort

        # Initial setup
        self.setWindowTitle(_("Cohort Editor"))
        self.setMinimumSize(900, 700)
        layout = qt.QVBoxLayout(self)

        # Main table widget
        cohortWidget = CohortTableWidget(self._cohort.model)
        cohortWidget.setFrameShape(qt.QFrame.Panel)
        cohortWidget.setFrameShadow(qt.QFrame.Sunken)
        cohortWidget.setLineWidth(3)
        layout.addWidget(cohortWidget)

        # Add Case (Row) + Add Feature (Column) buttons
        newCaseButton = qt.QPushButton(_("New Case"))

        def onNewCaseClicked():
            dialog = CaseEditorDialog(self._cohort)
            if dialog.exec():
                # Without this, the cells rapidly bloat for some reason
                cohortWidget.tableView.resizeColumnsToContents()
                cohortWidget.tableView.resizeRowsToContents()

        newCaseButton.clicked.connect(onNewCaseClicked)

        newFeatureButton = qt.QPushButton(_("New Feature"))

        def onNewFeatureClicked():
            dialog = FeatureEditorDialog(self._cohort)
            if dialog.exec():
                # Without this, the cells rapidly bloat for some reason
                cohortWidget.tableView.resizeColumnsToContents()
                cohortWidget.tableView.resizeRowsToContents()

        newFeatureButton.clicked.connect(onNewFeatureClicked)

        newXButtonPanel = qt.QHBoxLayout()
        newXButtonPanel.addWidget(newCaseButton)
        newXButtonPanel.addWidget(newFeatureButton)
        layout.addLayout(newXButtonPanel)

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

    @classmethod
    def from_paths(cls, csv_path: Path, data_path: Path):
        # Generate the cohort manager using the provided paths
        cohort = Cohort(csv_path, data_path)
        return cls(cohort)


class FeatureEditorDialog(qt.QDialog):
    def __init__(
        self, cohort: Cohort, feature_name: str = None, parent: qt.QObject = None
    ):
        """
        Dialog for editing (or creating) new Features within a cohort.

        :param cohort: The Cohort to apply the edits to
        :param feature_name: The name of the feature to edit. If None, will create a feature with
            the user specified name instead.
        :param parent: Parent widget, as required by QT.
        """
        super().__init__(parent)

        # Backing cohort manager
        self._cohort = cohort

        # Reference feature name
        self._reference_feature = feature_name

        # Track whether changes have been made since this dialog was opened
        self.has_changed = False

        def mark_changed():
            self.has_changed = True

        # Initial setup
        self.setWindowTitle(_("Add New Feature"))
        self.setMinimumSize(500, self.minimumHeight)
        layout = qt.QFormLayout(self)

        # Data entry fields
        nameLabel = qt.QLabel(_("Feature Name:"))
        nameField = qt.QLineEdit()
        if feature_name:
            nameField.setText(feature_name)
        nameField.setPlaceholderText(_("e.g. Segmentation_T1w, spinal_reference"))
        nameField.textChanged.connect(mark_changed)
        nameTooltip = _(
            "Anything is valid, so long as it does not have any commas. We recommend following your selected "
            "Task's naming convention to ensure CART runs smoothly, however."
        )
        nameLabel.setToolTip(nameTooltip)
        nameField.setToolTip(nameTooltip)
        self.nameField = nameField
        layout.addRow(nameLabel, nameField)

        includeLabel = qt.QLabel(_("Include:"))
        includeField = qt.QLineEdit()
        includeField.textChanged.connect(mark_changed)
        includeTooltip = _(
            "Comma-separated elements that a file MUST have to be used for this feature. "
            "This incudes the directory the file is contained within!"
        )
        includeLabel.setToolTip(includeTooltip)
        includeField.setToolTip(includeTooltip)
        includeField.setPlaceholderText(_("e.g. T1w, nii, lesion_seg"))
        self.includeField = includeField
        layout.addRow(includeLabel, includeField)

        excludeLabel = qt.QLabel(_("Exclude:"))
        excludeField = qt.QLineEdit()
        excludeField.textChanged.connect(mark_changed)
        excludeTooltip = _(
            "Comma-separated elements that a file MUST NOT have to be used for this feature. "
            "This incudes the directory the file is contained within!"
        )
        excludeLabel.setToolTip(excludeTooltip)
        excludeField.setToolTip(excludeTooltip)
        excludeField.setPlaceholderText(_("e.g. derivatives, masked, brain"))
        self.excludeField = excludeField
        layout.addRow(excludeLabel, excludeField)

        # Ok/Cancel Buttons
        buttonBox = qt.QDialogButtonBox()
        buttonBox.setStandardButtons(
            qt.QDialogButtonBox.Ok | qt.QDialogButtonBox.Cancel
        )

        def onButtonClicked(button: qt.QPushButton):
            button_role = buttonBox.buttonRole(button)
            if button_role == qt.QDialogButtonBox.RejectRole:
                # Delegate to "onCancel" to prevent immediate closing
                self.onCancel()
            elif button_role == qt.QDialogButtonBox.AcceptRole:
                # Apply the requested changes to the cohort before closing.
                self.apply_changes()
                self.accept()
            else:
                raise ValueError("Pressed a button with an invalid role!")

        buttonBox.clicked.connect(onButtonClicked)
        layout.addWidget(buttonBox)

    def onCancel(self):
        # If we have changed anything, confirm we want to exit first
        if self.has_changed:
            msg = qt.QMessageBox()
            msg.setWindowTitle("Are you sure?")
            msg.setText("You have unsaved changes. Do you want to close anyways?")
            msg.setStandardButtons(qt.QMessageBox.Yes | qt.QMessageBox.No)
            result = msg.exec()
            # If the user backs out, return early to do nothing.
            if result != qt.QMessageBox.Yes:
                return
        # Otherwise, exit the program with a "rejection" signal
        self.reject()

    def apply_changes(self):
        # Only run the (relatively) expensive update if something has changed
        if not self.has_changed:
            return
        # Parse the contents of our GUI elements, stripping leading/trailing whitespace
        label = self.nameField.text.strip()
        filter_entry: FilterEntry = {
            Cohort.FILTER_INCLUDE_KEY: [
                s.strip() for s in self.includeField.text.split(",")
            ],
            Cohort.FILTER_EXCLUDE_KEY: [
                s.strip() for s in self.excludeField.text.split(",")
            ],
        }

        # Clean up "blank" filters which may have slipped through
        filter_entry[Cohort.FILTER_INCLUDE_KEY] = [
            x for x in filter_entry[Cohort.FILTER_INCLUDE_KEY] if x != ""
        ]
        filter_entry[Cohort.FILTER_EXCLUDE_KEY] = [
            x for x in filter_entry[Cohort.FILTER_EXCLUDE_KEY] if x != ""
        ]

        # If this an updated feature, rename the feature to this new name
        if self._reference_feature:
            self._cohort.rename_filter(self._reference_feature, label)

        # Update cohort to use the new filter
        self._cohort.set_filter(label, filter_entry)

        # Save the result
        self._cohort.save()


class CaseEditorDialog(qt.QDialog):
    def __init__(
        self, cohort: Cohort, case_id: str = None, parent: qt.QObject = None
    ):
        """
        Dialog for editing (or creating) new Features within a cohort.

        :param cohort: The Cohort to apply the edits to
        :param case_id: The name of the case to edit. If None, will create a feature with
            the user specified name instead.
        :param parent: Parent widget, as required by QT.
        """
        super().__init__(parent)

        # Backing cohort manager
        self._cohort = cohort

        # Reference feature name
        self._reference_case = case_id

        # Track whether changes have been made since this dialog was opened
        self.has_changed = False

        def mark_changed():
            self.has_changed = True

        # Initial setup
        self.setWindowTitle(_("Add New Case"))
        self.setMinimumSize(500, self.minimumHeight)
        layout = qt.QFormLayout(self)

        # Name Field
        nameLabel = qt.QLabel(_("Case Name:"))
        nameField = qt.QLineEdit()
        if case_id:
            nameField.setText(case_id)
        nameField.setPlaceholderText(_("e.g. sub-001, sub001_ses002"))
        nameField.textChanged.connect(mark_changed)
        nameTooltip = _(
            "An identifier for this case. Should be unique to the cohort; ideally, it should also "
            "implicitly reference the data it will refer to as well "
            "(i.e. sub-001 refers to data in sub-001 associated directories)."
        )
        nameLabel.setToolTip(nameTooltip)
        nameField.setToolTip(nameTooltip)
        self.nameField = nameField
        layout.addRow(nameLabel, nameField)

        # Search path list
        searchPathLabels = qt.QLabel(_("Search Paths: "))
        searchPathList = qt.QListWidget()

        layout.addRow(searchPathLabels)
        layout.addRow(searchPathList)

        # Button panel
        addButton = qt.QPushButton("Add")
        removeButton = qt.QPushButton("Remove")
        removeButton.setEnabled(False)

        def onAddClicked():
            fileDialog = qt.QFileDialog()
            fileDialog.setDirectory(str(cohort.data_path))
            fileDialog.setFileMode(qt.QFileDialog.Directory)
            if fileDialog.exec():
                d = fileDialog.selectedFiles()[0]
                d = qt.QListWidgetItem(d)
                searchPathList.addItem(d)
        addButton.clicked.connect(onAddClicked)

        def onItemSelectionChanged():
            removeButton.setEnabled(len(searchPathList.selectedIndexes()) > 0)
        searchPathList.itemSelectionChanged.connect(onItemSelectionChanged)

        def onRemoveClicked():
            for i in searchPathList.selectedItems():
                searchPathList.takeItem(searchPathList.row(i))
        removeButton.clicked.connect(onRemoveClicked)

        # Make them side-by-side and add them to the layout
        w = qt.QWidget()
        l = qt.QHBoxLayout(w)
        l.addWidget(addButton)
        l.addWidget(removeButton)
        layout.addRow(w)

        # Ok/Cancel Buttons
        buttonBox = qt.QDialogButtonBox()
        buttonBox.setStandardButtons(
            qt.QDialogButtonBox.Ok | qt.QDialogButtonBox.Cancel
        )

        def onButtonClicked(button: qt.QPushButton):
            button_role = buttonBox.buttonRole(button)
            if button_role == qt.QDialogButtonBox.RejectRole:
                # Delegate to "onCancel" to prevent immediate closing
                self.onCancel()
            elif button_role == qt.QDialogButtonBox.AcceptRole:
                # Apply the requested changes to the cohort before closing.
                self.apply_changes()
                self.accept()
            else:
                raise ValueError("Pressed a button with an invalid role!")

        buttonBox.clicked.connect(onButtonClicked)
        layout.addWidget(buttonBox)

    def onCancel(self):
        # If we have changed anything, confirm we want to exit first
        if self.has_changed:
            msg = qt.QMessageBox()
            msg.setWindowTitle("Are you sure?")
            msg.setText("You have unsaved changes. Do you want to close anyways?")
            msg.setStandardButtons(qt.QMessageBox.Yes | qt.QMessageBox.No)
            result = msg.exec()
            # If the user backs out, return early to do nothing.
            if result != qt.QMessageBox.Yes:
                return
        # Otherwise, exit the program with a "rejection" signal
        self.reject()

    def apply_changes(self):
        # # Only run the (relatively) expensive update if something has changed
        # if not self.has_changed:
        #     return
        # # Parse the contents of our GUI elements, stripping leading/trailing whitespace
        # label = self.nameField.text.strip()
        # filter_entry: FilterEntry = {
        #     Cohort.FILTER_INCLUDE_KEY: [
        #         s.strip() for s in self.includeField.text.split(",")
        #     ],
        #     Cohort.FILTER_EXCLUDE_KEY: [
        #         s.strip() for s in self.excludeField.text.split(",")
        #     ],
        # }
        #
        # # Clean up "blank" filters which may have slipped through
        # filter_entry[Cohort.FILTER_INCLUDE_KEY] = [
        #     x for x in filter_entry[Cohort.FILTER_INCLUDE_KEY] if x != ""
        # ]
        # filter_entry[Cohort.FILTER_EXCLUDE_KEY] = [
        #     x for x in filter_entry[Cohort.FILTER_EXCLUDE_KEY] if x != ""
        # ]
        #
        # # If this an updated feature, rename the feature to this new name
        # if self._reference_case:
        #     self._cohort.rename_filter(self._reference_case, label)
        #
        # # Update cohort to use the new filter
        # self._cohort.set_filter(label, filter_entry)
        #
        # # Save the result
        # self._cohort.save()
        pass
