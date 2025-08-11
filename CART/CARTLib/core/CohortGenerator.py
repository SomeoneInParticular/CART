import qt
import csv
from pathlib import Path

from CARTLib.utils.config import config
from CARTLib.utils.data_checker import fetch_resources

class CohortGeneratorWindow(qt.QDialog):
    """
    GUI to display and configure a cohort from a data directory.
    """

    ### UI ###
    def __init__(self, data_path, cohort_data=None, cohort_path=None, current_data_convention=None, parent=None):
        super().__init__(parent)
        self.logic = CohortGeneratorLogic(data_path=data_path, cohort_data=cohort_data, cohort_path=cohort_path, current_data_convention=current_data_convention)
        self.setWindowFlags(self.windowFlags() | qt.Qt.WindowMaximizeButtonHint | qt.Qt.WindowMinimizeButtonHint | qt.Qt.Window)

        # Make dialog/window non-modal, to allow interaction with main window
        self.setModal(False)

        # Build the UI
        self.build_ui()

        # Connect all buttons to callback functions
        self.connect_signals()

        # Initial table population
        self.update_ui_from_logic()

    def build_ui(self):
        """
        UI to display tentative cohort table, apply and close buttons
        """
        self.setWindowTitle("Cohort Generator and Editor")
        self.setMinimumSize(900, 700)
        layout = qt.QVBoxLayout(self)

        # Tentative cohort table UI
        self.table_widget = qt.QTableWidget()
        layout.addWidget(self.table_widget)

        # Filtering UI
        controls_layout = qt.QHBoxLayout()
        controls_layout.addWidget(self.build_load_options_groupbox())
        controls_layout.addWidget(self.build_filtering_groupbox(), 1)
        layout.addLayout(controls_layout)

        button_layout = qt.QHBoxLayout()

        # If a preious cohort file was generated, give the option to override
        self.override_selected_cohort_file_toggle_button = qt.QCheckBox("Override selected Cohort File ?")
        self.override_selected_cohort_file_toggle_button.setEnabled(self.logic.selected_cohort_path is not None)

        # Utility buttons
        self.apply_button = qt.QPushButton("Save and Apply")
        self.cancel_button = qt.QPushButton("Cancel")

        # Tooltips
        self.override_selected_cohort_file_toggle_button.setToolTip("Saves your changes into the file located at " + str(self.logic.selected_cohort_path))
        self.apply_button.setToolTip("Overrides or creates new cohort file under " + str(self.logic.data_path / "cohort files"))

        button_layout.addStretch()

        button_layout.addWidget(self.override_selected_cohort_file_toggle_button)
        button_layout.addWidget(self.apply_button)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)

    def build_load_options_groupbox(self):
        """
        UI to display file extensions to exclude from cell
        """
        groupbox = qt.QGroupBox("Load Options")
        layout = qt.QFormLayout(groupbox)

        # By default, exclude these files, as they are common
        self.excluded_ext_input = qt.QLineEdit(".json, .py, .ssh, .csv")
        self.excluded_ext_input.toolTip = "Comma-separated list of file extensions to ignore."
        self.rescan_button = qt.QPushButton("Rescan Data Path")

        layout.addRow("Exclude Extensions:", self.excluded_ext_input)
        layout.addRow(self.rescan_button)

        # Temporarily disable
        groupbox.setEnabled(False)

        return groupbox

    def build_filtering_groupbox(self):
        """
        UI to display column creation and filtering options
        """
        groupbox = qt.QGroupBox("Column Creating, Filtering and Editing")
        layout = qt.QFormLayout(groupbox)

        # Any substring that must exist within all files loaded in a certain resource column
        self.include_input = qt.QLineEdit()
        self.include_input.setPlaceholderText("e.g., T1w, nii, lesion_seg")

        # Any substring that must not exist within all files loaded in a certain resource column
        self.exclude_input = qt.QLineEdit()
        self.exclude_input.setPlaceholderText("e.g., masked, brain")

        self.target_column_combo = qt.QComboBox()
        self.new_column_name_input = qt.QLineEdit()

        column_control_hbox = qt.QHBoxLayout()

        self.apply_filter_button = qt.QPushButton("Create New Column from Filters")
        self.delete_col_button = qt.QPushButton("Delete Column")
        self.delete_col_button.setStyleSheet("background-color: red; color: white;")

        column_control_hbox.addWidget(self.apply_filter_button)
        column_control_hbox.addWidget(self.delete_col_button)

        layout.addRow("Target Column:", self.target_column_combo)
        layout.addRow("New Column Name:", self.new_column_name_input)
        layout.addRow("Filenames MUST Contain:", self.include_input)
        layout.addRow("Filenames MUST NOT Contain:", self.exclude_input)

        # Tooltips
        self.new_column_name_input.setToolTip("Assigns name to the new resource column if creating")
        self.include_input.setToolTip("All files inserted into the target column must ALL include filters typed here. If left blank, selects all matches.")
        self.exclude_input.setToolTip("All files inserted into the target column must NOT include filters typed here. If left blank, ignored.")

        layout.addRow(column_control_hbox)

        return groupbox

    def update_ui_from_logic(self):
        self.populate_table()
        self.update_column_combo()

    def populate_table(self):
        self.table_widget.blockSignals(True)
        self.table_widget.clear()
        data = self.logic.cohort_data

        # If no cohort has selectedly been created, load empty
        if not data:
            self.table_widget.setRowCount(0)
            self.table_widget.setColumnCount(0)
            self.table_widget.blockSignals(False)
            return

        headers = self.logic.get_headers()
        num_rows = len(data)
        num_cols = len(headers)

        # Need extra row for header checkboxes
        self.table_widget.setRowCount(num_rows + 1)
        self.table_widget.setColumnCount(num_cols + 1)
        self.table_widget.setHorizontalHeaderLabels([""] + headers)

        # Create column checkboxes in header row (row 0)
        for c_idx in range(1, num_cols):
            self._create_checkbox(0, c_idx + 1, self.handle_column_toggle,
                                self.logic.is_column_enabled(c_idx), is_header=True)

        # Create row checkboxes and populate data
        for r_idx in range(num_rows):
            table_row = r_idx + 1  # Data starts at row 1 (row 0 is for column checkboxes)

            # Create row checkbox
            self._create_checkbox(table_row, 0, self.handle_row_toggle,
                                self.logic.is_row_enabled(r_idx))

            # Populate data cells
            for c_idx, header in enumerate(headers):
                item = qt.QTableWidgetItem(str(data[r_idx].get(header, '')))
                item.setFlags(qt.Qt.ItemIsEnabled | qt.Qt.ItemIsSelectable)
                self.table_widget.setItem(table_row, c_idx + 1, item)

        self.table_widget.resizeColumnsToContents()
        self.table_widget.verticalHeader().setVisible(False)
        self.table_widget.horizontalHeader().setSectionResizeMode(qt.QHeaderView.Interactive)
        self.update_all_visuals()
        self.table_widget.blockSignals(False)

    def _create_checkbox(self, row, col, handler, is_checked, is_header=False):
        """
        Create checkboxes to remove column or row from cohort and UI
        """
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
        """
        Update resource names from the headers of the currently displayed tentative cohort table
        """
        self.target_column_combo.blockSignals(True)
        self.target_column_combo.clear()
        self.target_column_combo.addItem("Create New Column")

        # Exclude uid
        self.target_column_combo.addItems(self.logic.get_headers()[1:])
        self.target_column_combo.blockSignals(False)

    # UI enhancement
    def highlight_uid_col(self):
        """
        Highlight the uid column in purple for visibility
        """
        for row in range(self.logic.get_case_count()):
            item = self.table_widget.item(row + 1, 1)
            if item and self.logic.is_row_enabled(row):
                item.setBackground(qt.QColor("#8f6ae7"))

    ### Connection signals ###
    def connect_signals(self):
        self.override_selected_cohort_file_toggle_button.stateChanged.connect(self.on_toggle_override_selected_cohort_file)
        self.apply_button.clicked.connect(self.on_apply)
        self.cancel_button.clicked.connect(self.on_cancel)
        self.rescan_button.clicked.connect(self.on_rescan)
        self.apply_filter_button.clicked.connect(self.on_apply_filter)
        self.delete_col_button.clicked.connect(self.on_delete_column)

        self.target_column_combo.currentTextChanged.connect(self.on_target_column_changed)

        self.table_widget.horizontalHeader().sectionDoubleClicked.connect(self.on_header_double_clicked)
        self.table_widget.horizontalHeader().sectionClicked.connect(self.on_header_single_clicked)


    ### Callback functions ###
    def on_rescan(self):
        """
        Rebuild entire tentative cohort table while excluding paths with forbidden filetypes
        """
        ext_to_exclude = [e.strip() for e in self.excluded_ext_input.text.split(',') if e.strip()]
        self.logic.load_cohort_data(self.logic.data_path, ext_to_exclude)
        self.logic.clear_filters()
        self.update_ui_from_logic()

    def on_toggle_override_selected_cohort_file(self):
        is_checked = self.override_selected_cohort_file_toggle_button.isChecked()
        self.logic.override_selected_cohort_file = is_checked

    def on_apply_filter(self):
        """
        Update or create new column based on filter requests
        """
        include_list = [s.strip() for s in self.include_input.text.split(',') if s.strip()]
        exclude_list = [s.strip() for s in self.exclude_input.text.split(',') if s.strip()]
        target_col = self.target_column_combo.currentText
        new_col = self.new_column_name_input.text.strip()

        # Rebuild entire tentative cohort table with new/updated column
        if self.logic.apply_filter(include_list, exclude_list, target_col, new_col):
            self.update_ui_from_logic()
            self.include_input.clear()
            self.exclude_input.clear()
            self.new_column_name_input.clear()
        else:
            qt.QMessageBox.warning(self, "Filter Error", "Could not apply filters. Your filters either contradict or no results yielded from your filters. Provide a unique 'New Column Name' if creating a new column.")

    def on_delete_column(self):
        """
        Delete the selected column from target_column_combo
        """
        target_col = self.target_column_combo.currentText

        # Don't allow deletion of "Create New Column" option or uid column
        if target_col == "Create New Column" or target_col == "uid":
            qt.QMessageBox.warning(self, "Delete Error", "Cannot delete this column.")
            return

        # Confirm deletion
        reply = qt.QMessageBox.question(
            self, "Delete Column",
            f"Are you sure you want to delete column '{target_col}'?",
            qt.QMessageBox.Yes | qt.QMessageBox.No,
            qt.QMessageBox.No
        )

        if reply == qt.QMessageBox.Yes:
            if self.logic.delete_column(target_col):
                # Reset to "Create New Column"
                self.on_target_column_changed("Create New Column")
                self.update_ui_from_logic()
            else:
                qt.QMessageBox.warning(self, "Delete Error", "Could not delete column.")

    def on_target_column_changed(self, text):
        """
        Enable creation of new column
        """
        is_new_column = (text == "Create New Column")
        self.new_column_name_input.setEnabled(is_new_column)

        if is_new_column:
            self.apply_filter_button.setText("Create New Column from Filters")
        else:
            # Populate include/exclude inputs from config if available
            selected_column_filters = config.get_filter(text)
            if selected_column_filters:
                include_input  = selected_column_filters["inclusion_input"]
                exclude_input  = selected_column_filters["exclusion_input"]

                self.include_input.setText(include_input)
                self.exclude_input.setText(exclude_input)

            self.apply_filter_button.setText(f"Apply Filters on `{text}`")

    def on_header_double_clicked(self, logical_index):
        """
        Change the name of the selected column
        """
        if logical_index <= 1:
            return

        old_name = self.logic.get_headers()[logical_index - 1]

        new_name = qt.QInputDialog.getText(
            self,
            "Rename Column",
            f"Enter new name for '{old_name}':",
            qt.QLineEdit.Normal,
            old_name
        )

        # If user cancels, getText returns empty string or None
        if new_name and new_name != old_name:
            if self.logic.rename_column(old_name, new_name):
                self.update_ui_from_logic()
            else:
                qt.QMessageBox.warning(self, "Rename Error", "Column name already exists.")

    def on_header_single_clicked(self, logical_index):
        """
        Populate the creating, filtering and editing UI with selected column metadata
        """
        if logical_index <= 1:
            return

        column_name = self.logic.get_headers()[logical_index - 1]

        # Automatically triggers `self.on_target_column_changed`
        self.target_column_combo.setCurrentText(column_name)
        self.new_column_name_input.setEnabled(False)

    def handle_row_toggle(self, table_row_idx, is_enabled):
        logical_row_idx = table_row_idx - 1
        self.logic.toggle_row(logical_row_idx, is_enabled)
        self._update_row_visuals(table_row_idx, is_enabled)

        # Make sure the coloring comes back for the uid column
        self.highlight_uid_col()

    def handle_column_toggle(self, col_idx, is_enabled):
        self.logic.toggle_column(col_idx, is_enabled)
        self.update_all_visuals()

    def _update_row_visuals(self, table_row, is_enabled):
        color = self.palette.color(qt.QPalette.Base) if is_enabled else qt.QColor(qt.Qt.lightGray)
        for col in range(self.table_widget.columnCount):
            item = self.table_widget.item(table_row, col)
            if item:
                item.setBackground(color)

    def _update_col_visuals(self, table_col, is_enabled):
        color = self.palette.color(qt.QPalette.Base) if is_enabled else qt.QColor(qt.Qt.lightGray)
        for row in range(self.logic.get_case_count()):
            item = self.table_widget.item(row + 1, table_col)

            # Activating a column cannot activate rows that are already turned off
            if item and row not in self.logic.disabled_rows:
                item.setBackground(color)

    def update_all_visuals(self):
        # Update row visuals (table rows start at index 1)
        for r_idx in range(self.logic.get_case_count()):
            table_row = r_idx + 1
            self._update_row_visuals(table_row, self.logic.is_row_enabled(r_idx))

        # Update column visibility
        for c_idx, header in enumerate(self.logic.get_headers()):
            table_col = c_idx + 1
            self._update_col_visuals(table_col, self.logic.is_column_enabled(c_idx))

        # Highlight uid column
        self.highlight_uid_col()

    def on_apply(self):
        self.logic.apply_changes()
        self.accept()

    def on_cancel(self):
        self.close()


