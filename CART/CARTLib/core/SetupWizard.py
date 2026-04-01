from pathlib import Path
from typing import TYPE_CHECKING, Optional, Iterable

import ctk
import qt
from slicer.i18n import tr as _

from CARTLib.utils import CART_PATH
from CARTLib.utils.cohort import (
    cohort_from_generator,
    CohortTableWidget,
    CohortEditorDialog,
    NewCohortDialog,
)
from CARTLib.utils.config import JobProfileConfig, MasterProfileConfig
from CARTLib.utils.task import CART_TASK_REGISTRY
from CARTLib.utils.widgets import CARTPathLineEdit

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

    def __init__(self, parent, prior_config: MasterProfileConfig = None):
        super().__init__(parent)

        # The to-be-tracked prior config (if any)
        self.prior_config = prior_config

        # Standard elements
        self.setWindowTitle(_("User Profile Setup"))
        self.setPixmap(qt.QWizard.LogoPixmap, CART_LOGO_PIXMAP)

        # Add pages
        if prior_config is None:
            self.addPage(self.createIntroPage())
        profilePage = _ProfileWizardPage(None, prior_config)
        self.addPage(profilePage)
        self.profilePage = profilePage
        if prior_config is None:
            self.addPage(self.createConclusionPage())

    ## Static Pages ##
    @staticmethod
    def createIntroPage():
        # Basic Attributes
        page = qt.QWizardPage(None)
        page.setTitle(_("Introduction"))
        layout = qt.QVBoxLayout()
        page.setLayout(layout)

        # Introduction text
        label = qt.QLabel(
            _(
                "Welcome to CART! This wizard will help you get started with CART."
            )
        )
        label.setWordWrap(True)
        layout.addWidget(label)

        return page

    @staticmethod
    def createConclusionPage():
        # Basic Attributes
        page = qt.QWizardPage()
        page.setTitle(_("Next Steps"))
        layout = qt.QVBoxLayout()
        page.setLayout(layout)

        # Introduction text
        label = qt.QLabel(
            _(
                "You have finished initial setup; you will now be prompted to set up your first CART Job."
            )
        )
        label.setWordWrap(True)
        layout.addWidget(label)

        return page

    ## Properties ##
    @property
    def author(self) -> str:
        return self.profilePage.author

    @property
    def position(self) -> str:
        return self.profilePage.position

    ## Utils ##
    def update_logic(self, logic: "CARTLogic"):
        # Update the logic's attributes
        logic.author = self.author
        logic.position = self.position if self.position != "" else None

        # Have the logic save its config immediately
        logic.save_master_config()


