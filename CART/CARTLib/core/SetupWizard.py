from pathlib import Path
from typing import TYPE_CHECKING, Optional

import ctk
import qt
from slicer.i18n import tr as _

from CARTLib.utils import CART_PATH
from CARTLib.utils.config import JobProfileConfig
from CARTLib.utils.task import CART_TASK_REGISTRY


if TYPE_CHECKING:
    # Avoid a cyclical import
    from CART import CARTLogic
    # NOTE: this isn't perfect (this only exposes Widgets, and Slicer's QT impl
    # isn't the same as PyQT5 itself), but it's a LOT better than constant
    # cross-referencing
    import PyQt5.Qt as qt


## Setup ##
CART_LOGO_PIXMAP = qt.QPixmap(CART_PATH / "Resources/Icons/CART.png")

JOB_NAME_FIELD = "job_name"
SELECTED_TASK_FIELD = "selected_task"


## Wizards ##
class CARTSetupWizard(qt.QWizard):
    """
    Linear setup wizard for CART; walks the user through
    setting up their master profile, creating the initial
    configuration file once completed.
    """

    AUTHOR_KEY = "author"
    POSITION_KEY = "position"

    def __init__(self, parent):
        super().__init__(parent)

        # Standard elements
        self.setWindowTitle("CART " + _("Setup"))
        self.setPixmap(
            qt.QWizard.LogoPixmap,
            CART_LOGO_PIXMAP
        )

        # Add pages
        self.addPage(self.createIntroPage())
        self.addPage(self.createProfileCreationPage())
        self.addPage(self.createConclusionPage())

    ## Pages ##
    @staticmethod
    def createIntroPage():
        # Basic Attributes
        page = qt.QWizardPage()
        page.setTitle(_("Introduction"))
        layout = qt.QVBoxLayout()
        page.setLayout(layout)

        # Introduction text
        label = qt.QLabel(_(
            "Welcome to CART! This wizard will help you get started with your first job."
        ))
        label.setWordWrap(True)
        layout.addWidget(label)

        return page

    def createProfileCreationPage(self):
        # Basic Attributes
        page = qt.QWizardPage()
        page.setTitle(_("Profile Creation"))
        layout = qt.QFormLayout()
        page.setLayout(layout)

        # Instruction text
        instructionLabel = qt.QLabel(_(
            "Please fill out the following fields:"
        ))
        instructionLabel.setWordWrap(True)
        layout.addRow(instructionLabel)

        # Author name
        authorLabel = qt.QLabel(_("Author:"))
        authorLineEdit = qt.QLineEdit()
        authorLineEdit.setPlaceholderText(_("How you want to be identified."))
        authorLabel.setBuddy(authorLineEdit)
        layout.addRow(authorLabel, authorLineEdit)
        # The asterisk marks this field as "mandatory"
        page.registerField(self.AUTHOR_KEY + "*", authorLineEdit)

        # Position
        positionLabel = qt.QLabel(_("Position"))
        positionLineEdit = qt.QLineEdit()
        positionLineEdit.setPlaceholderText(_(
            "Clinician, Research Associate, Student etc."
        ))
        positionLabel.setBuddy(positionLineEdit)
        layout.addRow(positionLabel, positionLineEdit)
        page.registerField(self.POSITION_KEY, positionLineEdit)

        return page

    @staticmethod
    def createConclusionPage():
        # Basic Attributes
        page = qt.QWizardPage()
        page.setTitle(_("Next Steps"))
        layout = qt.QVBoxLayout()
        page.setLayout(layout)

        # Introduction text
        label = qt.QLabel(_(
            "You have finished initial setup; you will now be prompted to set up your first CART Job."
        ))
        label.setWordWrap(True)
        layout.addWidget(label)

        return page

    ## Fields/Properties ##
    @property
    def author(self) -> str:
        return self.field(self.AUTHOR_KEY)

    @property
    def position(self) -> str:
        return self.field(self.POSITION_KEY)

    ## Utils ##
    def update_logic(self, logic: "CARTLogic"):
        # Update the logic's attributes
        logic.author = self.author
        logic.position = self.position

        # Have the logic save its config immediately
        logic.save_master_config()


