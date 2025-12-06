import importlib
import logging
import sys
from pathlib import Path
from typing import Optional, TYPE_CHECKING

import vtk
import ctk
import qt
import slicer
from slicer import vtkMRMLScalarVolumeNode
from slicer.ScriptedLoadableModule import *
from slicer.i18n import tr as _
from slicer.util import VTKObservationMixin

from CARTLib.core.DataManager import DataManager
from CARTLib.core.TaskBaseClass import TaskBaseClass, DataUnitFactory
from CARTLib.core.SetupWizard import CARTSetupWizard, JobSetupWizard
from CARTLib.utils import CART_PATH, CART_VERSION
from CARTLib.utils.config import GLOBAL_CONFIG_PATH, GLOBAL_CONFIG, JobProfileConfig, MasterProfileConfig
from CARTLib.utils.task import CART_TASK_REGISTRY

if TYPE_CHECKING:
    import PyQt5.Qt as qt

#
# CART
#


class CART(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "CART"  # It's an acronym title, not really translate-able
        self.parent.categories = ["Utilities"]
        self.parent.dependencies = []  # No dependencies
        # TODO: Move these metadata contents into a standalone file which can
        #  be updated automatically as new PRs are made
        self.parent.contributors = [
            "Kalum Ost (Montréal Polytechnique)",
            "Kuan Yi (Montréal Polytechnique)",
            "Ivan Johnson-Eversoll (University of Iowa)",
        ]
        self.parent.helpText = _(
            """
                CART (Case Annotation and Review Tool) provides a set
                of abstract base classes for creating streamlined annotation
                workflows in 3D Slicer. The framework enables efficient
                iteration through medical imaging cohorts with customizable
                tasks and flexible data loading strategies.

                See more information on the
                <a href="https://github.com/SomeoneInParticular/CART/tree/main">GitHub repository</a>.
            """
        )
        # TODO: replace with organization, grant and thanks
        self.parent.acknowledgementText = _(
            """
                Originally created during Slicer Project Week #43.

                Special thanks the many members of the Slicer community who
                contributed to this work, including the many projects which
                were used as reference. Of note:
                <a href="https://github.com/neuropoly/slicercart">SlicerCART</a> (the name and general framework),
                <a href="https://github.com/JoostJM/SlicerCaseIterator">SlicerCaseIterator</a> (inspired much of our logic),
                <a href="https://github.com/SlicerUltrasound/SlicerUltrasound">SlicerUltrasound/AnnotateUltrasound</a> (basis for our UI design),
                and the many other projects discussed during the breakout session (notes
                <a href="https://docs.google.com/document/d/12XuYPVuRgy4RTuIabSIjy_sRrYSliewKhcbB1zJgXVI/">here.</a>)
            """
        )

        # Load our configuration
        GLOBAL_CONFIG.load_from_json()

        # Add CARTLib to the Python Path for ease of (re-)use
        import sys

        cartlib_path = (Path(__file__) / "CARTLib").resolve()
        sys.path.append(str(cartlib_path))


#
# CARTWidget
#
class CARTWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    def __init__(self, parent=None) -> None:
        """
        Called when the module is initialized by Slicer
        """
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)

        # Initialize our logic instance
        self.logic: CARTLogic = CARTLogic()

        # "Dummy" widget, in which the Task GUI will be placed
        self.taskWidget: qt.QWidget = None

        # Start button; fallback to start CART setup if the user backs out
        self.setupWidgetsGroup: ctk.ctkCollapsibleGroupBox = None
        self.startButton: qt.QPushButton = None

    def setup(self) -> None:
        """
        Called when the user opens the CART module within Slicer for the first time.
        """
        ScriptedLoadableModuleWidget.setup(self)

        # Dropdown to contain setup widgets, so they can be hidden once we're done
        setupWidgetsGroup = ctk.ctkCollapsibleGroupBox()
        setupWidgetsGroup.setTitle(_("Job Setup"))
        layout = qt.QFormLayout()
        setupWidgetsGroup.setLayout(layout)

        # A button to manually start (or change) a CART job
        if GLOBAL_CONFIG_PATH.exists():
            button_text = _("Start/Resume Job")
        else:
            button_text = _("Set Up CART")
        startButton = qt.QPushButton(button_text)
        startButton.clicked.connect(self.startButtonPressed)
        layout.addWidget(startButton)

        # Track everything for later
        self.setupWidgetsGroup = setupWidgetsGroup
        self.startButton = startButton

        # Add it to our overall GUI
        self.layout.addWidget(self.setupWidgetsGroup)

    ## Connections ##
    def startButtonPressed(self):
        # If this is the first time CART has been run, ask if they want to initialize
        if not GLOBAL_CONFIG_PATH.exists():
            self.initialSetupPrompt()
            return
        # If they haven't run a job before, ask if they want to do so
        elif self.logic.last_job_path is None or not self.logic.last_job_path.exists():
            self.jobSetupPrompt()
            return
        # Otherwise, ask if they want to resume their last job
        else:
            self.resumePrompt()

    ## User Prompts ##
    def initialSetupPrompt(self):
        # Ask the user if they want to begin initial setup
        # noinspection PyTypeChecker
        response = qt.QMessageBox.question(
            None,
            _("Initialize CART?"),
            _("CART has not been run before. Would you like to run setup now?"),
            qt.QMessageBox.Yes | qt.QMessageBox.No,
            qt.QMessageBox.Yes
        )

        # Initiate CART setup if they do
        if response == qt.QMessageBox.Yes:
            self.runInitialSetup()

    def jobSetupPrompt(self):
        # Ask the user if they want to begin job setup
        # noinspection PyTypeChecker
        response = qt.QMessageBox.question(
            None,
            _("Create Job?"),
            _("You have not run a CART job before. Would you like to set up a job now?"),
            qt.QMessageBox.Yes | qt.QMessageBox.No,
            qt.QMessageBox.Yes
        )

        # Initiate Job setup if they do
        if response == qt.QMessageBox.Yes:
            self.runNewJobSetup()

    def resumePrompt(self):
        # noinspection PyTypeChecker
        response = qt.QMessageBox.question(
            None,
            _("Resume?"),
            _("Would you like to resume the last job you ran within CART?"),
            qt.QMessageBox.Yes | qt.QMessageBox.No,
            qt.QMessageBox.Yes
        )

        if response == qt.QMessageBox.Yes:
            self.logic.set_active_job(self.logic.last_job_name)
            print(self.logic.active_job_config.backing_dict)
        else:
            print("-" * 100)

    def runInitialSetup(self):
        initSetupWizard = CARTSetupWizard(None)
        result = initSetupWizard.exec()

        # If we got an "accept" signal, update our logic and begin job setup
        if result == qt.QDialog.Accepted:
            initSetupWizard.update_logic(self.logic)
            self.runNewJobSetup()

    def runNewJobSetup(self):
        jobSetupWizard = JobSetupWizard(None)
        result = jobSetupWizard.exec()

        # If we got an "accept" signal, create the job config and initialize it
        if result == qt.QDialog.Accepted:
            new_config = jobSetupWizard.generate_new_config(self.logic)
            self.logic.set_active_job(new_config.name)

    ## View Management ##
    def cleanup(self) -> None:
        """
        Called when the application closes and this widget is about to be destroyed.
        """
        pass

    def enter(self):
        # Delegate to our logic to have tasks properly update
        self.logic.enter()

    def exit(self):
        # Delegate to our logic to have tasks properly update
        self.logic.exit()


