import csv
from datetime import datetime
from pathlib import Path
from typing import Optional

import ctk
import qt
import slicer
from slicer.i18n import tr as _

from CARTLib.core.TaskBaseClass import TaskBaseClass, DataUnitFactory
from .RegistrationReviewDataUnit import RegistrationReviewDataUnit

VERSION = 0.01

# TODO Allow for stop and start of the task. Skip to the next case that is not reviewed.
# First step should be to check the current output CSV file for the current user and the current UID.
# If the current UID is already in the CSV file Add a button to skip the next unreviewed case.
# AND update the current data unit to have knowledge of the previous review status.


class RegistrationReviewGUI:
    def __init__(self, bound_task: "RegistrationReviewTask"):
        self.bound_task = bound_task
        self.data_unit: Optional["RegistrationReviewDataUnit"] = None

        # The currently selected orientation in the GUI
        self.currentOrientation: str = "Axial"

        # CSV log file path
        self.csv_log_path: Optional[Path] = None

    def setup(self) -> qt.QFormLayout:
        """
        Build the GUI's contents, returning the resulting layout for use.
        """
        # Initialize the layout we'll insert everything into
        formLayout = qt.QFormLayout()

        # 1) Orientation buttons
        self._addOrientationButtons(formLayout)

        # 2) CSV output selection
        self._addCsvSelectionButton(formLayout)

        # 3) Save button
        self._addSaveButton(formLayout)

        # Prompt for initial CSV setup
        self.promptSelectCsvOutput()

        return formLayout

    def _addOrientationButtons(self, layout: qt.QFormLayout) -> None:
        """
        Buttons to set Axial/Sagittal/Coronal for all slice views.
        """
        hbox = qt.QHBoxLayout()
        for orientation in ("Axial", "Sagittal", "Coronal"):
            btn = qt.QPushButton(orientation)
            btn.clicked.connect(lambda _, o=orientation: self.onOrientationChanged(o))
            hbox.addWidget(btn)
        layout.addRow(qt.QLabel("View Orientation:"), hbox)

    def _addCsvSelectionButton(self, layout: qt.QFormLayout) -> None:
        """
        Button to change CSV output location.
        """
        btn = qt.QPushButton("Change CSV Output Location")
        btn.clicked.connect(self.promptSelectCsvOutput)
        layout.addRow(btn)

    def _addSaveButton(self, layout: qt.QFormLayout) -> None:
        """
        Save button for recording registration review results.
        """
        btn = qt.QPushButton("Save Registration Review")
        btn.clicked.connect(self._save)
        layout.addRow(btn)
        self.saveButton = btn

    #
    # Handlers
    #

    def onOrientationChanged(self, orientation: str) -> None:
        """Update the orientation for all views."""
        # Update our currently tracked orientation
        self.currentOrientation = orientation

        # If we don't have a data unit at this point, end here
        if not self.data_unit:
            return

        # Update the data unit's orientation if it has a layout handler
        if hasattr(self.data_unit, "set_orientation"):
            self.data_unit.set_orientation(orientation)

        # Apply the layout if data unit has layout handler
        if hasattr(self.data_unit, "layout_handler"):
            self.data_unit.layout_handler.apply_layout()

    ## USER PROMPTS ##
    def promptSelectCsvOutput(self):
        """
        Prompt the user to select CSV output location for registration review logging.
        """
        # Initialize the prompt
        prompt = self._buildCsvOutputPrompt()

        # Show the prompt with "exec", blocking the main window until resolved
        result = prompt.exec()

        # If the user cancelled out of the prompt, notify them
        if result == 0:
            notif = qt.QErrorMessage()
            if self.bound_task.can_save():
                notif.setWindowTitle(_("REVERTING!"))
                notif.showMessage(
                    _("Cancelled out of window; keeping previous CSV output settings.")
                )
                notif.exec()
            else:
                notif.setWindowTitle(_("NO OUTPUT!"))
                notif.showMessage(
                    _(
                        "No CSV output location selected! You will need to "
                        "specify this before registration reviews can be saved."
                    )
                )
                notif.exec()

    def _buildCsvOutputPrompt(self):
        """Build the CSV output selection dialog."""
        prompt = qt.QDialog()
        prompt.setWindowTitle("Select CSV Output Location")

        layout = qt.QVBoxLayout()
        prompt.setLayout(layout)

        # Instruction label
        instructionLabel = qt.QLabel(
            "Select a CSV file location to log registration review results:"
        )
        instructionLabel.setWordWrap(True)
        layout.addWidget(instructionLabel)

        # CSV file path selection
        csvLabel = qt.QLabel("CSV log file:")
        layout.addWidget(csvLabel)

        # Create horizontal layout for CSV path input and buttons
        csvPathLayout = qt.QHBoxLayout()

        self.csvLogEdit = ctk.ctkPathLineEdit()
        self.csvLogEdit.setToolTip(
            _("Specify CSV log file path for registration review results.")
        )
        self.csvLogEdit.filters = ctk.ctkPathLineEdit.Files
        self.csvLogEdit.nameFilters = ["CSV files (*.csv)"]

        # Set current CSV log path if available
        if hasattr(self.bound_task, "csv_log_path") and self.bound_task.csv_log_path:
            self.csvLogEdit.currentPath = str(self.bound_task.csv_log_path)

        # Add browse button for CSV file selection
        csvBrowseButton = qt.QPushButton("Browse...")
        csvBrowseButton.setToolTip("Browse for CSV log file location")
        csvBrowseButton.clicked.connect(self._browseCsvLocation)
        csvBrowseButton.setMaximumWidth(100)

        csvPathLayout.addWidget(self.csvLogEdit)
        csvPathLayout.addWidget(csvBrowseButton)
        layout.addLayout(csvPathLayout)

        # Button box
        buttonBox = qt.QDialogButtonBox()
        buttonBox.addButton(_("Confirm"), qt.QDialogButtonBox.AcceptRole)
        buttonBox.addButton(_("Cancel"), qt.QDialogButtonBox.RejectRole)
        layout.addWidget(buttonBox)

        # Connect acceptance
        buttonBox.accepted.connect(lambda: self._attemptCsvUpdate(prompt))
        buttonBox.rejected.connect(prompt.reject)

        # Resize for better appearance
        prompt.resize(450, prompt.minimumHeight)

        return prompt

    def _browseCsvLocation(self):
        """Open file dialog to browse for CSV log file location."""
        dialog = qt.QFileDialog()
        dialog.setWindowTitle("Select CSV Log File Location")
        dialog.setAcceptMode(qt.QFileDialog.AcceptSave)
        dialog.setFileMode(qt.QFileDialog.AnyFile)
        dialog.setNameFilter("CSV files (*.csv)")
        dialog.setDefaultSuffix("csv")

        # Set default filename if none exists
        if not self.csvLogEdit.currentPath.strip():
            # Generate default filename based on user and current date
            user = getattr(self.bound_task, "user", "user")
            default_name = f"registration_review_log_{user}_{datetime.now().strftime('%Y%m%d')}.csv"
            dialog.selectFile(default_name)
        else:
            # Use existing path as starting point
            existing_path = Path(self.csvLogEdit.currentPath.strip())
            if existing_path.parent.exists():
                dialog.setDirectory(str(existing_path.parent))
            dialog.selectFile(existing_path.name)

        # Show dialog and update path if user selects a file
        if dialog.exec():
            selected_files = dialog.selectedFiles()
            if selected_files:
                selected_path = selected_files[0]
                self.csvLogEdit.currentPath = selected_path

    def _attemptCsvUpdate(self, prompt: qt.QDialog):
        """
        Validates and applies the selected CSV output path.
        """
        csv_path_str = self.csvLogEdit.currentPath.strip()

        if not csv_path_str:
            err_msg = "CSV output path was empty"
            self._showErrorPrompt(err_msg, prompt)
            return

        csv_path = Path(csv_path_str)

        # Validate CSV path parent directory exists
        if not csv_path.parent.exists():
            err_msg = f"CSV output directory does not exist: {csv_path.parent}"
            self._showErrorPrompt(err_msg, prompt)
            return

        # Set the CSV path in the bound task
        err_msg = self.bound_task.set_csv_output(csv_path)

        # Check for errors
        if err_msg:
            self._showErrorPrompt(err_msg, prompt)
            return

        # Success - close the prompt
        prompt.accept()

    def _showErrorPrompt(self, err_msg, prompt):
        """
        Prompt the user with an error message
        """
        failurePrompt = qt.QErrorMessage(prompt)
        failurePrompt.setWindowTitle("ERROR!")
        failurePrompt.showMessage(err_msg)
        failurePrompt.exec()

    def update(self, data_unit: "RegistrationReviewDataUnit") -> None:
        """
        Called whenever a new data-unit is in focus.
        """
        self.data_unit = data_unit

        # Apply the data unit's layout to our viewer if it has one
        if hasattr(self.data_unit, "layout_handler"):
            self.data_unit.layout_handler.apply_layout()

    def _save(self) -> None:
        """Save the current registration review."""
        err = self.bound_task.save()
        self.saveCompletePrompt(err)

    def saveCompletePrompt(self, err_msg: Optional[str]) -> None:
        """Show save completion message."""
        if err_msg is None:
            msg = qt.QMessageBox()
            msg.setWindowTitle("Success!")
            msg.setText(
                f"Registration review for '{self.bound_task.data_unit.uid}' "
                f"was successfully saved to CSV!\n\n"
                f"CSV file: {str(self.bound_task.csv_log_path)}"
            )
            msg.exec()
        else:
            errBox = qt.QErrorMessage()
            errBox.setWindowTitle("ERROR!")
            errBox.showMessage(err_msg)
            errBox.exec()

    ## GUI SYNCHRONIZATION ##
    def enter(self) -> None:
        """Called when entering the task."""
        pass

    def exit(self) -> None:
        """Called when exiting the task."""
        pass