class CohortGeneratorLogic:
    def __init__(self, data_path, cohort_data=None, cohort_path=None, current_data_convention=None):
        self.data_path = Path(data_path)
        self.all_files_by_case: dict[str, list[str]] = {}
        self.cohort_data = cohort_data if cohort_data is not None else []
        self.current_data_convention = current_data_convention

        self.headers = []

        self.disabled_rows = set()
        self.disabled_columns = set()

        # Exclude common files found in imagine datasetss
        self._scan_filesystem(['.json', '.py', '.ssh', '.csv'])

        if not self.cohort_data:
            # Initiliaze the uid column and populate case identifiers
            self.clear_filters()
        else:
            if self.cohort_data:
                self.headers = list(self.cohort_data[0].keys())

        # Location of the saved auto-generated cohort CSV file - also the path returned to the main widget
        self.selected_cohort_path = cohort_path
        self.override_selected_cohort_file: bool = False

    def _scan_filesystem(self, excluded_extensions=None):
        """
        Scan BIDS-formatted dataset: only consider subject folders (sub-*) in root and derivatives.
        Group derivatives with their corresponding raw subject, so each case (subject) includes both raw and derivatives files.
        """
        self.all_files_by_case.clear()
        root_path = Path(self.data_path).resolve()
        if not root_path.is_dir():
            return

        self.all_files_by_case = fetch_resources(
        self.current_data_convention,
        root_path,
        excluded_extensions=excluded_extensions
        )

    def load_cohort_data(self, data_path, excluded_extensions=None):
        self._scan_filesystem(excluded_extensions)
        self.clear_filters()

    def clear_filters(self):
        """
        Clear all filters and load uids into cohort data
        """
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

        print("DISABLED COLUMNS")
        print(self.disabled_columns)

    def is_column_enabled(self, col_index):
        return col_index not in self.disabled_columns

    def apply_filter(self, include, exclude, target_col, new_col_name):
        is_new = (target_col == "Create New Column")
        if is_new:
            if not new_col_name or new_col_name in self.headers: return False
            col_name = new_col_name
        else:
            col_name = target_col

        # One of the flags to test the filters
        found_match_in_root = False

        for i, row in enumerate(self.cohort_data):
            case_id = row['uid']
            found_match = False
            for file_path in self.all_files_by_case.get(case_id, []):
                has_includes = all(inc in file_path for inc in include)
                has_excludes = any(exc in file_path for exc in exclude)

                # This would load the first encountered resource within a case folder
                if has_includes and not has_excludes:
                    self.cohort_data[i][col_name] = file_path
                    found_match = True

                    # If a single match throughout the entire dataset is found, no error should be raised
                    found_match_in_root = True
                    break

            if not found_match and col_name not in self.cohort_data[i]:
                 self.cohort_data[i][col_name] = ''

        # This means that the set filters are either contradicting or yield nothing
        if not found_match_in_root:
            return False

        self.headers.append(new_col_name)

        # Save used filters to config for population later
        config.set_filter(
            column_name=col_name,
            inclusion_input=','.join(include),
            exclusion_input=','.join(exclude)
        )

        config.save()

        return True

    def delete_column(self, column_name):
        """
        Delete a column from headers and cohort data
        """
        if column_name not in self.headers or column_name == "uid":
            return False

        try:
            col_idx = self.headers.index(column_name)
            self.headers.remove(column_name)

            # Remove column from disabled columns set if it was disabled
            self.disabled_columns.discard(col_idx)

            # Adjust disabled column indices after deletion
            self.disabled_columns = {
                idx - 1 if idx > col_idx else idx
                for idx in self.disabled_columns
                if idx != col_idx
            }

            # Remove column data from all rows
            for row in self.cohort_data:
                row.pop(column_name, None)

            # Remove the filter from config
            config.remove_filter(column_name)
            config.save()

            return True
        except ValueError:
            return False

    def apply_changes(self):
        """
        Close the popup window and save the generated cohort file
        """
        final_data = []
        enabled_headers = [h for i, h in enumerate(self.headers) if self.is_column_enabled(i)]
        final_data.append(enabled_headers)

        # Build the filtered data
        filtered_cohort_data = []
        for r_idx, row_data in enumerate(self.cohort_data):
            if self.is_row_enabled(r_idx):
                # Filter to only enabled columns
                filtered_row = {h: row_data.get(h, '') for h in enabled_headers}
                filtered_cohort_data.append(filtered_row)

                # Add to CSV data
                row_to_add = [row_data.get(h, '') for h in enabled_headers]
                final_data.append(row_to_add)

        # Update the internal data to reflect the changes
        self.cohort_data = filtered_cohort_data
        self.headers = enabled_headers

        # Clear disabled states since we've applied them permanently
        self.disabled_rows.clear()
        self.disabled_columns.clear()

        # Save to CSV
        dir_path = Path(self.data_path / "cohort files")
        dir_path.mkdir(parents=True, exist_ok=True)
        #cohort_path = Path(dir_path / "cohort.csv")

        self._write_to_csv(dir_path, final_data)

    ###  CSV cohort file generation ###
    def _write_to_csv(self, dir_path, csv_data) -> None:
        """
        Write to CSV file
        """
        override: bool = self.override_selected_cohort_file

        cohort_path = self.selected_cohort_path

        if not override:
            index = self._determine_next_cohort_filename(dir_path)
            cohort_name = "cohort" + str(index) + ".csv"
            cohort_path = Path(dir_path / cohort_name)

        # Update the selected cohort path
        self.selected_cohort_path = cohort_path

        with open(cohort_path, 'w', newline='') as csvfile:
            csv_writer = csv.writer(csvfile)
            csv_writer.writerows(csv_data)


    def _determine_next_cohort_filename(self, dir_path) -> int:
        return sum(
            1 for file in dir_path.iterdir()
            if file.is_file() and file.name.lower().startswith("cohort") and file.suffix.lower() == ".csv"
        )