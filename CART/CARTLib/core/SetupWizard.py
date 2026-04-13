from pathlib import Path
from typing import TYPE_CHECKING, Optional, Iterable

import ctk
import qt
from slicer.i18n import tr as _

from CARTLib.core.TaskBaseClass import TaskBaseClass
from CARTLib.utils import CART_PATH
from CARTLib.utils.cohort import (
    cohort_from_generator,
    CohortTableWidget,
    CohortEditorDialog,
    NewCohortDialog,
    CohortModel,
)
from CARTLib.utils.config import JobProfileConfig, MasterProfileConfig, DictBackedConfig
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
        self,
        parent: qt.QWidget,
        taken_names: Iterable[str] = None,
        config: JobProfileConfig = None
    ):
        """
        Wizard for setting up a Job for use within CART.

        :param parent: Parent QT Widget.
        :param taken_names: Names which cannot be used by this job
            (usually because they are used by other registered jobs).
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

        # Generate and track the task-specific config, if there is one
        self.task_config: Optional[DictBackedConfig] = None
        task_type = CART_TASK_REGISTRY.get(self.config.task)
        if task_type is not None:
            self.task_config = task_type.init_config(config)

        # Workarounds for fields not playing nicely w/ CTK widgets
        self._taskPage = _TaskDefinitionPage(self.config, taken_names)
        self._dataPage = _DataSelectionPage(self.config)
        self._settingsPage = _TaskSettingsPage()

        # Add initial pages
        if config is None:
            # Only add the introduction page if this is a brand-new job
            self.addPage(self.introPage())
        self.addPage(self._taskPage)
        self.addPage(self._dataPage)
        self.addPage(self._settingsPage)
        self.addPage(self.conclusionPage())

        # Try to initialize the task page's GUI immediately
        self._settingsPage.initTaskGUI()

    ## Page Management ##
    def introPage(self):
        # Basic Attributes
        page = qt.QWizardPage(self)
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

    ## Utilities ##
    def taskChanged(self, new_label: str):
        # Confirm the new task type is properly registered with CART
        new_type = CART_TASK_REGISTRY.get(new_label, None)
        if not new_type:
            raise ValueError(
                f"Could not switch to task type '{new_type}', "
                f"no such task has been registered with CART."
            )

        # Purge config options added by the prior task (if any)
        self.config.purge_child_configs()

        # Create a new task config instance for our own reference
        self.task_config = new_type.init_config(self.config)

        # Update the rest of the Wizard to reflect the new task
        self._dataPage.changePreviewTask(new_type)
        self._settingsPage.initTaskGUI()

    def confirmDiscardChanges(self):
        # If no changes have been made, allow closing as-is
        if not self.config.has_changed:
            return True

        # Otherwise, confirm the user wants to discard changes made before doing so
        response = qt.QMessageBox.warning(
            self,
            _("Unsaved Changes"),
            _("Closing the wizard now would discard changes made to the job. Are you sure?"),
            qt.QMessageBox.Yes | qt.QMessageBox.No
        )
        # If the user confirms they want to close, proceed
        return response == qt.QMessageBox.Yes

    @qt.Slot()
    def reject(self):
        # Only reject if the user confirms discarding unsaved changes
        if self.confirmDiscardChanges():
            qt.QWizard.reject(self)

    # noinspection PyMethodOverriding
    def closeEvent(self, event: qt.QCloseEvent = None):
        if self.confirmDiscardChanges():
            event.accept()
        else:
            event.ignore()

    def save_config(self, logic: "CARTLogic") -> JobProfileConfig:
        """
        Save our currently managed config instances, using the CARTLogic
        instance passed to us.
        """
        # If the job's name has changed, purge the prior config entry
        if self._prior_name != self.config.name:
            logic.delete_job_config(self._prior_name)

        # Save our managed configuration file's changes
        if self.task_config is not None:
            self.task_config.save()
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

    def __init__(
        self,
        config: JobProfileConfig,
        taken_names: Iterable[str],
        parent: JobSetupWizard = None,
    ):
        super().__init__(parent)

        ## Basic Attributes ##
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

        ## Job name ##
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
        layout.addRow(jobNameLabel, jobNameEntry)

        # Set the job name to the current config's value (if any)
        job_name = config.name
        if job_name is not None:
            jobNameEntry.setText(job_name)

        # Highlight the text box in red if the name is already taken
        default_style = jobNameEntry.styleSheet
        error_style = "QLineEdit { color: red }"
        duplicateJobToolTip = _("Job with this name already exists!")

        @qt.Slot(str)
        def onJobNameChanged(new_txt: str):
            # Update the backing config to use the new name
            config.name = new_txt

            # Update the formatting of the name to indicate an error if present
            if new_txt in taken_names:
                jobNameEntry.setStyleSheet(error_style)
                jobNameEntry.setToolTip(duplicateJobToolTip)
            else:
                jobNameEntry.setStyleSheet(default_style)
                jobNameEntry.setToolTip(jobNameTooltip)

            # Emit the "completion changed" signal
            self.completeChanged()
        jobNameEntry.textChanged.connect(onJobNameChanged)

        ## Task selection ##
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
        taskSelectionLabel.setBuddy(taskSelectionWidget)
        layout.addRow(taskSelectionLabel, taskSelectionWidget)

        # Set the task's value to match our config's (if any)
        task_id = config.task
        if task_id is not None:
            taskSelectionWidget.setCurrentText(task_id)
        else:
            taskSelectionWidget.setCurrentIndex(-1)

        ## Task description ##
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
        @qt.Slot(str)
        def onSelectedTaskChanged(new_task: str):
            # Update the task description to inform the user
            task = CART_TASK_REGISTRY.get(new_task)
            # If no task was found, display error text and set the job's task to None (null)
            if task is None:
                error_text = _(
                    '<span style=" font-size:8pt; font-weight:600; color:#ff0000;" >'
                    f"ERROR! The file for the selected task could not be accessed! "
                    "Please check that the associated drive is mounted, "
                    "and that it can be accessed with Slicer's current permission level!"
                    "</span>"
                )
                config.task = None
                taskDescriptionWidget.setText(error_text)
            # Otherwise, update the task as expected
            else:
                config.task = new_task
                taskDescriptionWidget.setMarkdown(task.description())

            # Notify our wizard to run the corresponding changes downwind
            self.wizard().taskChanged(new_task)

            # Signal that the completion state may have changed
            self.completeChanged()
        taskSelectionWidget.currentTextChanged.connect(onSelectedTaskChanged)

        # Set the initial description to match the selected task (if any)
        if task_id:
            task = CART_TASK_REGISTRY.get(task_id)
            if task is not None:
                taskDescriptionWidget.setMarkdown(task.description())

        # Add it to the layout
        layout.addRow(taskDescriptionWidget)

        ## Tracked Widgets ##
        self.jobNameEntry = jobNameEntry
        self.taskSelectionWidget = taskSelectionWidget

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
        # Confirm this is a valid task before returning the result
        task_class = CART_TASK_REGISTRY.get(task_name)
        if task_class is None:
            return None
        return task_name

    @selected_task.setter
    def selected_task(self, new_task: str):
        task_class = CART_TASK_REGISTRY.get(new_task, None)
        if task_class is None:
            self.taskSelectionWidget.setCurrentIndex(-1)
        else:
            self.taskSelectionWidget.setCurrentText(new_task)

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
    def __init__(
        self,
        config: JobProfileConfig,
        parent: JobSetupWizard = None
    ):
        """
        Constructor

        :param config: The job profile config this page should reference.
        :param parent: The parent widget for QT hierarchy management.
        """
        super().__init__(parent)

        ## Basic Attributes ##
        self.setTitle(_("Data Selection"))
        layout = qt.QFormLayout(self)

        ## Instruction text ##
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

        ## Data Path ##
        dataPathLabel = qt.QLabel(_("Data Path:"))
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

        # Initialize ourselves to match the config
        data_path = config.data_path
        if data_path is not None:
            dataPathEntry.currentPath = str(data_path)

        ## Output Path ##
        outputPathLabel = qt.QLabel(_("Output Path:"))
        outputPathEntry: CARTPathLineEdit = CARTPathLineEdit()
        outputPathToolTip = _(
            "The structure and format of output files depends on your selected task and its settings; "
            "you'll probably be able to configure this more in the next page."
        )
        outputPathLabel.setToolTip(outputPathToolTip)
        outputPathEntry.setToolTip(outputPathToolTip)
        outputPathEntry.setPlaceholderText(
            _("Where the saved results/edits from your task should be placed.")
        )
        outputPathEntry.filters = ctk.ctkPathLineEdit.Dirs
        outputPathLabel.setBuddy(outputPathEntry)
        self._outputPathEntry = outputPathEntry
        layout.addRow(outputPathLabel, outputPathEntry)

        # Update ourselves to match the config
        out_path = config.output_path
        if out_path is not None:
            outputPathEntry.currentPath = str(out_path)

        ## Cohort File ##
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
        self._cohortFileSelector = cohortFileSelector
        layout.addRow(cohortFileLabel, cohortFileSelector)

        # Update ourselves to match the config
        cohort_file = config.cohort_path
        if cohort_file is not None:
            cohortFileSelector.currentPath = str(cohort_file)

        ## Cohort Button Panel ##
        buttonLayout = qt.QHBoxLayout()

        # Button to create the selected cohort file
        createNewButton = qt.QPushButton(_("New Cohort File"))
        createNewButton.setToolTip(
            _(
                "Generate a cohort file from scratch. "
                "Will reference the contents of your input directory to do so, whenever possible."
            )
        )

        def shouldEnableCreate():
            return config.data_path is not None and config.data_path.is_dir()

        createNewButton.setEnabled(shouldEnableCreate())

        editCohortButton = qt.QPushButton(_("Edit Cohort File"))
        editCohortButton.setToolTip(
            _(
                "Edit the selected selected cohort file. "
                "Changes are not saved until you explicitly request them."
            )
        )

        def shouldEnabledEdit():
            return shouldEnableCreate() and config.cohort_path is not None
        editCohortButton.setEnabled(shouldEnabledEdit())

        # User prompt connections
        createNewButton.clicked.connect(self.createNewCohort)
        editCohortButton.clicked.connect(self.editCohort)

        buttonLayout.addWidget(createNewButton)
        buttonLayout.addWidget(editCohortButton)
        layout.addRow(buttonLayout)

        ## Cohort Preview ##
        cohortPreviewWidget = CohortTableWidget.from_path(
            config.cohort_path,
            config.data_path,
            # It's a preview, so disable editing
            editable=False
        )

        # Give it a distinct frame
        cohortPreviewWidget.setFrameShape(qt.QFrame.Panel)
        cohortPreviewWidget.setFrameShadow(qt.QFrame.Sunken)
        cohortPreviewWidget.setLineWidth(3)

        # Add it to the layout and track it
        self._cohortPreviewWidget = cohortPreviewWidget
        layout.addRow(cohortPreviewWidget)

        # Update its reference task, if the provided config already had one
        if config.task:
            task_ref = CART_TASK_REGISTRY.get(config.task)
            if task_ref is not None:
                self.changePreviewTask(task_ref)

        ## Connections ##
        @qt.Slot(str)
        def onDataPathChanged(new_txt: str):
            # Enable the "create" button if our conditions are met now
            createNewButton.setEnabled(shouldEnableCreate())
            # Update the data path to match our new value
            config.data_path = Path(new_txt)
            # Denote that the completion state has likely changed
            self.completeChanged()
        dataPathEntry.textChanged.connect(onDataPathChanged)

        @qt.Slot(str)
        def onOutputPathChanged(new_text: str):
            config.output_path = Path(new_text)
            self.completeChanged()
        outputPathEntry.textChanged.connect(onOutputPathChanged)

        @qt.Slot(str)
        def onCohortPathChanged(new_txt: str):
            # Enable the "edit" button if there is now text
            editCohortButton.setEnabled(shouldEnabledEdit())
            # Preview the provided cohort file, if it exists
            if new_txt != "":
                cohortPreviewWidget.backing_csv = Path(new_txt)
            else:
                cohortPreviewWidget.backing_csv = None
            # Mark that the completion state has likely changed
            self.completeChanged()

        cohortFileSelector.textChanged.connect(onCohortPathChanged)

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
    def changePreviewTask(self, new_type: type[TaskBaseClass]):
        # Update the preview widget's reference task to use the new type
        self._cohortPreviewWidget.tableView.model().reference_task = new_type

    def createNewCohort(self):
        """
        Walk the user through the creation of a new cohort file from scratch
        """
        # Prompt the user for the new cohort file's specifications
        dialog = NewCohortDialog(self.data_path)

        # If the user backs out or cancels, end here
        if not dialog.exec():
            return

        # Create the backing cohort (and its associated files)
        cohort = cohort_from_generator(
            dialog.cohort_file, self.data_path, dialog.current_generator
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
            if self._cohortPreviewWidget.currentWidget() == self._cohortPreviewWidget.tableView:
                self._cohortPreviewWidget.model.load()
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


class _TaskSettingsPage(qt.QWizardPage):
    def __init__(self, parent: JobSetupWizard = None):
        super().__init__(parent)

        # Initialize w/ our default layout
        self.resetToDefaultLayout()

    def resetToDefaultLayout(self):
        # Assign the old layout to a temporary widget to re-parent it
        if self.layout():
            tmp = qt.QWidget(None)
            tmp.setLayout(self.layout())
            del tmp

        # Generate the placehold layout
        defaultLayout = qt.QFormLayout(self)
        defaultText = qt.QLabel(
            _(
                "The selected task provided no user-configurable options! "
                "You should ask the developer to rectify this!"
            )
        )
        defaultLayout.addRow(defaultText)

        # Update our layout + title
        self.setTitle("No Task Configurations Found!")
        self.setLayout(defaultLayout)

    def initTaskGUI(self):
        """
        Update the task-specific GUI layout to use a given task's layout
        If none is available, use the default instead.
        """
        # Check if there's a config to generate a GUI for
        task_config = self.wizard().task_config
        if task_config is None:
            self.resetToDefaultLayout()
            return

        # Confirm that there is actually a GUI to render
        result = task_config.generateGUILayout()
        if result is None:
            self.resetToDefaultLayout()
            return

        # Assign the old layout to a temporary widget to re-parent it
        if self.layout():
            tmp = qt.QWidget(None)
            tmp.setLayout(self.layout())
            del tmp

        # Swap in the new title and layout
        title, layout = result
        self.setTitle(title)
        self.setLayout(layout)