class JobSetupWizard(qt.QWizard):
    def __init__(
        self, parent, taken_names: Iterable[str] = None, config: JobProfileConfig = None
    ):
        """
        Wizard for setting up a Job for use within CART.

        :param parent: Parent QT Widget
        :param config: Reference job config to update. If none is provided,
            a new config instance will be made, and need to be saved.
        """
        super().__init__(parent)

        # Standard elements
        self.setWindowTitle(_("Job Setup"))
        self.setPixmap(qt.QWizard.LogoPixmap, CART_LOGO_PIXMAP)

        # Generate our backing configuration, tracking the original name for later
        self._prior_name = None
        if config is None:
            self.config = JobProfileConfig()
        else:
            if config.name is not None:
                self._prior_name = config.name
            taken_names = [n for n in taken_names if n != config.name]
            self.config = config

        # Workarounds for fields not playing nicely w/ CTK widgets
        self._taskPage = _TaskDefinitionPage(self, taken_names=taken_names)
        self._dataPage = _DataSelectionPage(self)

        # self._dataPage = _DataWizardPage(self, taken_names=taken_names)
        # self._taskPage = _TaskWizardPage(self)
        # self._cohortPage = _CohortWizardPage(self)

        # Add initial pages
        if config is None:
            # Only add the introduction page if this is a brand-new job
            self.addPage(self.introPage())
        self.addPage(self._taskPage)
        self.addPage(self._dataPage)
        self.addPage(self.conclusionPage())

        # If we had a starting config, initialize our fields to match it
        if config is not None:
            self._initFields()

    def _initFields(self):
        self.job_name = self.config.name
        data_path = self.config.data_path
        self.data_path = data_path if data_path else ""
        output_path = self.config.output_path
        self.output_path = output_path if output_path else ""
        self.selected_task = self.config.task
        self.cohort_path = self.config.cohort_path

    ## Page Management ##
    @staticmethod
    def introPage():
        # Basic Attributes
        page = qt.QWizardPage()
        page.setTitle(_("Introduction"))
        layout = qt.QVBoxLayout()
        page.setLayout(layout)

        # Introduction text
        label = qt.QLabel("")
        text = _(
            "This wizard will walk you through creating a Job for CART to run. "
            "Through this you will be prompted to answer the following:\n"
            "   1. What do you want to do, and how should it be done?\n"
            "   2. Which files would you like to use, and how do you want to iterate through them?\n"
            "   3. How should the results be handled, and where should they be saved?\n"
            "\n"
            "If you are unsure about what a specific element in the Wizard is, or what it would do, "
            "hover your mouse over it; a tooltip with more details will usually appear. "
            "You can also reference the "
            '[CART repository](https://github.com/SomeoneInParticular/CART) '
            "for further details, or "
            '[open an issue](https://github.com/SomeoneInParticular/CART/issues) '
            "with any questions or concerns you may have."
        )
        label.setText(text)
        # TODO; Find how to properly reference this enum
        label.setTextFormat(3)  # 3 -> Markdown enum value
        label.setToolTip(_("See?"))
        label.setOpenExternalLinks(True)
        label.setWordWrap(True)
        layout.addWidget(label)

        return page

    @staticmethod
    def conclusionPage():
        # TODO: Replace this with seamless task-config carry-over
        # Basic Attributes
        page = qt.QWizardPage(None)
        page.setTitle(_("Done!"))
        layout = qt.QVBoxLayout()
        page.setLayout(layout)

        # Introduction text
        label = qt.QLabel(
            _(
                "Click 'Finish' below to save the Job configuration; this will "
                "register your job (with any changes you made) to CART."
                "\n\n"
                "If the job does not start automatically, you can select the "
                "job's name from the drop-down and click 'Start' to start it "
                "instead."
                "\n\n"
                "Thank you for choosing CART as your imaging analysis tool!"
            )
        )
        label.setWordWrap(True)
        layout.addWidget(label)

        return page

    ## Attributes ##
    @property
    def job_name(self) -> str:
        return self._taskPage.job_name

    @job_name.setter
    def job_name(self, new_name: str):
        self._taskPage.job_name = new_name

    @property
    def selected_task(self) -> Optional[str]:
        return self._taskPage.selected_task

    @selected_task.setter
    def selected_task(self, new_task: str):
        self._taskPage.selected_task = new_task

    @property
    def data_path(self) -> Optional[Path]:
        return self._dataPage.data_path

    @data_path.setter
    def data_path(self, new_path: Path):
        self._dataPage.data_path = new_path

    @property
    def output_path(self):
        return self._dataPage.output_path

    @output_path.setter
    def output_path(self, new_path: Path):
        self._dataPage.output_path = new_path

    @property
    def cohort_path(self) -> Optional[Path]:
        return self._dataPage.cohort_path

    @cohort_path.setter
    def cohort_path(self, new_path: Path):
        self._dataPage.cohort_path = new_path

    def save_config(self, logic: "CARTLogic") -> JobProfileConfig:
        # Generate the new config and immediately save it
        self.config.name = self.job_name
        self.config.data_path = self.data_path
        self.config.output_path = self.output_path
        self.config.task = self.selected_task
        self.config.cohort_path = self.cohort_path

        # If the job's name has changed, purge the prior config entry
        if self._prior_name != self.config.name:
            logic.delete_job_config(self._prior_name)

        # Save the new config to file
        self.config.save()

        # Register the new job
        logic.register_job_config(self.config)

        return self.config


## Wizard Pages ##
class _ProfileWizardPage(qt.QWizardPage):

    AUTHOR_KEY = "author"
    POSITION_KEY = "position"

    def __init__(self, parent=None, prior_config: MasterProfileConfig = None):
        super().__init__(parent)

        # Basic Attributes
        self.setTitle(_("Profile Creation"))
        layout = qt.QFormLayout(self)

        # Instruction text
        instructionLabel = qt.QLabel(_("Please fill out the following fields:"))
        instructionLabel.setWordWrap(True)
        layout.addRow(instructionLabel)

        # Author name
        authorLabel = qt.QLabel(_("Author:"))
        authorLineEdit = qt.QLineEdit()
        authorLineEdit.setPlaceholderText(_("How you want to be identified."))
        authorLabel.setBuddy(authorLineEdit)
        layout.addRow(authorLabel, authorLineEdit)
        # The asterisk marks this field as "mandatory"
        self.registerField(self.AUTHOR_KEY + "*", authorLineEdit)
        authorLineEdit.textChanged.connect(lambda: self.completeChanged())

        # Position
        positionLabel = qt.QLabel(_("Position"))
        positionLineEdit = qt.QLineEdit()
        positionLineEdit.setPlaceholderText(
            _("Clinician, Research Associate, Student etc.")
        )
        positionLabel.setBuddy(positionLineEdit)
        layout.addRow(positionLabel, positionLineEdit)
        self.registerField(self.POSITION_KEY, positionLineEdit)

        # Load the previous configuration values if they were provided
        if prior_config is not None:
            if (author := prior_config.author) is not None:
                authorLineEdit.setText(author)
            if (position := prior_config.position) is not None:
                positionLineEdit.setText(position)

    ## Fields/Properties ##
    @property
    def author(self) -> str:
        return self.field(self.AUTHOR_KEY)

    @property
    def position(self) -> str:
        return self.field(self.POSITION_KEY)

    def isComplete(self):
        return self.author != ""


