import copy
import csv
import json
import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Protocol, TYPE_CHECKING

import numpy as np
from numpy import typing as npt

import ctk
import qt
from slicer.i18n import tr as _

from .config import DictBackedConfig
from .widgets import (
    CSVBackedTableModel,
    CSVBackedTableWidget,
    CARTPathLineEdit,
    ChangeTrackingDialogue,
)

## Type Utils ##
if TYPE_CHECKING:
    # Avoid potential cyclic imports
    from CARTLib.core.TaskBaseClass import TaskBaseClass
    from CARTLib.core.DataUnitBase import ResourceType

    # NOTE: this isn't perfect (this only exposes Widgets, and Slicer's QT impl
    # isn't the same as PyQT5 itself), but it's a LOT better than constant
    # cross-referencing
    import PyQt5.Qt as qt

# Typing aliases for commonly used dictionary mappings
CaseMap = dict[str, list[Path]]
FilterMap = dict[str, dict]
NameMap = dict[str, str]

# Current version of the cohort manager
COHORT_VERSION = "0.2.0"


## Core ##
class CohortModel(CSVBackedTableModel):
    """
    More specialized version of the CSV-backed model w/ additional checks
    and resources specific to cohort editing.
    """

    ## Constructors ##
    def __init__(
        self,
        # NOTE: These are "optional mandatory" to force devs to consider why they're doing this!
        csv_path: Optional[Path],
        data_path: Optional[Path],
        editable: bool = True,
        reference_task: "type[TaskBaseClass]" = None,
        use_sidecar: bool = True,
        parent: qt.QObject = None
    ):
        """
        Constructor

        :param csv_path: The file this model should save to (and load from, if it already exists).
        :param data_path: Where this cohort should look when trying to find resource files.
        :param editable: Whether this cohort can be edited by its views.
        :param reference_task: A task type this cohort should reference when generating "pretty" columns.
        :param use_sidecar: Whether to generator (and reference, if it already exists) a JSON sidecar file.
            If false, the cohort's resource and case maps will NOT be preserved across loads!
        :param parent: The parent widget for QT hierarchy management.
        """
        # Disable editing explicitly if no data path is provided
        if data_path is None:
            editable = False

        # Track the data path and reference task for later
        self.data_path = data_path
        self.reference_task = reference_task

        # Initialize blank placeholders
        self._case_map = dict()
        self._resource_map = dict()

        # Track whether to user a sidecar before initializing (which will attempt to load it)
        self.use_sidecar = use_sidecar

        super().__init__(csv_path, editable, parent)

        # Try to move the UID column to the front of the array
        if self._csv_path is not None:
            if not self._move_uid_to_index():
                raise ValueError("No UID column found, cannot set up Cohort model!")

        # Track whenever anything about this model changes!
        self.connectChangeEvents()

        # Set ourselves to "not changed"
        self.has_changed = False

    def connectChangeEvents(self):
        self.dataChanged.connect(self._mark_changed)
        self.headerDataChanged.connect(self._mark_changed)
        self.rowsInserted.connect(self._mark_changed)
        self.rowsMoved.connect(self._mark_changed)
        self.rowsRemoved.connect(self._mark_changed)
        self.columnsInserted.connect(self._mark_changed)
        self.columnsMoved.connect(self._mark_changed)
        self.columnsRemoved.connect(self._mark_changed)

    def disconnectChangeEvents(self):
        self.dataChanged.disconnect(self._mark_changed)
        self.headerDataChanged.disconnect(self._mark_changed)
        self.rowsInserted.disconnect(self._mark_changed)
        self.rowsMoved.disconnect(self._mark_changed)
        self.rowsRemoved.disconnect(self._mark_changed)
        self.columnsInserted.disconnect(self._mark_changed)
        self.columnsMoved.disconnect(self._mark_changed)
        self.columnsRemoved.disconnect(self._mark_changed)

    @classmethod
    def from_case_map(
        cls,
        csv_path: Path,
        data_path: Path,
        case_map: CaseMap,
        editable: bool = True,
        reference_task: "TaskBaseClass" = None,
        use_sidecar: bool = True
    ):
        # Generate the backing CSV immediately using the case map's contents
        row_data = [["uid"], *[[k] for k in case_map.keys()]]
        with open(csv_path, "w") as fp:
            csv.writer(fp).writerows(row_data)
        # Generate a new cohort instance, backed by this new CSV file and w/ a blank side-car
        cohort = cls(csv_path, data_path, editable, reference_task, False)
        cohort.use_sidecar = use_sidecar
        # Manually update its case map to match
        cohort._case_map = case_map
        # If we're using a sidecar, save its contents as well
        if use_sidecar:
            cohort._save_sidecar()

        return cohort

    ## Setup Utilities ##
    def _mark_changed(self):
        self.has_changed = True

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

    ## Attributes/Properties ##
    @property
    def sidecar_path(self) -> Path:
        # Get-only to avoid desync
        return self.csv_path.with_suffix(".json")

    @property
    def case_map(self):
        # Get only; use the set/remove functions instead
        return self._case_map

    @property
    def resource_map(self):
        # Get only; use the set/remove functions instead
        return self._resource_map

    ## Sidecar Management ##
    def set_case_data(self, case_label: str, search_paths: list[Path]):
        """
        Set the search paths for a given case in the cohort

        :param case_label: The label for the case (and its search paths).
            If a case already exists with this label, replaces it; otherwise, a new case is created.
        :param search_paths: The paths that should be searched when finding files for this case.
        """
        # Get the list of paths for this case
        new_paths = self.find_row_files(search_paths)
        new_paths = np.array([str(k) if k is not None else "" for k in new_paths])

        # If this is a new case, create a new column to match
        if case_label not in self.case_map.keys():
            # Create a new row at the end of the dataset
            row_idx = self.rowCount()
            self.addRow(row_idx, new_paths)
            # Set the header to this new label
            self.setHeaderData(
                row_idx, qt.Qt.Vertical, case_label, qt.Qt.EditRole
            )
        # Otherwise, replace the row's values with the newly found paths
        else:
            # Find the column position which matches our resource label
            row_idx = np.argwhere(self.indices == case_label).flatten()[0]
            # Change the column's contents to our new list of paths
            self.setRow(row_idx, new_paths)

        # Save the new filter for later
        self.case_map[case_label] = search_paths

    def rename_case(self, old_name: str, new_name: str):
        # Check if a case map with this name already exists
        if old_name not in self.case_map.keys():
            raise ValueError(f"Cannot rename case '{old_name}'; it doesn't exist!")
        # Update the backing model
        row_idx = np.argwhere(self.indices == old_name).flatten()[0]
        self.setHeaderData(row_idx, qt.Qt.Vertical, new_name, qt.Qt.EditRole)
        # Update the case map to reflect the change
        case_map_entry = self.case_map.pop(old_name)
        self.case_map[new_name] = case_map_entry

    def drop_cases(self, names: list[str]):
        # Check the names before proceeding
        for name in names:
            # Check if a case map with this name exists
            if name not in self.case_map.keys():
                raise ValueError(f"Cannot delete case '{name}'; it doesn't exist!")

        # Do everything in one go to avoid partial corruption
        for name in names:
            # Update the backing model
            row_idx = np.argwhere(self.indices == name).flatten()[0]
            self.dropRow(row_idx)
            # Update the case map
            self.case_map.pop(name)

    ORIGINAL_NAME_KEY = "original_name"
    RESOURCE_TYPE_KEY = "resource_type"
    FILTER_INCLUDE_KEY = "include"
    FILTER_EXCLUDE_KEY = "exclude"

    def set_resource_data(self, resource_label: str, filter_entry: dict):
        """
        Set the filters for a given resource in the cohort.

        :param resource_label: The label of the resource to update/create.
            If a filter already exists with this label, replaces it; otherwise, a new filter is created
        :param filter_entry: The filter entry to associate with the new/updated resource.
        """
        # Validate the new filter entry
        keyset = set(filter_entry.keys())
        invalid_keys = keyset - {
            self.ORIGINAL_NAME_KEY, self.RESOURCE_TYPE_KEY, self.FILTER_EXCLUDE_KEY, self.FILTER_INCLUDE_KEY
        }
        for v in invalid_keys:
            logging.warning(f"Found key {v} which wasn't recognized; ignored!")

        # Find and process the list of paths associated with this filter
        new_paths = self.find_column_files(filter_entry)
        new_paths = np.array([str(k) if k is not None else "" for k in new_paths])

        # If this is a new resource, create a new column to match
        if resource_label not in self.header:
            # Add a new column to the end of the dataset
            col_idx = self.columnCount()
            self.addColumn(col_idx, new_paths)
            # Set the header to this new label
            self.setHeaderData(
                col_idx, qt.Qt.Horizontal, resource_label, qt.Qt.EditRole
            )
        # Otherwise, replace the column's values with the newly found paths
        else:
            # Find the column position which matches our resource label
            col_idx = np.argwhere(self.header == resource_label).flatten()[0]
            # Change the model's contents to our new list of paths
            self.setColumn(col_idx, new_paths)

        # Save the filter for later
        self.resource_map[resource_label] = filter_entry

    def rename_filter(self, old_name: str, new_name: str):
        # Check that there's actually a filter to rename
        if old_name not in self.resource_map.keys():
            raise ValueError(f"Cannot rename resource '{old_name}'; it doesn't exist!")
        # Update the backing model
        col_idx = np.argwhere(self.header == old_name).flatten()[0]
        self.setHeaderData(col_idx, qt.Qt.Horizontal, new_name, qt.Qt.EditRole)
        # Update the filter map to reflect the change
        filter_map = self.resource_map.pop(old_name)
        self.resource_map[new_name] = filter_map

    def drop_filters(self, names: list[str]):
        # Check the names before proceeding
        for name in names:
            # Check if a case map with this name exists
            if name not in self.resource_map.keys():
                raise ValueError(f"Cannot delete resource '{name}'; it doesn't exist!")

        # Do everything in one go to avoid partial corruption
        for name in names:
            # Update the backing model
            col_idx = np.argwhere(self.header == name).flatten()[0]
            self.dropColumn(col_idx)
            # Update the case map
            self.resource_map.pop(name)

    ## Data Management ##
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

    def data(self, index: qt.QModelIndex, role=qt.Qt.DisplayRole):
        # If this is a tooltip role, add the corresponding tooltip
        if role == qt.Qt.ToolTipRole and self.is_editable():
            row_name = self.indices[index.row()]
            col_name = self.header[index.column()]
            return _(
                "Double-click to manually set the value of this cell.\n"
                "Right click to edit the settings for the entire case "
                f"({row_name}) or resource ({col_name});\n"
                "This will update ALL cells for that row/column!"
            )
        # Otherwise, delegate to the superclass
        return super().data(index, role)

    def headerData(self, section: int, orientation: qt.Qt.Orientation, role: int = ...):
        # Note; "section" -> column for Horizontal, row for Vertical
        if role == qt.Qt.DisplayRole:
            if orientation == qt.Qt.Horizontal:
                # Get the CSV value at this position
                csv_label = self.header[section]

                # Use the "pretty" name instead
                return self.csv_to_pretty(csv_label)
            elif orientation == qt.Qt.Vertical:
                return self.indices[section]
        return None

    def removeColumns(self, column, count, parent = ...):
        self.beginRemoveColumns(parent, column, column + count - 1)
        # Offset by 1 to account for the new UID column
        idx = [column + i + 1 for i in range(count)]
        self._csv_data = np.delete(self._csv_data, idx, axis=1)
        self.endRemoveColumns()

    def setHeaderData(self, section, orientation, value, role=...):
        if role == qt.Qt.EditRole:
            if orientation == qt.Qt.Horizontal:
                self.header[section] = value
            elif orientation == qt.Qt.Vertical:
                self.indices[section] = value
            self.headerDataChanged(orientation, section, section)

    ## File Searching/Filtering ##
    def find_first_valid_file(
        self, search_paths: list[Path], filters: dict
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

    def find_row_files(self, search_paths: list[Path]) -> list[Optional[Path]]:
        result_map = {}
        for k, v in self.resource_map.items():
            result_map[k] = self.find_first_valid_file(search_paths, v)
        sorted_pathlist = [result_map.get(k, None) for k in self.header]
        return sorted_pathlist

    def find_column_files(self, column_filters: dict) -> list[Optional[Path]]:
        result_map = {}
        for k, v in self.case_map.items():
            result_map[k] = self.find_first_valid_file(v, column_filters)
        sorted_pathlist = [result_map.get(k, None) for k in self.indices]
        return sorted_pathlist

    ## I/O ##
    VERSION_KEY = "cohort_version"
    CASE_PATH_KEY = "case_paths"
    FILTERS_KEY = "filters"

    def save(self):
        # Only save if we have changed
        if self.has_changed:
            # Save the CSV (super-class delegate)
            super().save()
            # Save the sidecar as well, if requested
            if self.use_sidecar:
                self._save_sidecar()
            # Mark ourselves as unchanged
            self.has_changed = False

    def _save_sidecar(self):
        # Save the sidecar data on its own.
        sidecar_data = {
            self.VERSION_KEY: COHORT_VERSION,
            self.CASE_PATH_KEY: {
                k: [str(x) for x in v] for k, v in self.case_map.items()
            },
            self.FILTERS_KEY: self.resource_map,
        }

        with open(self.sidecar_path, "w") as fp:
            json.dump(sidecar_data, fp, indent=2)

    def load(self):
        # Load the CSV contents
        super().load()
        # Load the sidecar contents as well if requested
        if self.use_sidecar:
            self._load_sidecar()
        # Mark ourselves as unchanged
        self.has_changed = False

    def _load_sidecar(self):
        # If this is for a not-yet-created cohort...
        if not self.csv_path:
            # ... reset everything and end
            self._case_map = dict()
            self._resource_map = dict()
            self._csv_data = None
            return
        # If we're just missing the sidecar...
        elif not self.sidecar_path.exists():
            # ... just reset the relevant contents instead
            self._case_map = dict()
            self._resource_map = dict()
            return
        # Otherwise, use the sidecar's contents to update ourselves
        with open(self.sidecar_path, "r") as fp:
            case_path_data = json.load(fp)

        # Update the case map
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
        self._resource_map = {k: v for k, v in filter_data.items()}

    ## Utilities ##
    @contextmanager
    def temporarily_editable(self):
        if self.is_editable():
            yield
        else:
            self.set_editable(True)
            yield
            self.set_editable(False)

    def csv_to_original(self, csv_label: str) -> Optional[str]:
        # Return the "original" name (provided by the user) for this resource
        resource = self.resource_map.get(csv_label)
        if resource is None:
            return None
        return resource.get(self.ORIGINAL_NAME_KEY)

    def csv_to_resource_type(self, csv_label: str) -> "Optional[ResourceType]":
        # If we don't have a reference task, there are no resource types (yet)
        if self.reference_task is None:
            return None

        # Get the resource associated with this label; return None if we couldn't find one
        resource = self.resource_map.get(csv_label)
        if resource is None:
            return None

        # Get the type of resource for this instance
        type_id = resource.get(self.RESOURCE_TYPE_KEY)
        resource_type: "ResourceType" = (
            self.reference_task.getDataUnitFactory().resource_types().get(type_id)
        )

        return resource_type

    def csv_to_pretty(self, csv_label: str) -> Optional[str]:
        # Get the resource for this label
        resource = self.resource_map.get(csv_label)
        if resource is None:
            return None

        # Get the type of resource for this instance
        resource_type = self.csv_to_resource_type(csv_label)
        if resource_type is None:
            return csv_label

        # If the resource doesn't have an original name, use the CSV name instead
        original_label = self.csv_to_original(csv_label)
        # Use the CSV string as a fallback if there's no original label
        if original_label is None:
            return resource_type.format_for_gui(csv_label)
        else:
            return resource_type.format_for_gui(original_label)


## Generators ##
class CaseGenerator(Protocol):
    """
    Function-like Protocol class for generating an initial set of cases.

    Allows for type-hinting, aiding in the registration of custom case generators for future extensions.
    """

    def __call__(self, data_path: Path) -> CaseMap: ...


# Default generators; simple BIDS support + blank slate
def _bids_cases(data_path: Path) -> CaseMap:
    # Identify the initial "source" paths
    subject_map = {}
    session_map = {}
    # Search by subject first
    for p in data_path.glob("sub*/"):
        # Find any sessions associated with this subject
        ses_ps = list(p.glob("ses*/"))
        # If there were none, use the subject alone for this case
        if len(ses_ps) < 1:
            name = p.parts[-1]
            subject_map[name] = [p.relative_to(data_path)]
        # Otherwise, prepare a case for each session
        else:
            for p2 in ses_ps:
                name = "_".join(p2.parts[-2:])
                session_map[name] = [p2.relative_to(data_path)]

    # Add associated derivative paths, if such a directory exists
    derivative_path = data_path / "derivatives"
    if not derivative_path.exists():
        logging.warning("No derivatives path found for BIDS directory, skipping.")
    else:
        # Parse subject-only cases
        for subject, val_list in subject_map.items():
            val_list.extend([
                p.relative_to(data_path)
                for p in derivative_path.glob(f"*/{subject}/")
            ])
        # Parse session-based cases
        for (subject, session), val_list in session_map.items():
            val_list.extend([
                p.relative_to(data_path)
                for p in derivative_path.glob(f"*/{subject}/{session}/")
            ])
    # Stack everything together
    case_map = {k: v for k, v in subject_map.items()}
    case_map.update(session_map)
    # Sort the results to make them easier to work with
    case_map = {k: case_map[k] for k in sorted(case_map.keys())}
    return case_map


def _blank(__: Path) -> CaseMap:
    return dict()


# Registry for cases to be displayed during Cohort init
CASE_GENERATORS: dict[str, CaseGenerator] = {
    "BIDS": _bids_cases,
    "Blank Slate": _blank,
}

GENERATOR_DESCRIPTIONS: dict[str, str] = {
    "BIDS": _(
        "Iterate through your BIDS dataset on a per-subject and per-session basis. "
        "If multiple sessions are present, will iterate through them one-at-a-time. "
        "Looks for the 'sub' prefix to identify subjects, and 'ses' for sessions."),
    "Blank Slate": _(
        "Generate a completely emply cohort file. You will need to add each case "
        "manually; this only generates the (blank) files needed for a cohort file "
        "to be managed by CART."
    )
}

def register_case_generator(label: str, description: str, generator: CaseGenerator):
    if label in CASE_GENERATORS.keys():
        raise ValueError(
            f"Cannot register generator '{label}', an existing generator with that label already exists!"
        )
    GENERATOR_DESCRIPTIONS[label] = description
    CASE_GENERATORS[label] = generator


def cohort_from_generator(
    cohort_path: Path, data_path: Path, generator: CaseGenerator
) -> CohortModel:
    """
    Generate a cohort from scratch, using the provided generator and input dataset.

    :param cohort_path: The to-be-created (or overwritten) cohort file path
    :param data_path: The data path to reference when finding cases
    :param generator: The generator to user.
    """
    # Build the case map from the generator
    case_map = generator(data_path)
    # Create the cohort model from that
    cohort = CohortModel.from_case_map(cohort_path, data_path, case_map)
    return cohort


## Related Widgets ##
class CohortTableView(qt.QTableView):
    """
    Provides a default context menu for use w/ this class of widgets.

    Generally, however, you should use CohortTableWidget (below) instead.
    """

    def __init__(
        self,
        task_config: DictBackedConfig = None,
        parent: qt.QObject = None
    ):
        """
        Constructor

        :param parent: The parent widget for QT hierarchy management.
        """
        super().__init__(parent)

        # Track the task config for later
        self.task_config = task_config

        # Change the layout to be more sensible
        self.horizontalHeader().setSectionResizeMode(qt.QHeaderView.ResizeToContents)
        self.verticalHeader().setSectionResizeMode(qt.QHeaderView.ResizeToContents)
        self.setHorizontalScrollMode(qt.QAbstractItemView.ScrollPerPixel)

    def contextMenuEvent(self, event: "qt.QContextMenuEvent"):
        # If the table we're viewing isn't editable, skip
        if not self.model().is_editable():
            return

        # If the corresponding index is invalid, end here
        pos = event.pos()
        idx = self.indexAt(pos)
        if not idx.isValid():
            return

        # Otherwise, build a menu of actions to do
        menu = qt.QMenu(self)
        self.installRowActions(menu, idx)
        self.installColActions(menu, idx)

        # Show it to the user
        menu.popup(self.viewport().mapToGlobal(pos))

    def installRowActions(self, menu: qt.QMenu, idx: qt.QModelIndex):
        # Get the case label for ease-of-use
        row_id = self.model().indices[idx.row()]

        # Modification action
        editAction = menu.addAction(_(f"Modify {row_id}"))
        def _modifyRow():
            dialog = CaseEditorDialog(self.model(), row_id)
            dialog.exec()
        editAction.triggered.connect(_modifyRow)

    def installColActions(self, menu: qt.QMenu, idx: qt.QModelIndex):
        # Get the case label for ease-of-use
        model: CohortModel = self.model()
        col_id = model.header[idx.column()]
        col_pretty = model.csv_to_pretty(col_id)
        task_config = self.task_config

        # Modification action
        editAction = menu.addAction(_(f"Modify {col_pretty}"))
        def _modifyColumn():
            dialog = ResourceEditorDialogue(
                cohort=model, resource_name=col_id, task_config=task_config
            )
            dialog.exec()
        editAction.triggered.connect(_modifyColumn)

    def __del__(self):
        # Disconnect change events; PythonQT isn't smart enough to clean up
        #  self-referential actions it seems.
        if self.model() is not None:
            self.model().disconnectChangeEvents()


class CohortTableWidget(CSVBackedTableWidget):
    """
    Modified version of the CSVBackedTableWidget which tracks a
    CohortTableView instead.
    """

    def __init__(
        self,
        model: CohortModel,
        task_config: Optional[DictBackedConfig] = None,
        parent: qt.QWidget = None,
    ):
        """
        Constructor

        :param model: The cohort model to view within this widget.
        :param parent: The parent widget for QT hierarchy management.
        """
        super().__init__(model, parent)

        # Swap to our (contex-menu providing) table view class.
        self.tableView = CohortTableView(task_config=task_config)
        self.tableView.setModel(model)
        self.refresh()

    @classmethod
    def from_path(
        cls,
        csv_path: Optional[Path] = None,
        data_path: Optional[Path] = None,
        editable: bool = True
    ):
        # Explicitly disable editing if no data path was provided
        if data_path is None:
            editable = False
        model = CohortModel(csv_path, data_path, editable=editable)
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
        cohortNameLabel = qt.QLabel(_("File: "))
        cohortFileEdit = CARTPathLineEdit()
        cohortNameTooltip = _(
            "A CSV file with cases generated based on your input file will be created "
            "when this prompt is closed; you can select (and edit) it later if you need to."
        )
        cohortNameLabel.setToolTip(cohortNameTooltip)
        cohortFileEdit.setToolTip(cohortNameTooltip)
        cohortFileEdit.setPlaceholderText(_(
            "Where the cohort file should be saved."
        ))
        # Allow the user to create files as well
        cohortFileEdit.filters = cohortFileEdit.filters | ctk.ctkPathLineEdit.Writable
        # Make sure only CSV files are visible (and valid)
        cohortFileEdit.nameFilters = [
            "CSV files (*.csv)",
        ]
        self._cohortFileEdit = cohortFileEdit
        layout.addRow(cohortNameLabel, cohortFileEdit)

        # Type of cohort to generate
        cohortTypeComboBox = qt.QComboBox(None)
        cohortTypeLabel = qt.QLabel(_("Cohort Type: "))
        cohortTypeComboBox.addItems(list(CASE_GENERATORS.keys()))
        self._cohortTypeComboBox = cohortTypeComboBox
        layout.addRow(cohortTypeLabel, cohortTypeComboBox)

        # Description of said type
        cohortTypeDescription = qt.QTextBrowser(None)
        cohortTypeDescription.setText(
            _("Details about the selected cohort type will appear here.")
        )
        # Fill all available space
        cohortTypeDescription.setSizePolicy(
            qt.QSizePolicy.Expanding, qt.QSizePolicy.Expanding
        )
        # Add a border around it to visually distinguish it
        cohortTypeDescription.setFrameShape(qt.QFrame.Panel)
        cohortTypeDescription.setFrameShadow(qt.QFrame.Sunken)
        cohortTypeDescription.setLineWidth(3)
        # Align text to the upper-left
        cohortTypeDescription.setAlignment(qt.Qt.AlignLeft | qt.Qt.AlignTop)
        # Make it read-only
        cohortTypeDescription.setReadOnly(True)
        layout.addRow(cohortTypeDescription)
        # Default to no selected index
        cohortTypeComboBox.setCurrentIndex(-1)

        # Ok/Cancel Buttons
        buttonBox = qt.QDialogButtonBox()
        buttonBox.setStandardButtons(
            qt.QDialogButtonBox.Ok | qt.QDialogButtonBox.Cancel
        )
        layout.addWidget(buttonBox)
        # Disable the OK button until the user selects valid options
        self._ok_button = buttonBox.button(qt.QDialogButtonBox.Ok)

        # Connections
        @qt.Slot(str)
        def onCohortChanged(new_txt: str):
            # Disable the button if the file changed
            self.validate()

        cohortFileEdit.textChanged.connect(onCohortChanged)

        @qt.Slot(str)
        def onCohortTypeChanged(new_txt: str):
            # Update the preview text to match the new selection
            new_description = GENERATOR_DESCRIPTIONS.get(new_txt, _("Missing description for this case generator!"))
            cohortTypeDescription.setText(new_description)
            self.validate()

        cohortTypeComboBox.currentTextChanged.connect(onCohortTypeChanged)

        @qt.Slot(qt.QPushButton)
        def onButtonClicked(button: qt.QPushButton):
            button_role = buttonBox.buttonRole(button)
            if button_role == qt.QDialogButtonBox.RejectRole:
                self.reject()
            elif button_role == qt.QDialogButtonBox.AcceptRole:
                self.accept()
            else:
                raise ValueError("Pressed a button with an invalid role!")

        buttonBox.clicked.connect(onButtonClicked)

        # Run validation to sync everything up
        self.validate()

    @property
    def cohort_file(self) -> Path:
        # Workaround to CTK not playing nicely w/ "registerField"
        path = self._cohortFileEdit.currentPath
        if not path:
            return None
        return Path(path)

    @property
    def current_generator(self) -> Optional[CaseGenerator]:
        # noinspection PyTypeChecker
        return CASE_GENERATORS.get(self._cohortTypeComboBox.currentText, None)

    def validate(self):
        # Enable/disable the button based on current values
        self._ok_button.setEnabled(
            self.cohort_file is not None and self.current_generator
        )


# TODO: Switch to SmartClosingDialog
class CohortEditorDialog(qt.QDialog):
    """
    GUI Dialog for editing a given cohort file.

    Using the button panel, users can add, edit, or delete rows/columns within the cohort.

    The user can manually add, remove, edit the rows/columns within the table widget itself.
    """

    def __init__(
        self,
        cohort: CohortModel,
        task_config: DictBackedConfig,
        parent: qt.QObject = None,
    ):
        # If the cohort is not editable, reject attempts to edit it
        if not cohort.is_editable():
            raise ValueError("Cannot edit a un-editable Cohort!")

        super().__init__(parent)

        # QT is astonishingly shit at handling itself, so we need to track
        #  connections to disconnect later
        self._to_disconnect = []

        # Backing cohort manager
        self._cohort = cohort

        # Track a parent-less copy of the config
        # (parent-less to prevent changes propagating upwards prematurely)
        self._original_task_config = task_config
        self._task_config = copy.deepcopy(task_config)
        self._task_config.parent_config = None

        # Initial setup
        self.setWindowTitle(_("Cohort Editor"))
        self.setMinimumSize(900, 700)
        layout = qt.QVBoxLayout(self)

        # Main table widget
        cohortWidget = CohortTableWidget(self._cohort, self._task_config)
        cohortWidget.setFrameShape(qt.QFrame.Panel)
        cohortWidget.setFrameShadow(qt.QFrame.Sunken)
        cohortWidget.setLineWidth(3)
        layout.addWidget(cohortWidget)

        # Cohort Management Buttons
        self._addButtons(layout, cohortWidget)

        # Ok/Cancel Buttons
        buttonBox = qt.QDialogButtonBox()
        buttonBox.setStandardButtons(
            qt.QDialogButtonBox.Ok | qt.QDialogButtonBox.Cancel
        )

        @qt.Slot(qt.QPushButton)
        def onButtonClicked(button: qt.QPushButton):
            button_role = buttonBox.buttonRole(button)
            if button_role == qt.QDialogButtonBox.RejectRole:
                # Confirm the user wants to reject any changes first
                if self.confirmReject():
                    self.reject()
            elif button_role == qt.QDialogButtonBox.AcceptRole:
                # Only save changes to the cohort when confirmed!
                self._cohort.save()
                # Update our original config w/ any changes made to our modified config
                self._original_task_config.backing_dict = self._task_config.backing_dict
                self._original_task_config.has_changed = True
                # Accept and close
                self.accept()
            else:
                raise ValueError("Pressed a button with an invalid role!")

        buttonBox.clicked.connect(onButtonClicked)
        self._to_disconnect.append(buttonBox.clicked)
        layout.addWidget(buttonBox)

    def _addButtons(self, layout: "qt.QVBoxLayout", cohortWidget: "CohortTableWidget") -> qt.QGridLayout:
        # Add Case (Row) + Add Resource (Column) buttons
        newCaseButton = qt.QPushButton(_("New Case [Row]"))
        newCaseButton.setToolTip(
            _(
                "Add a new case to the cohort. All resources (columns) "
                "will be automatically populated with corresponding files "
                "wherever possible."
            )
        )

        @qt.Slot(None)
        def newCaseClicked():
            dialog = CaseEditorDialog(self._cohort)
            if dialog.exec():
                # Without this, the cells rapidly bloat for some reason
                cohortWidget.tableView.resizeColumnsToContents()
                cohortWidget.tableView.resizeRowsToContents()
        newCaseButton.clicked.connect(newCaseClicked)
        self._to_disconnect.append(newCaseButton.clicked)

        newResourceButton = qt.QPushButton(_("New Resource [Column]"))
        newResourceButton.setToolTip(
            _(
                "Add a new resource to the cohort. All cases (rows) "
                "will be automatically populated wherever possible."
            )
        )

        @qt.Slot(None)
        def newResourceClicked():
            dialog = ResourceEditorDialogue(
                cohort=self._cohort, task_config=self._task_config
            )
            if dialog.exec():
                # Without this, the cells rapidly bloat for some reason
                cohortWidget.tableView.resizeColumnsToContents()
                cohortWidget.tableView.resizeRowsToContents()
        newResourceButton.clicked.connect(newResourceClicked)
        self._to_disconnect.append(newResourceButton.clicked)

        # Drop Cases (Rows) + Drop Resources (Columns) Buttons
        dropCasesButton = qt.QPushButton(_("Drop Case(s) [Rows]"))
        dropCasesButton.setToolTip(
            _(
                "Drop the selected case(s) in the cohort. THIS CANNOT BE UNDONE!"
            )
        )

        @qt.Slot(None)
        def dropCasesClicked():
            # Prompt the user to confirm this is what they want to do
            msg = qt.QMessageBox()
            msg.setWindowTitle("Are you sure?")
            case_names = list({
                self._cohort.indices[idx.row()]
                for idx in cohortWidget.selectedIndices
            })
            case_points = "\n".join(["  * " + c for c in case_names])
            msg.setText(
                "You are about to delete the following cases:\n"
                f"{case_points}\n"
                f"Are you sure?"
            )
            msg.setStandardButtons(qt.QMessageBox.Yes | qt.QMessageBox.No)
            # Only apply the deletion if confirmed by the user
            if msg.exec() == qt.QMessageBox.Yes:
                self._cohort.drop_cases(case_names)
        dropCasesButton.clicked.connect(dropCasesClicked)
        self._to_disconnect.append(dropCasesButton.clicked)

        dropResourcesButton = qt.QPushButton(_("Drop Resource(s) [Columns]"))
        dropResourcesButton.setToolTip(
            _("Drop the selected resource(s) in the cohort. THIS CANNOT BE UNDONE!")
        )

        @qt.Slot(None)
        def dropResourcesClicked():
            # Prompt the user to confirm this is what they want to do
            msg = qt.QMessageBox()
            msg.setWindowTitle("Are you sure?")
            resource_names = list({
                self._cohort.header[idx.column()]
                for idx in cohortWidget.selectedIndices
            })
            resource_points = "\n".join(["  * " + c for c in resource_names])
            msg.setText(
                "You are about to delete the following resources:\n"
                f"{resource_points}\n"
                f"Are you sure?"
            )
            msg.setStandardButtons(qt.QMessageBox.Yes | qt.QMessageBox.No)
            # Only apply the deletion if confirmed by the user
            if msg.exec() == qt.QMessageBox.Yes:
                self._cohort.drop_filters(resource_names)
        dropResourcesButton.clicked.connect(dropResourcesClicked)
        self._to_disconnect.append(dropResourcesButton.clicked)

        buttonPanel = qt.QGridLayout()
        buttonPanel.addWidget(newCaseButton, 0, 0)
        buttonPanel.addWidget(newResourceButton, 0, 1)
        buttonPanel.addWidget(dropCasesButton, 1, 0)
        buttonPanel.addWidget(dropResourcesButton, 1, 1)
        layout.addLayout(buttonPanel)

    def closeEvent(self, event):
        # Confirm that the user wants to reject any changes they made first
        if self.confirmReject():
            event.accept()
        # Otherwise, boot them back
        else:
            event.ignore()

    def confirmReject(self) -> bool:
        # If we have changed anything, confirm we want to exit first
        if self._cohort.has_changed:
            reply = qt.QMessageBox.question(
                self,
                "Are you sure?",
                "If you close now, any changes made will be lost. Do you want to proceed?",
                qt.QMessageBox.Yes | qt.QMessageBox.No,
                qt.QMessageBox.No,
            )
            return reply == qt.QMessageBox.Yes
        # Otherwise always proceed (as there's nothing to be lost)
        return True

    def disconnectAll(self):
        for v in self._to_disconnect:
            v.disconnect()


class ResourceEditorDialogue(ChangeTrackingDialogue):

    def __init__(
        self,
        cohort: CohortModel,
        resource_name: str = None,
        task_config: "Optional[DictBackedConfig]" = None,
        parent: qt.QObject = None,
    ):
        """
        Dialog for editing (or creating) new resources within a cohort.

        :param cohort: The Cohort to apply the edits to
        :param resource_name: The name of the resource (within the cohort CSV) to edit.
            If None, will create a resource with the user specified name instead.
        :param task_config: A (parent-less!) task config that the resource this dialog
            is managing should reference and modify.
        :param parent: Parent widget, as required by QT.
        """
        # If the cohort is not editable, reject attempts to edit it
        if not cohort.is_editable():
            raise ValueError("Cannot edit a un-editable Cohort!")

        # Initial setup
        super().__init__(parent)
        self.setSizePolicy(qt.QSizePolicy.Preferred, qt.QSizePolicy.Minimum)

        # Backing cohort model
        self._cohort = cohort

        # Track the previous resource's details (if any)
        self._prior_resource_name = resource_name
        self._prior_resource = None
        if resource_name is not None:
            self._prior_resource = cohort.resource_map.get(resource_name)

        # Track the task config for later
        self.task_config = task_config

        # Cached map of the resource types for this provided task
        duf = cohort.reference_task.getDataUnitFactory()
        self._resource_type_map = {v.pretty_name: v for v in duf.resource_types().values()}

        # Initial setup
        if resource_name:
            pretty_name = cohort.csv_to_pretty(resource_name)
            self.setWindowTitle(_(f"Editing Resource '{pretty_name}'"))
        else:
            self.setWindowTitle(_("Add New Resource"))
        self.setMinimumSize(500, self.minimumHeight)
        layout = qt.QFormLayout(self)

        # The resource name itself (prior to formatting)
        nameLabel = qt.QLabel(_("Resource Name:"))
        nameField = qt.QLineEdit()
        if resource_name:
            nameField.setText(cohort.csv_to_original(resource_name))
        nameField.setPlaceholderText(_("e.g. disk_labels, spinal_T2w, liver_segmentation"))
        nameTooltip = _(
            "The name you'd like this resource to have. "
            "This can be anything you'd like; just don't use any commas."
        )
        nameLabel.setToolTip(nameTooltip)
        nameField.setToolTip(nameTooltip)
        layout.addRow(nameLabel, nameField)
        nameField.textChanged.connect(self.mark_changed)
        self.nameField = nameField

        # Other input fields
        includeLabel = qt.QLabel(_("Include:"))
        includeField = qt.QLineEdit()
        if resource_name:
            include_vals = self._cohort.resource_map.get(resource_name, {}).get(
                CohortModel.FILTER_INCLUDE_KEY, []
            )
            includeField.setText(", ".join(include_vals))
        includeTooltip = _(
            "Comma-separated elements that a file MUST have to be used for this resource. "
            "This incudes the directory the file is contained within!"
        )
        includeLabel.setToolTip(includeTooltip)
        includeField.setToolTip(includeTooltip)
        includeField.setPlaceholderText(_("e.g. T1w, nii, lesion_seg"))
        self.includeField = includeField
        layout.addRow(includeLabel, includeField)

        excludeLabel = qt.QLabel(_("Exclude:"))
        excludeField = qt.QLineEdit()
        if resource_name:
            exclude_vals = self._cohort.resource_map.get(resource_name, {}).get(
                CohortModel.FILTER_EXCLUDE_KEY, []
            )
            excludeField.setText(", ".join(exclude_vals))
        excludeTooltip = _(
            "Comma-separated elements that a file MUST NOT have to be used for this resource. "
            "This incudes the directory the file is contained within!"
        )
        excludeLabel.setToolTip(excludeTooltip)
        excludeField.setToolTip(excludeTooltip)
        excludeField.setPlaceholderText(_("e.g. derivatives, masked, brain"))
        self.excludeField = excludeField
        layout.addRow(excludeLabel, excludeField)

        includeField.textChanged.connect(self.mark_changed)
        excludeField.textChanged.connect(self.mark_changed)

        # Field type selection GUI
        self._generate_field_type_gui(layout)

        # Container widget to hold the resource-specific task GUI
        self.taskConfigBox: qt.QWidget = qt.QWidget(self)
        self.rebuild_task_config_gui()
        self.resourceTypeSelector.currentIndexChanged.connect(self.rebuild_task_config_gui)
        layout.addRow(self.taskConfigBox)

        # Ok/Cancel Buttons
        buttonBox = qt.QDialogButtonBox()
        buttonBox.setStandardButtons(
            qt.QDialogButtonBox.Ok | qt.QDialogButtonBox.Cancel
        )

        @qt.Slot(qt.QPushButton)
        def onButtonClicked(button: qt.QPushButton):
            button_role = buttonBox.buttonRole(button)
            if button_role == qt.QDialogButtonBox.RejectRole:
                self.reject()
            elif button_role == qt.QDialogButtonBox.AcceptRole:
                # Attempt to apply the requested changes before closing
                if self.apply_changes():
                    self.accept()
            else:
                raise ValueError("Pressed a button with an invalid role!")
        buttonBox.clicked.connect(onButtonClicked)

        # Add it to the layout w/ a spacer to force it to the bottom
        stretch = qt.QWidget(self)
        stretch.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Expanding)
        layout.addWidget(stretch)
        layout.addWidget(buttonBox)

    def _generate_field_type_gui(self, layout: "qt.QFormLayout"):
        # Resource type selector and description
        resourceTypeLabel = qt.QLabel(_("Resource Type:"))
        resourceTypeSelector = qt.QComboBox(None)
        resourceTypeSelector.addItems(list(self._resource_type_map.keys()))
        resourceTypeToolTip = _(
            "The resource type for this column."
            "\n\n"
            "Most tasks will use the name of each resource to determine "
            "how to process the corresponding resource for each case; "
            "selecting the correct resource type ensures the task can "
            "do so successfully."
        )
        resourceTypeLabel.setToolTip(resourceTypeToolTip)
        resourceTypeSelector.setToolTip(resourceTypeToolTip)
        layout.addRow(resourceTypeLabel, resourceTypeSelector)

        # Add it to the overall layout
        layout.addRow(resourceTypeLabel, resourceTypeSelector)

        # Description for the selected resource to help inform the user
        resourceTypeDescriptionBox = ctk.ctkCollapsibleGroupBox()
        resourceTypeDescriptionBox.setTitle(_("Type Description"))
        resourceTypeDescriptionBoxLayout = qt.QVBoxLayout()
        resourceTypeDescriptionBox.setLayout(resourceTypeDescriptionBoxLayout)
        default_description = _(
            "A description of the selected resource type will appear here"
        )
        resourceTypeDescription = qt.QLabel(default_description)
        resourceTypeDescription.setWordWrap(True)
        resourceTypeDescriptionBoxLayout.addWidget(resourceTypeDescription)

        @qt.Slot(str)
        def syncDescriptionText(__: str):
            new_type = self.resource_type
            if new_type is None:
                resourceTypeDescription.setText(default_description)
            else:
                resourceTypeDescription.setText(new_type.description)
            self.mark_changed()

        resourceTypeSelector.currentIndexChanged.connect(syncDescriptionText)

        # Track the resource selector for later
        self.resourceTypeSelector = resourceTypeSelector

        # Disable resource-type widgets for tasks which do not specify resource types
        if len(self._resource_type_map) < 2:
            resourceTypeSelector.setEnabled(False)
            resourceTypeDescriptionBox.setEnabled(False)
            disabledToolTip = _("The selected task did specify multiple resource types.")
            resourceTypeSelector.setToolTip(disabledToolTip)
            resourceTypeDescriptionBox.setToolTip(disabledToolTip)

        # Add it to the layout
        layout.addRow(resourceTypeDescriptionBox)

        # Match the selected resource type to the previous resource type (if possible)
        if self._prior_resource is not None:
            prior_type_id = self._prior_resource.get(self._cohort.RESOURCE_TYPE_KEY)
            if prior_type_id is None:
                resourceTypeSelector.setCurrentIndex(-1)
            else:
                duf = self._cohort.reference_task.getDataUnitFactory()
                prior_type = duf.resource_types().get(prior_type_id)
                if prior_type is None:
                    resourceTypeSelector.setCurrentIndex(-1)
                else:
                    resourceTypeSelector.setCurrentText(prior_type.pretty_name)
        else:
            resourceTypeSelector.setCurrentIndex(-1)

    def rebuild_task_config_gui(self):
        # If we don't have a valid resource type, or no GUI exists for it, hide our config GUI
        if (
            self.resource_type is None
            or (config_layout := self.resource_type.buildConfigGUI(self.task_config))
            is None
        ):
            # Hide the widget
            self.taskConfigBox.setVisible(False)
        # Otherwise, replace the previous GUI layout with the corresponding one for this new resource
        else:
            # Make the configuration box visible and expand it, if it was not already
            self.taskConfigBox.setVisible(True)

            # Replace the layout in the dropdown w/ this new one
            if self.taskConfigBox.layout() is not None:
                tmp = qt.QWidget(None)
                tmp.setLayout(self.taskConfigBox.layout())
                del tmp

            # Use our new layout in its place
            self.taskConfigBox.setLayout(config_layout)

    def apply_changes(self):
        # Only run the (relatively) expensive update if something has changed
        if not self._has_changed:
            return True

        # Make sure a resource of this name doesn't already exist
        base_str = self.nameField.text.strip()
        csv_str = self.resource_type.format_for_csv(base_str)
        pretty_str = self.resource_type.format_for_gui(base_str)
        if csv_str != self._prior_resource_name and csv_str in self._cohort.resource_map.keys():
            # If it does, show an error and return "False" (no changes made)
            qt.QMessageBox.critical(
                None,
                "Invalid Resource Name",
                f"'Resource of name {pretty_str}' ({csv_str}) already exists; "
                f"please change this resource's name or type to make it unique.",
                qt.QMessageBox.Ok,
            )
            return False

        # Parse the contents of our GUI elements, stripping leading/trailing whitespace
        # TODO: Replace "pretty string" with the resource type ID after other uses have been handled
        filter_entry: dict = {
            CohortModel.ORIGINAL_NAME_KEY: base_str,
            CohortModel.RESOURCE_TYPE_KEY: self.resource_type.id,
            CohortModel.FILTER_INCLUDE_KEY: [
                s.strip() for s in self.includeField.text.split(",")
            ],
            CohortModel.FILTER_EXCLUDE_KEY: [
                s.strip() for s in self.excludeField.text.split(",")
            ],
        }

        # Clean up "blank" filters which may have slipped through
        filter_entry[CohortModel.FILTER_INCLUDE_KEY] = [
            x for x in filter_entry[CohortModel.FILTER_INCLUDE_KEY] if x != ""
        ]
        filter_entry[CohortModel.FILTER_EXCLUDE_KEY] = [
            x for x in filter_entry[CohortModel.FILTER_EXCLUDE_KEY] if x != ""
        ]

        # If this an updated resource, rename the resource to this new name
        if self._prior_resource is not None:
            self._cohort.rename_filter(self._prior_resource_name, csv_str)

        # Update cohort to use the new filter
        self._cohort.set_resource_data(csv_str, filter_entry)

        # Signal that everything ran successfully
        return True

    @property
    def resource_type(self) -> "Optional[ResourceType]":
        current_text = self.resourceTypeSelector.currentText.strip()
        resource_type = self._resource_type_map.get(current_text)
        return resource_type

    @resource_type.setter
    def resource_type(self, new_type: "ResourceType"):
        # Make sure the provided resource type is one recognized by our mapping
        if new_type not in self._resource_type_map.values():
            raise ValueError(
                f"Resource type {new_type.pretty_name} is not a valid type for the selected data unit."
            )
        # Update our GUI (and everything else that follows) to match
        self.resourceTypeSelector.setCurrentText(new_type.pretty_name)


