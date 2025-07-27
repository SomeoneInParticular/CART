import csv
import traceback
from pathlib import Path
from typing import *
from collections import defaultdict
import re
import shutil


import vtk
import ctk
import qt
import slicer
from slicer import vtkMRMLScalarVolumeNode
from slicer.ScriptedLoadableModule import *
from slicer.i18n import tr as _
from slicer.util import VTKObservationMixin
class CohortGeneratorWindow(qt.QDialog):
    """GUI to display a 2D array and toggle rows/columns."""
    def __init__(self, data_path, parent=None):
        super().__init__(parent)

        # Flag to check if the auto-generated cohort gets accepted, for widget use
        self.is_cohort_accepted = False

        ### UI ###

        self.setWindowTitle("Cohort Configuration")
        self.logic = CohortGeneratorLogic(data_path)
        self.setMinimumSize(800, 500) # Increased size for better viewing

        # --- Colors for visual state ---
        self.palette = self.palette
        self.disabled_color = qt.QColor(qt.Qt.gray)
        self.enabled_color = self.palette.color(qt.QPalette.Base) # Default background

        # --- Main Layout ---
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10) # Added margins for aesthetics

        # --- Table Widget ---
        self.table_widget = qt.QTableWidget()
        layout.addWidget(self.table_widget)

        # --- Add spacing between table and buttons ---
        layout.addSpacing(15)

        # --- Buttons ---
        button_layout = qt.QHBoxLayout()
        self.apply_button = qt.QPushButton("Apply")
        self.cancel_button = qt.QPushButton("Cancel")

        # --- Add styling to buttons for a nicer look ---
        self.apply_button.setDefault(True)
        self.apply_button.setStyleSheet("padding: 5px 15px;")
        self.cancel_button.setStyleSheet("padding: 5px 15px;")

        button_layout.addStretch()
        button_layout.addWidget(self.apply_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

        # --- Populate and Connect ---
        self._populate_table()
        self._configure_table_sizing() # New method for sizing
        self._connect_signals()

    def _populate_table(self):
        """Fills the table with data and control checkboxes."""
        data = self.logic.cohort_data
        if not data or not data[0]:
             self.table_widget.setRowCount(0)
             self.table_widget.setColumnCount(0)
             return

        header_row = data[0]
        data_rows = data[1:]

        self.table_widget.setColumnCount(len(header_row) + 1)
        self.table_widget.setRowCount(len(data_rows) + 2)

        # Set headers (in the table itself, not the header widget)
        # Leave cell (0,0) blank
        for c, header_text in enumerate(header_row):
             item = qt.QTableWidgetItem(header_text)
             item.setFlags(item.flags() & ~qt.Qt.ItemIsEditable)
             item.setTextAlignment(qt.Qt.AlignCenter)
             self.table_widget.setItem(1, c + 1, item)

        # --- Create Checkboxes for the first column (case controls) ---
        for r in range(1, len(data_rows)):
            self._create_checkbox(r + 1, 0, self.handle_row_toggle)

        # --- Create Checkboxes for the first row (resource controls) ---
        for c in range(1, len(header_row)):
            self._create_checkbox(0, c + 1, self.handle_column_toggle)

        # --- Fill data cells ---
        for r, row_data in enumerate(data_rows):
            for c, cell_value in enumerate(row_data):
                item = qt.QTableWidgetItem(str(cell_value))
                item.setFlags(item.flags() & ~qt.Qt.ItemIsEditable) # Make read-only
                self.table_widget.setItem(r + 2, c + 1, item)

    def _configure_table_sizing(self):
        """Adjusts column widths for better readability and to fill space."""
        header = self.table_widget.horizontalHeader()
        header.hide() # Hide default header, as we put headers in the table
        self.table_widget.verticalHeader().hide()

        # Column 0 (row checkboxes): Resize to fit the content snugly.
        self.table_widget.setColumnWidth(0, 40)

        # Column 1 ('uid'): Resize to fit the content.
        self.table_widget.resizeColumnToContents(1)

        # Columns 2 onwards: Stretch to fill the remaining available width.
        for col_idx in range(2, self.table_widget.columnCount):
            header.setSectionResizeMode(col_idx, qt.QHeaderView.Stretch)

    def _create_checkbox(self, row, col, handler_slot):
        """Helper to create and place a checkbox in the table."""
        # A container widget is needed to center the checkbox
        cell_widget = qt.QWidget()
        layout = qt.QHBoxLayout(cell_widget)
        layout.setAlignment(qt.Qt.AlignCenter)
        layout.setContentsMargins(0,0,0,0)

        checkbox = qt.QCheckBox()
        checkbox.setChecked(True)
        checkbox.toggled.connect(lambda state, r=row, c=col: handler_slot(r, c, not state))

        layout.addWidget(checkbox)
        self.table_widget.setCellWidget(row, col, cell_widget)

    def _connect_signals(self):
        """Connect button signals to dialog actions."""
        self.apply_button.clicked.connect(self.on_apply)
        self.cancel_button.clicked.connect(self.reject)

    def handle_row_toggle(self, row, col, is_disabled):
        """Handles a click on a row-control checkbox."""
        data_row_index = row - 1 # Adjust for header row in data model
        self.logic.toggle_row(data_row_index, is_disabled)
        self._update_row_visuals(row, is_disabled)

    def handle_column_toggle(self, row, col, is_disabled):
        """Handles a click on a column-control checkbox."""
        # This function is not connected as column toggles were removed for clarity
        # but the logic is kept if you wish to re-implement it.
        data_col_index = col - 1
        self.logic.toggle_column(data_col_index, is_disabled)
        self._update_column_visuals(col, is_disabled)

    def _update_row_visuals(self, table_row, is_disabled):
        """Grays out or illuminates an entire row."""
        color = self.disabled_color if is_disabled else self.enabled_color
        for col in range(1, self.table_widget.columnCount):
            self.table_widget.item(table_row, col).setBackground(color)

    def _update_column_visuals(self, table_col, is_disabled):
        """Grays out or illuminates an entire column."""
        color = self.disabled_color if is_disabled else self.enabled_color
        for row in range(1, self.table_widget.rowCount):
            self.table_widget.item(row, table_col).setBackground(color)

    def on_apply(self):
        """Calls the logic's apply method and accepts the dialog."""
        self.logic.apply_changes()
        self.accept()


class CohortGeneratorLogic:
    """Handles the data and state for contrast selection."""
    def __init__(self, data_path):
        self.data_path: Path = data_path
        self.cohort_data = self.load_cohort_data(self.data_path)
        self.disabled_rows = []
        self.disabled_columns = []
        self.is_accepted = False

        # Generated
        self.cohort_path: Path = None

    def load_cohort_data(self, data_path: Path) -> List[List[str]]:
        """
        Recursively scans a directory to create a 2D array of subjects and their
        associated file resources using pathlib.
        """
        root_path = Path(data_path).resolve()
        if not root_path.is_dir():
            print(f"Warning: Provided path '{data_path}' is not a valid directory. Returning empty.")
            return []

        subjects_data = {}
        all_resource_keys = set()

        for current_path in root_path.rglob('*'):
            if current_path.is_dir():
                files = [f for f in current_path.iterdir() if f.is_file()]
                subdirs = [d for d in current_path.iterdir() if d.is_dir()]

                if files and not subdirs:
                    subject_id = current_path.relative_to(root_path).as_posix()
                    resource_map = {}
                    for file_path in files:
                        try:
                            resource_key = re.split(r'[_.-]+', file_path.stem)[-1]
                            resource_map[resource_key] = "/".join(file_path.parts[-2:])
                            all_resource_keys.add(resource_key)
                        except IndexError:
                            print(f"Warning: Could not parse resource key from filename: {file_path.name}")
                            continue
                    if resource_map:
                        subjects_data[subject_id] = resource_map
        if not subjects_data:
            return []

        sorted_headers = sorted(list(all_resource_keys))
        header_row = ['uid'] + sorted_headers
        cohort_data = [header_row]

        for subject_id in sorted(subjects_data.keys()):
            row = [subject_id]
            resources = subjects_data[subject_id]
            for resource_key in sorted_headers:
                row.append(resources.get(resource_key, ''))
            cohort_data.append(row)
        return cohort_data

    def toggle_row(self, row_index, is_disabled):
        """Adds or removes a row index from the disabled list."""
        if is_disabled and row_index not in self.disabled_rows:
            self.disabled_rows.append(row_index)
        elif not is_disabled and row_index in self.disabled_rows:
            self.disabled_rows.remove(row_index)

    def toggle_column(self, col_index, is_disabled):
        """Adds or removes a column index from the disabled list."""
        if is_disabled and col_index not in self.disabled_columns:
            self.disabled_columns.append(col_index)
        elif not is_disabled and col_index in self.disabled_columns:
            self.disabled_columns.remove(col_index)

    def apply_changes(self):
        """Marks the action as accepted."""
        self.is_accepted = True

        # Update cohort data to match unwanted rows or columns
        row_count, col_count = len(self.cohort_data), len(self.cohort_data[0])

        for disabled_row in self.disabled_rows:
            self.cohort_data[disabled_row - 1] = col_count * ['']

        for disabled_col in self.disabled_columns:
            for row in range(row_count):
                self.cohort_data[row][disabled_col - 1] = ''

        # Create a CSV file using the cohort data and use it as cohort file
        dir_path = Path(self.data_path / "code")
        dir_path.mkdir(parents=True, exist_ok=True)

        self.cohort_path = Path(dir_path / "cohort.csv")

        with open(self.cohort_path, 'w', newline='') as csvfile:
            csv_writer = csv.writer(csvfile)
            csv_writer.writerows(self.cohort_data)

        self.is_accepted = True

        print(f"Applying changes. Disabled Rows: {self.disabled_rows}, Disabled Columns: {self.disabled_columns}")