class _TaskDefinitionPage(qt.QWizardPage):
    def __init__(self, parent=None, taken_names=Iterable[str]):
        super().__init__(parent)

        # Basic Attributes
        self.setTitle(_("Name and Task"))
        layout = qt.QFormLayout(self)

        # Track the list of names already used by other Jobs so far
        self._taken_names = taken_names

        # Instruction text
        instructionLabel = qt.QLabel(
            _(
                "Please give this job a name, and select the task you would like this Job to run."
            )
        )
        instructionLabel.setWordWrap(True)
        layout.addRow(instructionLabel)

        # Job name
        jobNameLabel = qt.QLabel(_("Job Name:"))
        jobNameEntry = qt.QLineEdit()
        jobNameTooltip = _(
            "This label will be used to identify the Job within CART. "
            "It can be any valid string, though you should try and name it something you'll remember later."
        )
        jobNameLabel.setToolTip(jobNameTooltip)
        jobNameEntry.setToolTip(jobNameTooltip)
        jobNameEntry.setPlaceholderText(
            _(
                "You will use this name to 'resume' the job if you close and reopen CART."
            )
        )
        jobNameLabel.setBuddy(jobNameEntry)
        self.jobNameEntry = jobNameEntry
        layout.addRow(jobNameLabel, jobNameEntry)
        jobNameEntry.textChanged.connect(
            lambda __: self.completeChanged()
        )

        # Task selection
        taskSelectionLabel = qt.QLabel(_("Task: "))
        taskSelectionWidget = qt.QComboBox(None)
        taskSelectionToolTip = _(
            "The task determines what CART will do each time you load a set of files, what actions you can take, "
            "and how your changes will be saved. Read the description below for further details."
        )
        taskSelectionLabel.setToolTip(taskSelectionToolTip)
        taskSelectionWidget.setToolTip(taskSelectionToolTip)
        taskSelectionWidget.addItems(list(CART_TASK_REGISTRY.keys()))
        # This doesn't work; keeping it here in case Slicer ever fixes this bug
        taskSelectionWidget.placeholderText = _("[None Selected]")
        taskSelectionWidget.setCurrentIndex(-1)
        taskSelectionLabel.setBuddy(taskSelectionWidget)
        layout.addRow(taskSelectionLabel, taskSelectionWidget)
        self.taskSelectionWidget = taskSelectionWidget

        # Task description
        taskDescriptionWidget = qt.QTextBrowser(None)
        taskDescriptionWidget.setText(
            _("Details about your selected task will appear here.")
        )
        taskDescriptionWidget.setOpenExternalLinks(True)
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
                error_text = _(
                    '<span style=" font-size:8pt; font-weight:600; color:#ff0000;" >'
                    f"ERROR! The file for the selected task could not be accessed! "
                    "Please check that the associated drive is mounted, "
                    "and that it can be accessed with Slicer's current permission level!"
                    "</span>"
                )
                taskDescriptionWidget.setText(error_text)
            else:
                taskDescriptionWidget.setMarkdown(task.description())
            self.completeChanged()

        taskSelectionWidget.currentTextChanged.connect(onSelectedTaskChanged)

        # Add it to the layout
        layout.addRow(taskDescriptionWidget)

    @property
    def job_name(self) -> str:
        # noinspection PyTypeChecker
        return self.jobNameEntry.text

    @job_name.setter
    def job_name(self, new_name: str):
        self.jobNameEntry.setText(new_name)

    @property
    def selected_task(self) -> Optional[str]:
        # noinspection PyTypeChecker
        task_name: str = self.taskSelectionWidget.currentText
        if task_name is None:
            return None
        # Confirm this is a valid task before returning the result
        task_class = CART_TASK_REGISTRY.get(task_name, None)
        if task_class is None:
            return None
        return task_name

    @selected_task.setter
    def selected_task(self, new_task: str):
        task_class = CART_TASK_REGISTRY.get(new_task, None)
        if task_class is None:
            self.taskSelectionWidget.setCurrentIndex(-1)
        else:
            idx = self.taskSelectionWidget.findText(new_task)
            self.taskSelectionWidget.setCurrentIndex(idx)

    def isComplete(self):
        # If we're missing a job name, said name was already taken,
        # or we don't have a task, return false
        return not any(
            [
                self.job_name == "",
                self.job_name in self._taken_names,
                self.selected_task is None,
            ]
        )