class JobSetupWizard(qt.QWizard):
    def __init__(self, parent):
        super().__init__(parent)

        # Standard elements
        self.setWindowTitle(_("Job Setup"))
        self.setPixmap(
            qt.QWizard.LogoPixmap,
            CART_LOGO_PIXMAP
        )

        # Workarounds for fields not playing nicely w/ CTK widgets
        self._dataPage = _DataWizardPage()
        self._cohortPage = _CohortWizardPage()

        # Add initial pages
        self.addPage(self.introPage())
        self.addPage(self._dataPage)
        self.addPage(self.selectTaskPage())
        self.addPage(self._cohortPage)
        self.addPage(self.conclusionPage())

    ## Page Management ##
    @staticmethod
    def introPage():
        # Basic Attributes
        page = qt.QWizardPage()
        page.setTitle(_("Introduction"))
        layout = qt.QVBoxLayout()
        page.setLayout(layout)

        # Introduction text
        label = qt.QLabel(_(
            "This wizard will walk you through job creation, including data selection and task setup."
        ))
        label.setWordWrap(True)
        layout.addWidget(label)

        return page

    def selectTaskPage(self):
        # Basic Attributes
        page = qt.QWizardPage()
        page.setTitle(_("Task Selection"))
        layout = qt.QVBoxLayout()
        page.setLayout(layout)

        # Task selection
        taskSelectionLabel = qt.QLabel(_("Please select a task for this job:"))
        taskSelectionWidget = qt.QComboBox()
        taskSelectionWidget.addItems(list(
            CART_TASK_REGISTRY.keys()
        ))
        # This doesn't work; keeping it here in case Slicer ever fixes this bug
        taskSelectionWidget.placeholderText = _("[None Selected]")
        taskSelectionWidget.setCurrentIndex(-1)
        taskSelectionLabel.setBuddy(taskSelectionWidget)
        page.registerField(SELECTED_TASK_FIELD + "*", taskSelectionWidget)
        layout.addWidget(taskSelectionLabel)
        layout.addWidget(taskSelectionWidget)

        # Task description
        default_text = _(
            "Details about the selected task will appear here."
        )
        taskDescriptionWidget = qt.QTextEdit(default_text)
        # Make it fill out all available space
        taskDescriptionWidget.setSizePolicy(
            qt.QSizePolicy.Expanding, qt.QSizePolicy.Expanding
        )
        # Add a border around it to visually distinguish it
        taskDescriptionWidget.setFrameShape(qt.QFrame.Panel)
        taskDescriptionWidget.setFrameShadow(qt.QFrame.Sunken)
        taskDescriptionWidget.setLineWidth(3)
        # Align text to the upper-left
        taskDescriptionWidget.setAlignment(qt.Qt.AlignLeft | qt.Qt.AlignTop)
        # Make it read-only
        taskDescriptionWidget.setReadOnly(True)
        # When the selected task changes, update the description text to match
        def onSelectedTaskChanged(new_task: str):
            task = CART_TASK_REGISTRY.get(new_task)
            if task is None:
                taskDescriptionWidget.setMarkdown(default_text)
            else:
                taskDescriptionWidget.setMarkdown(task.description())
        taskSelectionWidget.currentTextChanged.connect(onSelectedTaskChanged)
        # Add it to the layout
        layout.addWidget(taskDescriptionWidget)

        return page

    @staticmethod
    def conclusionPage():
        # TODO: Replace this with seamless task carry-over
        # Basic Attributes
        page = qt.QWizardPage()
        page.setTitle(_("Almost There!"))
        layout = qt.QVBoxLayout()
        page.setLayout(layout)

        # Introduction text
        label = qt.QLabel(_(
            "Job specification is nearly complete; "
            "fill out the task-specific setup, and you're done!"
        ))
        label.setWordWrap(True)
        layout.addWidget(label)

        return page

    ## Attributes ##
    @property
    def job_name(self) -> str:
        return self.field(JOB_NAME_FIELD)

    @property
    def data_path(self) -> Optional[Path]:
        return self._dataPage.data_path

    @property
    def output_path(self):
        return self._dataPage.output_path

    @property
    def cohort_path(self) -> Optional[Path]:
        # Delegate property, due to the unique checks required for the cohort path
        return self._cohortPage.cohort_path

    def generate_new_config(self, logic: "CARTLogic") -> JobProfileConfig:
        # Generate the new config and immediately save it
        new_config = JobProfileConfig()
        new_config.name = self.job_name
        new_config.data_path = self.data_path
        new_config.output_path = self.output_path
        new_config.cohort_path = self.cohort_path
        new_config.save()

        # Register the new job
        logic.register_job_config(new_config)

        return new_config