class CaseEditorDialog(ChangeTrackingDialogue):
    def __init__(self, cohort: CohortModel, case_id: str = None, parent: qt.QObject = None):
        """
        Dialog for editing (or creating) new resources within a cohort.

        :param cohort: The Cohort to apply the edits to
        :param case_id: The name of the case to edit. If None, will create a resource with
            the user specified name instead.
        :param parent: Parent widget, as required by QT.
        """
        super().__init__(parent)

        # If the cohort is not editable, reject attempts to edit it
        if not cohort.is_editable():
            raise ValueError("Cannot edit a un-editable Cohort!")

        # Backing cohort manager
        self._cohort = cohort

        # Reference resource name
        self._reference_case = case_id

        # Nested signals which need to be disconnected to avoid a memory leak
        self._nested_connections = []

        # Initial setup
        if case_id:
            self.setWindowTitle(_(f"Editing Case '{case_id}'"))
        else:
            self.setWindowTitle(_("Add New Case"))
        self.setMinimumSize(500, self.minimumHeight)
        layout = qt.QFormLayout(self)

        # Name Field
        nameLabel = qt.QLabel(_("Case Name:"))
        nameField = qt.QLineEdit()
        if case_id:
            nameField.setText(case_id)
        nameField.setPlaceholderText(_("e.g. sub-001, sub001_ses002"))
        nameField.textChanged.connect(self.mark_changed)
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
        searchPathList = qt.QListWidget(None)
        if case_id:
            path_entries = cohort.case_map.get(case_id, [])
            for p in path_entries:
                if p.is_absolute():
                    searchPathList.addItem(str(p))
                else:
                    searchPathList.addItem(str(cohort.data_path / p))

        model = searchPathList.model()
        model.rowsInserted.connect(self.mark_changed)
        model.rowsRemoved.connect(self.mark_changed)
        layout.addRow(searchPathLabels)
        layout.addRow(searchPathList)
        self.searchPathList = searchPathList
        self._nested_connections.append(model.rowsInserted)
        self._nested_connections.append(model.rowsRemoved)

        # Button panel
        addButton = qt.QPushButton("Add")
        removeButton = qt.QPushButton("Remove")
        removeButton.setEnabled(False)

        def onAddClicked():
            fileDialog = qt.QFileDialog(None)
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
        w = qt.QWidget(None)
        l = qt.QHBoxLayout(w)
        l.addWidget(addButton)
        l.addWidget(removeButton)
        layout.addRow(w)

        self._nested_connections.append(addButton.clicked)
        self._nested_connections.append(removeButton.clicked)

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
                # Apply the requested changes to the cohort before closing.
                if self.apply_changes():
                    self.accept()
            else:
                raise ValueError("Pressed a button with an invalid role!")

        buttonBox.clicked.connect(onButtonClicked)
        layout.addWidget(buttonBox)

    def apply_changes(self):
        # Only run the (relatively) expensive update if something has changed
        if not self._has_changed:
            return True

        # Make sure a case with this name doesn't already exist
        label = self.nameField.text.strip()
        if self._reference_case is None and label in self._cohort.case_map.keys():
            # If it does, show an error and return "False" (no changes made)
            qt.QMessageBox.critical(
                None,
                "Invalid Case Name",
                f"A case with the name '{label}' already exists; please change it to be unique.",
                qt.QMessageBox.Ok,
            )
            return False

        # Parse the contents of our GUI elements, stripping leading/trailing whitespace
        search_paths: list[Path] = []
        for i in range(self.searchPathList.count):
            p = Path(self.searchPathList.item(i).text())
            if self._cohort.data_path in p.parents:
                search_paths.append(p.relative_to(self._cohort.data_path))
            else:
                search_paths.append(p)

        # If this is an updated case, rename it to match
        if self._reference_case:
            self._cohort.rename_case(self._reference_case, label)

        # Insert it into our cohort
        self._cohort.set_case_data(label, search_paths)

        # Confirm that the changes went through
        return True

    def _disconnectAll(self):
        super()._disconnectAll()
        for c in self._nested_connections:
            c.disconnect()
