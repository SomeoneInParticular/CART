import csv
from pathlib import Path
from typing import *
import re

import qt
from slicer.i18n import tr as _

class CohortGeneratorWindow(qt.QDialog):
    """GUI to display and configure a cohort from a data directory."""
    def __init__(self, data_path, parent=None):
        super().__init__(parent)
        self.logic = CohortGeneratorLogic(data_path)
        self.setWindowFlags(self.windowFlags() | qt.Qt.WindowMaximizeButtonHint | qt.Qt.WindowMinimizeButtonHint | qt.Qt.Window)

        # Make dialog/window non-modal, to allow interaction with main window
        self.setModal(False)

        self.build_ui()
        self.connect_signals()
        self.update_ui_from_logic()

    def build_ui(self):
        self.setWindowTitle("Cohort Generator and Editor")
        self.setMinimumSize(900, 700)
        layout = qt.QVBoxLayout(self)

        self.table_widget = qt.QTableWidget()
        layout.addWidget(self.table_widget)

        controls_layout = qt.QHBoxLayout()
        controls_layout.addWidget(self.build_load_options_groupbox())
        controls_layout.addWidget(self.build_filtering_groupbox(), 1)
        layout.addLayout(controls_layout)

        button_layout = qt.QHBoxLayout()
        self.apply_button = qt.QPushButton("Save and Apply")
        self.cancel_button = qt.QPushButton("Cancel")
        button_layout.addStretch()
        button_layout.addWidget(self.apply_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

    def build_load_options_groupbox(self):
        groupbox = qt.QGroupBox("Load Options")
        layout = qt.QFormLayout(groupbox)
        self.excluded_ext_input = qt.QLineEdit(".json, .py")
        self.excluded_ext_input.toolTip = "Comma-separated list of file extensions to ignore."
        self.rescan_button = qt.QPushButton("Rescan Data Path")
        layout.addRow("Exclude Extensions:", self.excluded_ext_input)
        layout.addRow(self.rescan_button)
        return groupbox

    def build_filtering_groupbox(self):
        groupbox = qt.QGroupBox("Column Filtering")
        layout = qt.QFormLayout(groupbox)
        self.include_input = qt.QLineEdit()
        self.include_input.setPlaceholderText("e.g., T1w, nifti")
        self.exclude_input = qt.QLineEdit()
        self.exclude_input.setPlaceholderText("e.g., masked, brain")
        self.target_column_combo = qt.QComboBox()
        self.new_column_name_input = qt.QLineEdit()
        self.apply_filter_button = qt.QPushButton("Apply Filter")

        layout.addRow("Files MUST Contain:", self.include_input)
        layout.addRow("Files MUST NOT Contain:", self.exclude_input)
        layout.addRow("Target Column:", self.target_column_combo)
        layout.addRow("New Column Name:", self.new_column_name_input)
        layout.addWidget(self.apply_filter_button)
        return groupbox

    def update_ui_from_logic(self):
        self.populate_table()
        self.update_column_combo()

    def populate_table(self):
        self.table_widget.blockSignals(True)
        self.table_widget.clear()
        data = self.logic.cohort_data
        if not data:
            self.table_widget.setRowCount(0)
            self.table_widget.setColumnCount(0)
            self.table_widget.blockSignals(False)
            return

        headers = self.logic.get_headers()
        num_rows = len(data)
        num_cols = len(headers)
        self.table_widget.setRowCount(num_rows)
        self.table_widget.setColumnCount(num_cols + 1)
        self.table_widget.setHorizontalHeaderLabels([""] + headers)

        for c_idx in range(num_cols):
            self._create_checkbox(0, c_idx + 1, self.handle_column_toggle, self.logic.is_column_enabled(c_idx), is_header=True)

        for r_idx in range(num_rows):
            self._create_checkbox(r_idx, 0, self.handle_row_toggle, self.logic.is_row_enabled(r_idx))
            for c_idx, header in enumerate(headers):
                item = qt.QTableWidgetItem(str(data[r_idx].get(header, '')))
                item.setFlags(qt.Qt.ItemIsEnabled | qt.Qt.ItemIsSelectable)
                self.table_widget.setItem(r_idx, c_idx + 1, item)

        self.table_widget.resizeColumnsToContents()
        self.table_widget.verticalHeader().setVisible(False)
        self.table_widget.horizontalHeader().setSectionResizeMode(qt.QHeaderView.Interactive)
        self.update_all_visuals()
        self.table_widget.blockSignals(False)

    def _create_checkbox(self, row, col, handler, is_checked, is_header=False):
        cell_widget = qt.QWidget()
        layout = qt.QHBoxLayout(cell_widget)
        layout.setAlignment(qt.Qt.AlignCenter)
        layout.setContentsMargins(0, 0, 0, 0)
        checkbox = qt.QCheckBox()
        checkbox.setChecked(is_checked)

        layout.addWidget(checkbox)

        if is_header:
            checkbox.toggled.connect(lambda state, c=col-1: handler(c, state))
        else:
            checkbox.toggled.connect(lambda state, r=row: handler(r, state))

        self.table_widget.setCellWidget(row, col, cell_widget)

    def update_column_combo(self):
        self.target_column_combo.blockSignals(True)
        self.target_column_combo.clear()
        self.target_column_combo.addItem("Create New Column")
        self.target_column_combo.addItems(self.logic.get_headers()[1:]) # Exclude uid
        self.target_column_combo.blockSignals(False)

    def connect_signals(self):
        self.apply_button.clicked.connect(self.on_apply)
        self.cancel_button.clicked.connect(self.reject)
        self.rescan_button.clicked.connect(self.on_rescan)
        self.apply_filter_button.clicked.connect(self.on_apply_filter)
        self.target_column_combo.currentTextChanged.connect(self.on_target_column_changed)
        self.table_widget.horizontalHeader().sectionDoubleClicked.connect(self.on_header_double_clicked)

    def on_rescan(self):
        ext_to_exclude = [e.strip() for e in self.excluded_ext_input.text.split(',') if e.strip()]
        self.logic.load_cohort_data(self.logic.data_path, ext_to_exclude)
        self.logic.clear_filters()
        self.update_ui_from_logic()

    def on_apply_filter(self):
        include_list = [s.strip() for s in self.include_input.text.split(',') if s.strip()]
        exclude_list = [s.strip() for s in self.exclude_input.text.split(',') if s.strip()]
        target_col = self.target_column_combo.currentText
        new_col = self.new_column_name_input.text.strip()

        if self.logic.apply_filter(include_list, exclude_list, target_col, new_col):
            self.update_ui_from_logic()
            self.include_input.clear()
            self.exclude_input.clear()
            self.new_column_name_input.clear()
        else:
            qt.QMessageBox.warning(self, "Filter Error", "Could not apply filter. Ensure you provide an 'Include' substring and a unique 'New Column Name' if creating a new column.")

    def on_target_column_changed(self, text):
        is_new_column = (text == "Create New Column")
        self.new_column_name_input.setEnabled(is_new_column)

    def on_header_double_clicked(self, logical_index):
        if logical_index <= 1: return
        old_name = self.logic.get_headers()[logical_index - 1]
        new_name, ok = qt.QInputDialog.getText(self, "Rename Column", f"Enter new name for '{old_name}':", text=old_name)
        if ok and new_name and new_name != old_name:
            if self.logic.rename_column(old_name, new_name):
                self.update_ui_from_logic()
            else:
                qt.QMessageBox.warning(self, "Rename Error", "Column name already exists.")

    def handle_row_toggle(self, row_idx, is_enabled):
        self.logic.toggle_row(row_idx, is_enabled)
        self._update_row_visuals(row_idx, is_enabled)

    def handle_column_toggle(self, col_idx, is_enabled):
        self.logic.toggle_column(col_idx, is_enabled)
        self.update_all_visuals()

    def _update_row_visuals(self, table_row, is_enabled):
        color = self.palette.color(qt.QPalette.Base) if is_enabled else qt.QColor(qt.Qt.lightGray)
        for col in range(self.table_widget.columnCount):
            item = self.table_widget.item(table_row, col)
            if item: item.setBackground(color)

    def update_all_visuals(self):
        for r_idx in range(self.logic.get_case_count()):
             self._update_row_visuals(r_idx, self.logic.is_row_enabled(r_idx))
        for c_idx, header in enumerate(self.logic.get_headers()):
             is_enabled = self.logic.is_column_enabled(c_idx)
             self.table_widget.setColumnHidden(c_idx + 1, not is_enabled)

    def on_apply(self):
        self.logic.apply_changes()
        self.accept()


class CohortGeneratorLogic:
    def __init__(self, data_path):
        self.data_path = Path(data_path)
        self.all_files_by_case = {}
        self.cohort_data = []
        self.headers = ['uid']
        self.disabled_rows = set()
        self.disabled_columns = set()
        self.load_cohort_data(self.data_path, ['.json', '.py'])

    def load_cohort_data(self, data_path, excluded_extensions=None):
        self.all_files_by_case.clear()
        root_path = Path(data_path).resolve()
        if not root_path.is_dir(): return

        excluded_ext = [e.lower().strip() for e in excluded_extensions or []]
        temp_cases = {}

        for file_path in root_path.rglob('*'):
            if file_path.is_file() and file_path.suffix.lower() not in excluded_ext:
                case_dir = file_path.parent
                if case_dir != root_path:
                    case_id = case_dir.relative_to(root_path).as_posix()
                    if case_id not in temp_cases:
                        temp_cases[case_id] = []
                    temp_cases[case_id].append(file_path.relative_to(case_dir).as_posix())

        self.all_files_by_case = {case_id: files for case_id, files in sorted(temp_cases.items())}
        self.clear_filters()

    def clear_filters(self):
        self.headers = ['uid']
        self.cohort_data = [{'uid': case_id} for case_id in self.all_files_by_case.keys()]
        self.disabled_rows.clear()
        self.disabled_columns.clear()

    def get_headers(self):
        return self.headers

    def get_case_count(self):
        return len(self.cohort_data)

    def rename_column(self, old_name, new_name):
        if new_name in self.headers: return False
        try:
            col_idx = self.headers.index(old_name)
            self.headers[col_idx] = new_name
            for row in self.cohort_data:
                if old_name in row:
                    row[new_name] = row.pop(old_name)
            return True
        except ValueError:
            return False

    def toggle_row(self, row_index, is_enabled):
        if is_enabled: self.disabled_rows.discard(row_index)
        else: self.disabled_rows.add(row_index)

    def is_row_enabled(self, row_index):
        return row_index not in self.disabled_rows

    def toggle_column(self, col_index, is_enabled):
        if is_enabled: self.disabled_columns.discard(col_index)
        else: self.disabled_columns.add(col_index)

    def is_column_enabled(self, col_index):
        return col_index not in self.disabled_columns

    def apply_filter(self, include, exclude, target_col, new_col_name):
        if not include: return False
        is_new = (target_col == "Create New Column")
        if is_new:
            if not new_col_name or new_col_name in self.headers: return False
            self.headers.append(new_col_name)
            col_name = new_col_name
        else:
            col_name = target_col

        for i, row in enumerate(self.cohort_data):
            case_id = row['uid']
            found_match = False
            for file_path in self.all_files_by_case.get(case_id, []):
                has_includes = all(inc in file_path for inc in include)
                has_excludes = any(exc in file_path for exc in exclude)
                if has_includes and not has_excludes:
                    self.cohort_data[i][col_name] = file_path
                    found_match = True
                    break
            if not found_match and col_name not in self.cohort_data[i]:
                 self.cohort_data[i][col_name] = ''

        return True

    def apply_changes(self):
        final_data = []
        enabled_headers = [h for i, h in enumerate(self.headers) if self.is_column_enabled(i)]
        final_data.append(enabled_headers)

        for r_idx, row_data in enumerate(self.cohort_data):
            if self.is_row_enabled(r_idx):
                row_to_add = [row_data.get(h, '') for h in enabled_headers]
                final_data.append(row_to_add)

        dir_path = self.data_path / "code"
        dir_path.mkdir(parents=True, exist_ok=True)
        self.cohort_path = dir_path / "cohort.csv"
        with open(self.cohort_path, 'w', newline='') as csvfile:
            csv_writer = csv.writer(csvfile)
            csv_writer.writerows(final_data)