class RegistrationReviewTask(TaskBaseClass[RegistrationReviewDataUnit]):
    """
    Task for reviewing registration results.
    Saves review data to a CSV log file.
    """

    def __init__(self, user: str):
        super().__init__(user)

        # Variable for tracking the active GUI instance
        self.gui: Optional["RegistrationReviewGUI"] = None

        # CSV log file path
        self.csv_log_path: Optional[Path] = None

        # Current data unit
        self.data_unit: Optional[RegistrationReviewDataUnit] = None

    def setup(self, container: qt.QWidget):
        """Set up the GUI for this task."""
        print(f"Running {self.__class__.__name__} setup!")

        # Initialize the GUI instance for this task
        self.gui = RegistrationReviewGUI(self)

        # Build its GUI and install it into the container widget
        gui_layout = self.gui.setup()
        container.setLayout(gui_layout)

        # Update this new GUI with our current data unit
        if self.data_unit:
            self.gui.update(self.data_unit)

        # "Enter" the gui to ensure it is loaded correctly
        self.gui.enter()

    def receive(self, data_unit: RegistrationReviewDataUnit):
        """Receive a new data unit for review."""
        # Track the data unit for later
        self.data_unit = data_unit

    def cleanup(self):
        """Clean up resources when task is destroyed."""
        # Break the cyclical link with our GUI so garbage collection can run
        if self.gui:
            self.gui.exit()
            self.gui = None

    def save(self) -> Optional[str]:
        """Save the current registration review to CSV."""
        if not self.can_save():
            return "Cannot save: No CSV output location specified"

        if not self.data_unit:
            return "Cannot save: No data unit available"

        try:
            # Prepare the data to save
            review_data = {
                "uid": self.data_unit.uid,
                "user": self.user,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "review_status": "reviewed",  # Could be extended with more statuses
                # TODO Add in the registration classification:
                # "No_Registration_Required", "Deformable_Registration_Required", "Rigid_Registration_Required"
                # Add any additional review data here
            }

            # Check if CSV file exists
            csv_exists = self.csv_log_path.exists()

            # Read existing data if file exists
            existing_data = []
            if csv_exists:
                with open(self.csv_log_path, newline="") as csvfile:
                    reader = csv.DictReader(csvfile)
                    existing_data = list(reader)

            # Check if this UID already has an entry and update it
            entry_found = False
            for entry in existing_data:
                if (
                    entry.get("uid") == self.data_unit.uid
                    and entry.get("user") == self.user
                ):
                    # Update existing entry
                    entry.update(review_data)
                    entry_found = True
                    break

            # If no existing entry, add new one
            if not entry_found:
                existing_data.append(review_data)

            # Define field names (CSV headers)
            fieldnames = ["uid", "user", "timestamp", "review_status"]

            # Write the updated data back to CSV
            with open(self.csv_log_path, "w", newline="") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(existing_data)

            print(f"Registration review saved for UID: {self.data_unit.uid}")
            return None  # Success

        except Exception as e:
            error_msg = f"Error saving registration review: {str(e)}"
            print(error_msg)
            return error_msg

    def can_save(self) -> bool:
        """Check if we can save the current registration review."""
        return self.csv_log_path is not None and self.data_unit is not None

    def set_csv_output(self, csv_path: Path) -> Optional[str]:
        """Set the CSV output path and validate it."""
        try:
            # Ensure parent directory exists
            csv_path.parent.mkdir(parents=True, exist_ok=True)

            # Store the path
            self.csv_log_path = csv_path

            # Initialize CSV file with headers if it doesn't exist
            if not csv_path.exists():
                fieldnames = ["uid", "user", "timestamp", "review_status"]
                with open(csv_path, "w", newline="") as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()

            return None  # Success

        except Exception as e:
            error_msg = f"Error setting CSV output path: {str(e)}"
            print(error_msg)
            return error_msg

    def enter(self):
        """Called when the task is entered/focused."""
        if self.gui:
            self.gui.enter()

    def exit(self):
        """Called when the task is exited/unfocused."""
        if self.gui:
            self.gui.exit()

    @classmethod
    def getDataUnitFactories(cls) -> dict[str, DataUnitFactory]:
        """Return the data unit factories for this task."""
        return {"Default": RegistrationReviewDataUnit}
