import csv
import traceback
from pathlib import Path
from typing import Optional

import vtk
import ctk
import qt
import slicer
from slicer import vtkMRMLScalarVolumeNode
from slicer.ScriptedLoadableModule import *
from slicer.i18n import tr as _
from slicer.util import VTKObservationMixin

from CARTLib.utils.config import config
from CARTLib.core.DataManager import DataManager
from CARTLib.core.DataUnitBase import DataUnitBase
from CARTLib.core.TaskBaseClass import TaskBaseClass, DataUnitFactory

CURRENT_DIR = Path(__file__).parent
CONFIGURATION_FILE_NAME = CURRENT_DIR / "configuration.json"
sample_data_path = CURRENT_DIR.parent / "sample_data"
sample_data_cohort_csv = sample_data_path / "example_cohort.csv"


class CohortGeneratorWindow(qt.QDialog):
    """GUI to display a 2D array and toggle rows/columns."""
    def __init__(self, data_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Iteration Configuration")
        self.logic = CohortGeneratorLogic(data_path)
        self.setMinimumSize(600, 400)

        # --- Colors for visual state ---
        self.disabled_color = qt.QColor(qt.Qt.gray)
        self.enabled_color = self.palette.color(qt.QPalette.Base) # Default background

        # --- Main Layout ---
        layout = qt.QVBoxLayout(self)

        # --- Table Widget ---
        self.table_widget = qt.QTableWidget()
        layout.addWidget(self.table_widget)

        # --- Buttons ---
        button_layout = qt.QHBoxLayout()
        self.apply_button = qt.QPushButton("Apply")
        self.cancel_button = qt.QPushButton("Cancel")
        button_layout.addStretch()
        button_layout.addWidget(self.apply_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

        # --- Populate and Connect ---
        self._populate_table()
        self._connect_signals()

    def _populate_table(self):
        """Fills the table with data and control checkboxes."""
        data = self.logic.csv_data
        num_data_rows = len(data)
        num_data_cols = len(data[0]) if num_data_rows > 0 else 0

        self.table_widget.setRowCount(num_data_rows + 1)
        self.table_widget.setColumnCount(num_data_cols + 1)

        # --- Create Checkboxes for the first row and column ---
        for r in range(num_data_rows):
            self._create_checkbox(r + 1, 0, self.handle_row_toggle)

        for c in range(num_data_cols):
            self._create_checkbox(0, c + 1, self.handle_column_toggle)

        # --- Fill data cells ---
        for r, row_data in enumerate(data):
            for c, cell_value in enumerate(row_data):
                item = qt.QTableWidgetItem(str(cell_value))
                item.setFlags(item.flags() & ~qt.Qt.ItemIsEditable) # Make read-only
                self.table_widget.setItem(r + 1, c + 1, item)

    def _create_checkbox(self, row, col, handler_slot):
        """Helper to create and place a checkbox in the table."""
        checkbox = qt.QCheckBox()
        checkbox.setStyleSheet("margin-left: 50%; margin-right: 50%;") # Center checkbox
        checkbox.setChecked(True)
        checkbox.toggled.connect(lambda state, r=row, c=col: handler_slot(r, c, not state))
        self.table_widget.setCellWidget(row, col, checkbox)

    def _connect_signals(self):
        """Connect button signals to dialog actions."""
        self.apply_button.clicked.connect(self.on_apply)
        self.cancel_button.clicked.connect(self.reject)

    def handle_row_toggle(self, row, col, is_disabled):
        """Handles a click on a row-control checkbox."""
        data_row_index = row - 1
        self.logic.toggle_row(data_row_index, is_disabled)
        self._update_row_visuals(row, is_disabled)

    def handle_column_toggle(self, row, col, is_disabled):
        """Handles a click on a column-control checkbox."""
        data_col_index = col - 1
        self.logic.toggle_column(data_col_index, is_disabled)
        self._update_column_visuals(col, is_disabled)

    def _update_row_visuals(self, table_row, is_disabled):
        """Grays out or illuminates an entire row."""
        color = self.disabled_color if is_disabled else self.enabled_color
        for col in range(1, self.table_widget.columnCount()):
            self.table_widget.item(table_row, col).setBackground(color)

    def _update_column_visuals(self, table_col, is_disabled):
        """Grays out or illuminates an entire column."""
        color = self.disabled_color if is_disabled else self.enabled_color
        for row in range(1, self.table_widget.rowCount()):
            self.table_widget.item(row, table_col).setBackground(color)

    def on_apply(self):
        """Calls the logic's apply method and accepts the dialog."""
        self.logic.apply_changes()
        self.accept()

class CohortGeneratorLogic:
    """Handles the data and state for contrast selection."""
    def __init__(self, data_path):
        self.data_path: Path = data_path

        self.csv_data = self.load_csv_data(self.data_path)

        self.disabled_rows = []
        self.disabled_columns = []
        self.is_accepted = False

    def load_csv_data(self, file_path):
        """
        """
        csv_data = []
        with open(file_path, 'r', newline='', encoding='utf-8') as csvfile:
            csv_reader = csv.reader(csvfile)
            for row in csv_reader:
                csv_data.append(row)
        return csv_data

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
        print(f"Applying changes. Disabled Rows: {self.disabled_rows}, Disabled Columns: {self.disabled_columns}")


# --- Example of how to run this inside a Slicer module ---
#
# # Example 2D array data
# sample_data = [
#     [f"T1_Sub{i:02}" for i in range(1, 6)],
#     [f"T2_Sub{i:02}" for i in range(1, 6)],
#     [f"FLAIR_Sub{i:02}" for i in range(1, 6)],
# ]
#
# window = ContrastSelectionWindow(data=sample_data)
#
# # Use exec_() to make the dialog modal
# if window.exec_() == qt.QDialog.Accepted:
#     print("Dialog was accepted.")
#     print("Final Disabled Rows:", window.logic.disabled_rows)
#     print("Final Disabled Columns:", window.logic.disabled_columns)
# else:
#     print("Dialog was canceled.")