## Wizard Pages ##
class _DataWizardPage(qt.QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Basic Attributes
        self.setTitle(_("Data Specification"))
        layout = qt.QFormLayout()
        self.setLayout(layout)

        # Instruction text
        instructionLabel = qt.QLabel(_(
            "Please fill out the following fields:"
        ))
        instructionLabel.setWordWrap(True)
        layout.addRow(instructionLabel)

        # Job name
        jobNameLabel = qt.QLabel(_("Job Name:"))
        jobNameEntry = qt.QLineEdit()
        jobNameEntry.setPlaceholderText(_(
            "Should not match a previous job's name."
        ))
        jobNameLabel.setBuddy(jobNameEntry)
        self.registerField(JOB_NAME_FIELD, jobNameEntry)
        layout.addRow(jobNameLabel, jobNameEntry)

        # Data path
        dataPathLabel = qt.QLabel(_("Data Source:"))
        dataPathEntry: qt.QWidget = ctk.ctkPathLineEdit()
        dataPathEntry.filters = ctk.ctkPathLineEdit.Dirs
        dataPathEntry.setToolTip(_(
            "This should be a directory containing the data files you wish to use. If left blank, "
            "all files within the cohort will be treated as absolute paths"
        ))
        dataPathLabel.setBuddy(dataPathEntry)
        # Workaround to CTK not playing nicely w/ "registerField"
        self._dataPathEntry = dataPathEntry
        layout.addRow(dataPathLabel, dataPathEntry)

        # Output path
        outputPathLabel = qt.QLabel(_("Output Path:"))
        outputPathEntry: qt.QWidget = ctk.ctkPathLineEdit()
        outputPathEntry.filters = ctk.ctkPathLineEdit.Dirs
        outputPathEntry.setToolTip(_(
            "The directory the results/output of the job should be placed in. "
            "What is saved, and in what structure, depends on the task (selected later)"
        ))
        outputPathLabel.setBuddy(outputPathEntry)
        # Workaround to CTK not playing nicely w/ "registerField"
        self._outputPathEntry = outputPathEntry
        layout.addRow(outputPathLabel, outputPathEntry)

        # Connections which mark that the page's status may have changed
        dummy_func = lambda __: self.completeChanged()
        jobNameEntry.textChanged.connect(dummy_func)
        dataPathEntry.comboBox().currentTextChanged.connect(dummy_func)
        outputPathEntry.comboBox().currentTextChanged.connect(dummy_func)

    @property
    def job_name(self) -> str:
        return self.field(JOB_NAME_FIELD)

    @property
    def data_path(self) -> Optional[Path]:
        # Workaround to CTK not playing nicely w/ "registerField"
        path = self._dataPathEntry.currentPath
        if not path:
            return None
        return Path(path)

    @property
    def output_path(self) -> Optional[Path]:
        # Workaround to CTK not playing nicely w/ "registerField"
        path = self._outputPathEntry.currentPath
        if not path:
            return None
        return Path(path)

    def isComplete(self):
        # If we don't have a job name yet, return false immediately
        if self.job_name == "":
            return False
        # TODO: Check if the job name is already taken
        # Confirm a data path has been specified, and is a directory
        if not self.data_path or not self.data_path.is_dir():
            return False
        # Confirm an output path has been specified and is not a file
        if not self.output_path or self.output_path.is_file():
            return False
        # Otherwise we're done!
        return True


class _CohortWizardPage(qt.QWizardPage):
    """
    A wizard page that allows for selecting, creating, editing, and previewing cohort files.

    Has enough unique functionality (including a Qt override) to form its own class;
    """
    def __init__(self, parent=None):
        super().__init__(parent)

        # Basic Attributes
        self.setTitle(_("Define Cohort"))
        layout = qt.QFormLayout()
        self.setLayout(layout)

        # Directory selection button
        cohortFileLabel = qt.QLabel(_("Cohort File"))
        cohortFileSelector: qt.QWidget = ctk.ctkPathLineEdit()
        cohortFileSelector.filters = ctk.ctkPathLineEdit.Files
        cohortFileSelector.nameFilters = [
            "CSV files (*.csv)",
        ]
        # Workaround to CTK not playing nicely w/ "registerField"
        self._cohortFileSelector = cohortFileSelector
        layout.addRow(cohortFileLabel, cohortFileSelector)

        # Button panel for common cohort operations
        buttonLayout = qt.QHBoxLayout()

        # Button to create/edit the selected cohort file
        createNewButton = qt.QPushButton(_("New"))
        buttonLayout.addWidget(createNewButton)

        # Buttons to edit/preview an existing cohort
        previewCohortButton = qt.QPushButton(_("Preview"))
        previewCohortButton.setEnabled(False)
        buttonLayout.addWidget(previewCohortButton)
        editCohortButton = qt.QPushButton(_("Edit"))
        editCohortButton.setEnabled(False)
        buttonLayout.addWidget(editCohortButton)

        # Cohort preview widget
        # TODO

        # Connections
        def onTextChanged(__: str):
            # If the input is valid (a '.csv' file) and exists, allow the user to edit and preview it
            enabled = self.is_current_path_valid()
            previewCohortButton.setEnabled(enabled)
            editCohortButton.setEnabled(enabled)
            # Emit a signal noting that the page's completeness may have changed
            self.completeChanged()
        cohortFileSelector.comboBox().currentTextChanged.connect(onTextChanged)

        # Add the button panel to our overall layout
        buttonWidget = qt.QWidget()
        buttonWidget.setLayout(buttonLayout)
        layout.addRow(buttonWidget)

    @property
    def cohort_path(self):
        # Workaround to CTK not playing nicely w/ "registerField"
        if self._cohortFileSelector is None:
            return None
        path = self._cohortFileSelector.currentPath
        if not path:
            return None
        return Path(path)

    def is_current_path_valid(self):
        cohort_path = self.cohort_path
        return cohort_path and cohort_path.is_file() and ".csv" in cohort_path.suffixes

    def isComplete(self):
        return self.is_current_path_valid()