#
# CARTLogic
#
class CARTLogic(ScriptedLoadableModuleLogic):
    def __init__(self):
        ScriptedLoadableModuleLogic.__init__(self)

        # Attribute declaration
        self.master_profile_config: MasterProfileConfig = MasterProfileConfig()
        self.active_job_config: Optional[JobProfileConfig] = None
        self._data_manager: Optional[DataManager] = None
        self._task_instance: Optional[TaskBaseClass] = None
        self._data_unit_factory: Optional[DataUnitFactory] = None

        # Logging
        self.logger = logging.getLogger("CARTLogic")

        # Attempt to load the config into memory
        self.reload_master_config()

        # Attempt to fetch all loaded tasks
        self.load_registered_tasks()

    ## Attributes
    @property
    def author(self) -> str:
        return self.master_profile_config.author

    @author.setter
    def author(self, new_author: str):
        self.master_profile_config.author = new_author

    @property
    def position(self) -> str:
        return self.master_profile_config.position

    @position.setter
    def position(self, new_position: str):
        self.master_profile_config.position = new_position

    ## Job Management ##
    @property
    def registered_jobs(self) -> dict[str, str]:
        return self.master_profile_config.registered_jobs

    @property
    def registered_jobs_names(self) -> list[str]:
        # Shortcut function for easy reference.
        return list(self.master_profile_config.registered_jobs.keys())

    @property
    def last_job_name(self):
        return self.master_profile_config.last_job[0]

    @property
    def last_job_path(self) -> Optional[Path]:
        if self.master_profile_config.last_job is None:
            return None
        else:
            return Path(self.master_profile_config.last_job[1])

    def set_active_job(self, job_name: str):
        """
        Loads the specified job, based on its associated config
        """
        # Confirm the requested job is registered
        if not job_name in self.registered_jobs.keys():
            raise ValueError(f"Cannot set job '{job_name}' as active; it has not been registered!")

        # Confirm the job config file exist
        job_file = Path(self.registered_jobs.get(job_name))
        if not job_file.exists() or not job_file.is_file():
            raise ValueError(f"Cannot set job '{job_name}' as active; its corresponding config file does not exist!")

        # Unload the previous job TODO
        print(f"Unloaded previous job")

        # Initiate the new job
        job_profile = JobProfileConfig(file_path=job_file)
        job_profile.reload()
        self.active_job_config = job_profile
        print("Job profile loaded!")
        # TODO: Initialize the task as well

        # Update the config to use this as our last job
        self.master_profile_config.set_last_job(job_name)

    def register_job_config(self, job_config: JobProfileConfig):
        self.master_profile_config.register_new_job(job_config)
        self.master_profile_config.save()

    ## Task Management ##
    def load_registered_tasks(self):
        """
        Attempt to load all registered tasks for reference throughout the program
        """
        registered_tasks = self.master_profile_config.registered_task_paths
        # If there are no registered tasks, rebuild the registry from scratch
        if registered_tasks is None:
            self.logger.warning(
                f"No registered task entry found in config file! "
                f"Resetting the config to use only example tasks."
            )
            self.reset_task_registry()
            return
        # Otherwise, load each of our registered tasks
        else:
            # Load all task paths
            for p in set(registered_tasks.values()):
                # Load the task
                new_tasks = self.load_tasks_from_file(p)
                # Filter out tasks which were loaded, but not registered
                for k in [x for x in new_tasks if x not in registered_tasks.keys()]:
                    CART_TASK_REGISTRY.pop(k)
                    self.logger.warning(
                        f"Task '{k}' was loaded alongside another task, "
                        f"but has not been registered and was filtered out."
                    )

    def load_tasks_from_file(self, task_path):
        # Confirm the path exists and can be read as a (python) file
        if not task_path.exists():
            raise ValueError(f"File '{task_path}' does not exist; cannot load task!")
        elif not task_path.is_file():
            raise ValueError(f"Path '{task_path}' is not a file; cannot load directories!")
        elif ".py" not in task_path.suffixes:
            self.logger.warning(
                f"Registered task file '{task_path}' was not a Python file; "
                f"will attempt to load it anyways!"
            )

        # Track the list of tasks already registered for later
        prior_tasks = set(CART_TASK_REGISTRY.keys())

        # Add the parent of the path to our Python path
        module_path = str(task_path.parent.resolve())
        sys.path.append(module_path)
        module_name = task_path.name.split('.')[0]

        try:
            # Try to load the module in question
            spec = importlib.util.spec_from_file_location(module_name, task_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            # If something went wrong, roll back our changes to `sys.path`
            sys.path.remove(module_path)
            raise e

        # Get the list of tasks that were registered by the decorator
        new_tasks = set(CART_TASK_REGISTRY.keys()) - prior_tasks

        # If no new tasks were registered, roll back the changes and raise an error
        if len(new_tasks) < 1:
            sys.path.remove(module_path)
            raise ValueError(f"No tasks were registered when importing the file '{task_path}'; "
                             f"Rolling everything back!")
        # Otherwise, keep the module loaded!
        sys.modules[module_name] = module

        # Return the list of (now-loaded) tasks!
        return new_tasks

    def register_new_task(self, task_path: Path):
        # Load the task(s) within the task file
        new_tasks = self.load_tasks_from_file(task_path)

        # Keep track of the task(s) in our configuration file
        for k in new_tasks:
            self.master_profile_config.add_task_path(k, task_path)

        # Save the configuration immediately
        self.master_profile_config.save()
        return new_tasks

    def reset_task_registry(self):
        # Try to load all the example tasks
        examples_path = CART_PATH / "CARTLib/examples"
        example_task_paths = [
            examples_path / "SegmentationReview/SegmentationReviewTask.py",
            examples_path / "GenericClassification/GenericClassificationTask.py",
            examples_path / "RapidMarkup/RapidMarkupTask.py"
        ]

        # Make sure the example tasks all exist before doing anything!
        missing_paths = []
        for p in example_task_paths:
            if not p.exists():
                missing_paths.append(p)

        if len(missing_paths) > 0:
            err_msg = "CART seems to have been corrupted; was missing the following paths!\n"
            err_msg += f"\n  * ".join([str(p) for p in missing_paths])
            raise ValueError(err_msg)

        # Completely reset our task registry and configuration
        self.master_profile_config.clear_task_paths()
        CART_TASK_REGISTRY.clear()

        # Register each example task again, one-by-one
        for p in example_task_paths:
            self.register_new_task(p)

        # Save the config immediately to preserve the changes
        self.master_profile_config.save()

    ## Config Management ##
    def save_master_config(self):
        self.master_profile_config.save()

    def reload_master_config(self):
        # Pull the data from the config file
        self.master_profile_config.reload()
        # If the config version doesn't match the current CART version, warn the user
        if self.master_profile_config.version != CART_VERSION:
            # TODO: Prompt the user directly!
            print("WARNING: Current CART version does not match that of the master profile! "
                  "CART may not work as expected!")
            self.master_profile_config.version = CART_VERSION

    ## GUI Management ##
    def enter(self):
        """
        Called when the CART module is loaded (through our CARTWidget).

        Just signals to the current task that CART is now in view again, and it
        should synchronize its state to the MRML scene. This can include:
          * Installing any shortcuts
          * Restoring any active processes
          * Re-synchronizing with the MRML scene
        """
        if self._task_instance:
            self._task_instance.enter()

    def exit(self):
        """
        Called when the CART module is un-loaded (through our CARTWidget).

        Just signals to the current task that CART is no longer in view, and it
        should pause any active processes in the GUI. This can include:
          * Uninstalling any shortcuts
          * Pausing/killing any active processes
        """
        if self._task_instance:
            self._task_instance.exit()