class _DataSelectionPage(qt.QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Basic Attributes
        self.setTitle(_("Data Selection"))
        layout = qt.QFormLayout(self)

        # Instruction text
        instructionText = _(
            "Please define the directory containing the files to use (the “Input Path”), "
            "where you would like the results saved (the “Output Path”), "
            "and how you would like to iterate through it (the “Cohort File”)."
            "\n\n"
            "If you have a cohort file you would like to reuse, click the “...” button to select it; "
            "otherwise, click 'New' to generate a cohort file from scratch."
        )
        instructionLabel = qt.QLabel(instructionText)
        instructionLabel.setWordWrap(True)
        layout.addRow(instructionLabel)

        # Data path
        dataPathLabel = qt.QLabel(_("Input Path:"))
        dataPathEntry: CARTPathLineEdit = CARTPathLineEdit()
        dataPathToolTip = _(
            "The path given here will be treated as the 'source' path when CART is looking for files."
        )
        dataPathLabel.setToolTip(dataPathToolTip)
        dataPathEntry.setToolTip(dataPathToolTip)
        dataPathEntry.setPlaceholderText(
            _("The folder containing the files you want to use, i.e. a BIDS dataset.")
        )
        dataPathEntry.filters = ctk.ctkPathLineEdit.Dirs
        dataPathLabel.setBuddy(dataPathEntry)
        self._dataPathEntry = dataPathEntry
        layout.addRow(dataPathLabel, dataPathEntry)

        # Output path
        outputPathLabel = qt.QLabel(_("Output Path:"))
        outputPathEntry: CARTPathLineEdit = CARTPathLineEdit()
        outputPathToolTip = _(
            "The structure and format of output files depends on your selected task and its settings; "
            "you'll probably be able to configure this more in the next page."
        )
        outputPathLabel.setToolTip(outputPathToolTip)
        outputPathEntry.setToolTip(outputPathToolTip)
        outputPathEntry.setPlaceholderText(
            _("Where the saved results/edits from your task should be saved.")
        )
        outputPathEntry.filters = ctk.ctkPathLineEdit.Dirs
        outputPathLabel.setBuddy(outputPathEntry)
        self._outputPathEntry = outputPathEntry
        layout.addRow(outputPathLabel, outputPathEntry)

        # Cohort file
        cohortFileLabel = qt.QLabel(_("Cohort File:"))
        cohortFileSelector: CARTPathLineEdit = CARTPathLineEdit()
        cohortFileToolTip = _(
            "This file dictates how CART will iterate through your dataset and load files. "
            "See your task's documentation for further details on what is required here, and "
            "how it should be formatted."
        )
        cohortFileLabel.setToolTip(cohortFileToolTip)
        cohortFileSelector.setToolTip(cohortFileToolTip)
        cohortFileSelector.setPlaceholderText(
            _(
                "A CSV file, with one row per iteration (case) CART should run, "
                "and one column per resource each iteration should try to load."
            )
        )
        cohortFileSelector.filters = ctk.ctkPathLineEdit.Files
        cohortFileSelector.nameFilters = [
            "CSV files (*.csv)",
        ]
        self._cohortFileSelector = cohortFileSelector
        layout.addRow(cohortFileLabel, cohortFileSelector)

        # Cohort create/edit button panel
        buttonLayout = qt.QHBoxLayout()

        # Button to create the selected cohort file
        createNewButton = qt.QPushButton(_("New Cohort File"))
        createNewButton.setToolTip(
            _(
                "Generate a cohort file from scratch. "
                "Will reference the contents of your input directory to do so, whenever possible."
            )
        )
        editCohortButton = qt.QPushButton(_("Edit Cohort File"))
        editCohortButton.setToolTip(
            _(
                "Edit the selected selected cohort file. "
                "Changes are not saved until you explicitly request them."
            )
        )
        buttonLayout.addWidget(createNewButton)
        buttonLayout.addWidget(editCohortButton)
        layout.addRow(buttonLayout)

        # Cohort preview widget; it's a preview, so disable editing
        cohortPreviewWidget = CohortTableWidget.from_path(None, editable=False)
        cohortPreviewWidget.setFrameShape(qt.QFrame.Panel)
        cohortPreviewWidget.setFrameShadow(qt.QFrame.Sunken)
        cohortPreviewWidget.setLineWidth(3)
        self._cohortPreviewWidget = cohortPreviewWidget
        layout.addRow(cohortPreviewWidget)

        # Connections
        @qt.Slot(str)
        def onDataPathChanged(new_txt: str):
            # Enable the "create" button if there is now text
            createNewButton.setEnabled(new_txt != "" and Path(new_txt).is_dir())
            # Denote that the completion state has likely changed
            self.completeChanged()
        dataPathEntry.textChanged.connect(onDataPathChanged)

        outputPathEntry.textChanged.connect(lambda: self.completeChanged())

        @qt.Slot(str)
        def onCohortPathChanged(new_txt: str):
            text_is_valid = new_txt != ""
            # Enable the "edit" button if there is now text
            editCohortButton.setEnabled(text_is_valid)
            # Preview the new cohort file, if it exists
            if text_is_valid:
                cohortPreviewWidget.backing_csv = Path(new_txt)
            else:
                cohortPreviewWidget.backing_csv = None
            # Mark that the completion state has likely changed
            self.completeChanged()

        cohortFileSelector.textChanged.connect(onCohortPathChanged)

        createNewButton.clicked.connect(self.createNewCohort)
        editCohortButton.clicked.connect(self.editCohort)

        # Sync and end
        onDataPathChanged("")
        onCohortPathChanged("")

    ## Properties ##
    @property
    def data_path(self) -> Optional[Path]:
        currentPath = self._dataPathEntry.currentPath
        if not currentPath:
            return None
        else:
            return Path(currentPath)

    @data_path.setter
    def data_path(self, new_path: Path):
        path_str = str(new_path)
        self._dataPathEntry.currentPath = path_str

    @property
    def output_path(self) -> Optional[Path]:
        currentPath = self._outputPathEntry.currentPath
        if not currentPath:
            return None
        else:
            return Path(currentPath)

    @output_path.setter
    def output_path(self, new_path: Path):
        path_str = str(new_path)
        self._outputPathEntry.currentPath = path_str

    @property
    def cohort_path(self) -> Optional[Path]:
        currentPath = self._cohortFileSelector.currentPath
        if not currentPath:
            return None
        else:
            return Path(currentPath)

    @cohort_path.setter
    def cohort_path(self, new_path: Path):
        path_str = str(new_path)
        self._cohortFileSelector.currentPath = path_str

    ## Utilities ##
    def createNewCohort(self):
        """
        Walk the user through the creation of a new cohort file from-scratch
        """
        # Prompt the user for the new cohort file's specifications
        dialog = NewCohortDialog(self.data_path)

        # If the user backs out or cancels, end here
        if not dialog.exec():
            return

        # Create the backing cohort (and its associated files)
        cohort = cohort_from_generator(
            dialog.cohort_name, self.data_path, self.output_path, dialog.current_generator
        )
        # Update the cohort's reference task to match ours
        task_id = self.wizard().selected_task
        cohort.reference_task = CART_TASK_REGISTRY.get(task_id, None)

        # Update the GUI's selected file to use the newly created cohort file
        self._cohortFileSelector.setCurrentPath(str(cohort.csv_path))

        # Begin editing the selected cohort
        self.editCohort()

    def editCohort(self):
        task_name = self.wizard().selected_task
        selected_task = CART_TASK_REGISTRY.get(task_name)
        if selected_task is None:
            raise ValueError(f"Cannot load task {task_name}, has not been registered!")
        dialog = CohortEditorDialog.from_paths(
            self.cohort_path, self.data_path, reference_task=selected_task
        )
        # Refresh the preview if the dialogue succeeded in changing something
        if dialog.exec():
            self._cohortPreviewWidget.refresh()
        # Disconnect it from everything, no matter what the user did.
        dialog.disconnectAll()

    def isComplete(self):
        to_check = [self.data_path, self.output_path, self.cohort_path]
        # Ensure all fields are filled (not blank)
        if not all(to_check):
            return False
        # Confirm the fields are the correct type of object (directory and/or path)
        if not self.data_path.is_dir() and self.output_path.is_dir():
            return False
        if not self.cohort_path.is_file():
            return False
        # If all checks pass, return True
        return True


class _DataWizardPage(qt.QWizardPage):
    def __init__(self, parent=None, taken_names=Iterable[str]):
        super().__init__(parent)

        # Basic Attributes
        self.setTitle(_("Data Specification"))
        layout = qt.QFormLayout(None)
        self.setLayout(layout)
        self._taken_names = taken_names

        # Instruction text
        instructionLabel = qt.QLabel(_("Please fill out the following fields:"))
        instructionLabel.setWordWrap(True)
        layout.addRow(instructionLabel)

        # Job name
        jobNameLabel = qt.QLabel(_("Job Name:"))
        jobNameEntry = qt.QLineEdit()
        jobNameTooltip = _(
            "This is the name that CART will use to track this Job; if you want to "
            "resume this Job after restarting Slicer, you would select the name you specify "
            "here before clicking 'Start' in CART. As such, don't use a previous job's name!"
        )
        jobNameLabel.setToolTip(jobNameTooltip)
        jobNameEntry.setToolTip(jobNameTooltip)
        jobNameEntry.setPlaceholderText(
            _("i.e. SpineSegReview, VesselClassification, BrainMarkup")
        )
        jobNameLabel.setBuddy(jobNameEntry)
        self.registerField(JOB_NAME_FIELD, jobNameEntry)
        layout.addRow(jobNameLabel, jobNameEntry)

        # Data path
        dataPathLabel = qt.QLabel(_("Input Path:"))
        dataPathEntry: qt.QWidget = ctk.ctkPathLineEdit()
        dataPathToolTip = _(
            "This should be a directory containing any data files you wish to use. "
            "Unless you specify absolute path's in your cohort (done later), this "
            "directory will be used as the 'root' directory when CART tries to find"
            "files to load."
        )
        dataPathLabel.setToolTip(dataPathToolTip)
        dataPathEntry.setToolTip(dataPathToolTip)
        dataPathEntry.filters = ctk.ctkPathLineEdit.Dirs
        dataPathLabel.setBuddy(dataPathEntry)
        # Workaround to CTK not playing nicely w/ "registerField"
        self._dataPathEntry = dataPathEntry
        layout.addRow(dataPathLabel, dataPathEntry)

        # Output path
        outputPathLabel = qt.QLabel(_("Output Path:"))
        outputPathEntry: qt.QWidget = ctk.ctkPathLineEdit()
        outputPathToolTip = _(
            "This is the directory the results/output of your Job be placed within. "
            "You should usually specify an empty directory for this to avoid data loss; "
            "if you explicitly want to overwrite your input data, however, you can use "
            "the 'Input Path' you specified above here too. WARNING; Each task (selected "
            "next) handles data output differently; read its documentation carefully before "
            "selecting an output directory that already contains files within it!"
        )
        outputPathLabel.setToolTip(outputPathToolTip)
        outputPathEntry.setToolTip(outputPathToolTip)
        outputPathEntry.filters = ctk.ctkPathLineEdit.Dirs
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

    @job_name.setter
    def job_name(self, new_str):
        self.field(JOB_NAME_FIELD, new_str)

    @property
    def data_path(self) -> Optional[Path]:
        # Workaround to CTK not playing nicely w/ "registerField"
        path = self._dataPathEntry.currentPath
        if not path:
            return None
        return Path(path)

    @data_path.setter
    def data_path(self, new_path: Path):
        path_str = str(new_path)
        self._dataPathEntry.currentPath = path_str

    @property
    def output_path(self) -> Optional[Path]:
        # Workaround to CTK not playing nicely w/ "registerField"
        path = self._outputPathEntry.currentPath
        if not path:
            return None
        return Path(path)

    @output_path.setter
    def output_path(self, new_path: Path):
        path_str = str(new_path)
        self._outputPathEntry.currentPath = path_str

    def isComplete(self):
        # If we don't have a job name yet, return false immediately
        if self.job_name == "":
            return False
        # Check if the name is already taken
        if self.job_name in self._taken_names:
            return False
        # Confirm a data path has been specified, and is a directory
        if not self.data_path or not self.data_path.is_dir():
            return False
        # Confirm an output path has been specified and is not a file
        if not self.output_path or self.output_path.is_file():
            return False
        # Otherwise we're done!
        return True


class _TaskWizardPage(qt.QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Basic Attributes
        self.setTitle(_("Task Selection"))
        layout = qt.QFormLayout()
        self.setLayout(layout)

        # Task selection
        taskDescriptionText = qt.QLabel(
            _(
                "The job's 'Task' determines what you want to do to your data. Examples include "
                "managing segmentations, placing markup labels, and classifying samples."
                "\n\n"
                "Select a Task using the dropdown below to display its intended use, considerations for "
                "how to use it, and any other relevant information its developer may have provided."
            )
        )
        taskDescriptionText.setWordWrap(True)
        layout.addRow(taskDescriptionText)
        taskSelectionLabel = qt.QLabel(_("Task: "))
        taskSelectionWidget = qt.QComboBox(None)
        taskSelectionToolTip = _(
            "If the details provided by the Task description below are insufficient, check out "
            "its formal documentation. If you installed the Task yourself, the repository you "
            'downloaded it from will likely have it. Otherwise, check the CART repo\'s "examples" '
            "directory; all tasks installed in CART by default are stored there."
        )
        taskSelectionLabel.setToolTip(taskSelectionToolTip)
        taskSelectionWidget.setToolTip(taskSelectionToolTip)
        taskSelectionWidget.addItems(list(CART_TASK_REGISTRY.keys()))
        # This doesn't work; keeping it here in case Slicer ever fixes this bug
        taskSelectionWidget.placeholderText = _("[None Selected]")
        taskSelectionWidget.setCurrentIndex(-1)
        taskSelectionLabel.setBuddy(taskSelectionWidget)
        layout.addRow(taskSelectionLabel, taskSelectionWidget)

        # Task description
        taskDescriptionWidget = qt.QTextBrowser(None)
        taskDescriptionWidget.setText(
            _("Details about your selected task will appear here.")
        )
        taskDescriptionWidget.setOpenExternalLinks(True)
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
                error_text = _(
                    '<span style=" font-size:8pt; font-weight:600; color:#ff0000;" >'
                    f"ERROR! The file for the selected task could not be accessed! "
                    "Please check that the associated drive is mounted, "
                    "and that it can be accessed with Slicer's current permission level!"
                    "</span"
                )
                taskDescriptionWidget.setText(error_text)
            else:
                taskDescriptionWidget.setMarkdown(task.description())
            self.completeChanged()

        taskSelectionWidget.currentTextChanged.connect(onSelectedTaskChanged)

        self.taskSelectionWidget = taskSelectionWidget
        # Add it to the layout
        layout.addRow(taskDescriptionWidget)

    @property
    def selected_task(self) -> Optional[str]:
        # Helper method to parse
        # noinspection PyTypeChecker
        task_name: str = self.taskSelectionWidget.currentText
        if task_name is None:
            return None
        # Confirm this is a valid task before returning the result
        task_class = CART_TASK_REGISTRY.get(task_name, None)
        if task_class is None:
            return None
        return task_name

    @selected_task.setter
    def selected_task(self, new_task: str):
        task_class = CART_TASK_REGISTRY.get(new_task, None)
        if task_class is None:
            self.taskSelectionWidget.setCurrentIndex(-1)
        else:
            idx = self.taskSelectionWidget.findText(new_task)
            self.taskSelectionWidget.setCurrentIndex(idx)

    def isComplete(self):
        return self.selected_task is not None


class _CohortWizardPage(qt.QWizardPage):
    """
    A wizard page that allows for selecting, creating, editing, and previewing cohort files.

    Has enough unique functionality (including a Qt override) to form its own class;
    """

    def __init__(self, parent=None):
        """
        The data path hook should return a path containing the file a cohort editor should search
        for; it is a function to allow it to be implicitly "synced" when needed, rather than
        being static post-init.
        """
        super().__init__(parent)

        # Basic Attributes
        self.setTitle(_("Define Cohort"))
        layout = qt.QFormLayout()
        self.setLayout(layout)

        # Wizard help for this page
        cohortDescriptionText = qt.QLabel(
            _(
                "The job's 'Cohort' dictates how data in your dataset will be organized and, "
                "by extension, iterated through. CART will load each row ('case') in this file, "
                "one-at-a-time, prompting you to complete the Task you selected prior before "
                "loading the next. Each column ('feature') represents a resource each case may have; "
                "this is usually a file on your computer, such as an imaging volume, organ segmentation, "
                "or positional label markup that should be associated with each given case."
                "\n\n"
                "If you do not already have a Cohort file for the dataset you wish to process, you can "
                "select 'New' below to generate one from scratch. You can also edit an existing cohort "
                "file by selecting it below and clicking 'Edit'."
            )
        )
        cohortDescriptionText.setWordWrap(True)
        layout.addRow(cohortDescriptionText)

        # Directory selection button
        cohortFileLabel = qt.QLabel(_("Cohort File: "))
        cohortFileSelector: qt.QWidget = ctk.ctkPathLineEdit()
        cohortFileToolTip = _(
            "If in doubt, create a Cohort file from scratch; given your dataset is in a BIDS-like format, "
            "CART will determine the best way to organized it into 'cases' for you. Even if it isn't, you "
            "can manually specify the folder(s) which contain data relevant to each case you want as well. "
            "Each feature can then be defined via file filters to auto-select each case's relevant file; then"
            "you're done!"
        )
        cohortFileLabel.setToolTip(cohortFileToolTip)
        cohortFileSelector.setToolTip(cohortFileToolTip)
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
        createNewButton.setToolTip(
            _(
                "Generate a new cohort file from scratch! Will attempt to parse the contents of "
                "the 'Input Data' folder you selected previously to determine which cases there "
                "should be."
            )
        )

        def onCreateClick():
            # Create and show the creator dialog
            data_path = self.wizard().data_path
            output_path = self.wizard().output_path
            dialog = NewCohortDialog(data_path)
            self.mediateCohortCreation(
                dialog, data_path, output_path, cohortFileSelector, cohortPreviewWidget
            )

        createNewButton.clicked.connect(onCreateClick)
        buttonLayout.addWidget(createNewButton)

        # Button to edit the selected CSV
        editCohortButton = qt.QPushButton(_("Edit"))
        editCohortButton.setEnabled(False)
        editCohortButton.setToolTip(
            _(
                "Modifies the selected cohort file; you can add, remove, or change each case and/or "
                "feature this way."
            )
        )

        def onEditClick():
            # Create and show the editor dialog
            wz: JobSetupWizard = self.wizard()
            data_path = wz.data_path
            reference_task = CART_TASK_REGISTRY[wz.selected_task]
            dialog = CohortEditorDialog.from_paths(
                self.cohort_path, data_path, reference_task=reference_task
            )
            self.mediateCohortEditor(dialog, cohortPreviewWidget)

        editCohortButton.clicked.connect(onEditClick)
        buttonLayout.addWidget(editCohortButton)

        # Button to preview the selected CSV
        previewCohortButton = qt.QPushButton(_("Preview"))
        previewCohortButton.setEnabled(False)
        previewCohortButton.setToolTip(
            _(
                "Preview the selected cohort file; the contents will appear in the widget below."
            )
        )
        buttonLayout.addWidget(previewCohortButton)

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

        # Cohort preview widget; it's a preview, so disable editing
        cohortPreviewWidget = CohortTableWidget.from_path(None, editable=False)

        def onPreviewClick():
            cohortPreviewWidget.backing_csv = self.cohort_path

        previewCohortButton.clicked.connect(onPreviewClick)
        # Add a border around it to visually distinguish it
        cohortPreviewWidget.setFrameShape(qt.QFrame.Panel)
        cohortPreviewWidget.setFrameShadow(qt.QFrame.Sunken)
        cohortPreviewWidget.setLineWidth(3)
        layout.addRow(cohortPreviewWidget)

    @property
    def cohort_path(self):
        # Workaround to CTK not playing nicely w/ "registerField"
        if self._cohortFileSelector is None:
            return None
        path = self._cohortFileSelector.currentPath
        if not path:
            return None
        return Path(path)

    @cohort_path.setter
    def cohort_path(self, new_path: Path):
        if self._cohortFileSelector is None:
            return
        if new_path is None:
            self._cohortFileSelector.currentPath = ""
        else:
            path_str = str(new_path)
            self._cohortFileSelector.currentPath = path_str

    def is_current_path_valid(self):
        cohort_path = self.cohort_path
        return cohort_path and cohort_path.is_file() and ".csv" in cohort_path.suffixes

    def isComplete(self):
        return self.is_current_path_valid()

    def mediateCohortCreation(
        self,
        dialog: NewCohortDialog,
        data_path: Path,
        output_path: Path,
        fileSelector: ctk.ctkPathLineEdit,
        previewWidget: CohortTableWidget,
    ):
        """
        Mediates GUI updates required after a Cohort is initialized.
        """
        result = dialog.exec()
        # If the user confirmed creation, create the file and proceed
        if result:
            # Create the backing cohort (and its associated files)
            cohort = cohort_from_generator(
                dialog.cohort_name, data_path, output_path, dialog.current_generator
            )
            # Update the cohort's reference task to match outs
            task_id = self.wizard().selected_task
            cohort.reference_task = CART_TASK_REGISTRY.get(task_id, None)
            # Update the GUI's selected file to match the newly created file
            fileSelector.setCurrentPath(str(cohort.csv_path))
            # Spawn and manage a cohort editor to continue building up the cohort
            editorDialog = CohortEditorDialog(cohort)
            self.mediateCohortEditor(editorDialog, previewWidget)

    def mediateCohortEditor(
        self, dialog: CohortEditorDialog, cohortPreview: CohortTableWidget
    ):
        """
        Updates our GUI in response to a Cohort Editor finishing
        """
        result = dialog.exec()
        # If the user confirmed the edits, preview the result on close
        if result:
            cohortPreview.backing_csv = self.cohort_path
        dialog.disconnectAll()
