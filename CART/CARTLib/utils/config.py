import json
from abc import ABC, abstractmethod, ABCMeta
from pathlib import Path
from typing import Generic, Optional, TypeVar, Union, Callable

import qt

from . import CART_PATH, CART_VERSION

# The location of the default config used by a fresh installation of CART.
#  DO NOT TOUCH IT UNLESS YOU KNOW WHAT YOU'RE DOING.
DEFAULT_FILE = Path(__file__).parent / "default_config.json"
JOB_PROFILE_DIR = CART_PATH / "job_profiles"


## Re-Usable Abstract Elements ##
class DictBackedConfig(ABC):

    CONFIG_KEY = None

    def __init__(
            self,
            parent_config: Optional["DictBackedConfig"] = None,
            config_key_override: Optional[str] = None
    ):
        # Track the parent config
        self.parent_config: "DictBackedConfig" = parent_config

        # If a config label was provided, use it instead of our classmethod
        if config_key_override:
            self.config_label = config_key_override
        else:
            self.config_label = self.default_config_label()

        # Get (or generate) a backing dict
        if self.parent_config:
            # If the parent exists, ensure the backing dict is embedded within it
            self._backing_dict = parent_config.get_or_default(self.config_label, {})
        else:
            # Otherwise, use a standalone dict
            self._backing_dict = {}

        # Whether the contents of this config has been changed since creation
        self._has_changed = False

    @property
    def has_changed(self) -> bool:
        return self._has_changed

    @has_changed.setter
    def has_changed(self, new_state: bool):
        # Update our own state
        self._has_changed = new_state

        # If we've changed, mark every parent as having changed as well
        if new_state and self.parent_config:
            self.parent_config.has_changed = new_state

    @property
    def backing_dict(self) -> dict:
        return self._backing_dict

    @backing_dict.setter
    def backing_dict(self, new_dict: dict):
        """
        The backing dictionary for this Config.

        NOTE: The setter for this attribute does NOT change `has_changed` in any
        way; you should change it to match the context of why you overwrote the
        backing dict directly (i.e. setting it to "False" when you're resetting to
        a previous state).
        """
        # KO: To prevent de-sync with the parent config, replace the contents of
        #  our backing dict with the new dicts contents (instead of replacing
        #  the dictionary itself)
        self._backing_dict.clear()
        for k, v in new_dict.items():
            self._backing_dict[k] = v

    @classmethod
    @abstractmethod
    def default_config_label(cls) -> str:
        """
        Should return a string denoting the type of Config this is.

        Used to create child entries within parent configurations, as
        well as to help with debugging.
        """
        ...

    def get_or_default(self, key: str, default):
        """
        Gets a specific value from backing dict; if it doesn't exist,
        initializes the key in the dict to the default value provided,
        and returns it instead.
        """
        # Try to get the specified value
        val = self._backing_dict.get(key, None)

        # If it didn't exist, set it to our default and make a logged note
        if val is None:
            print(f"No '{key}' entry existed, setting it to {default}.")
            val = default
            self._backing_dict[key] = val
            self.has_changed = True

        return val

    @abstractmethod
    def show_gui(self) -> None:
        """
        Should show a dialogue prompt to the user, allowing them to change
        the configuration values managed by this Config object.
        """
        ...

    def save_without_parent(self) -> None:
        """
        Override if you want the save to go through when this
        Config instance lacks a parent to delegate too
        """
        raise NotImplementedError(
            f"Could not save DictBackedConfig instance of type '{self.__name__}'; "
            f"It does not have an '_save_without_parent' implementation, "
            f"and had no parent instance to delegate too."
        )

    def save(self) -> None:
        """
        Delegate to the parent configuration if possible
        """
        # Only save if our state has changed
        if not self.has_changed:
            return

        # If we have a parent config, have it save instead
        if self.parent_config:
            self.parent_config.save()
        else:
            self.save_without_parent()

        # Mark ourselves as no longer having changes from the file
        self.has_changed = False


# I love Metaclass conflicts! Wooo!
class _ABCQDialog(type(qt.QDialog), ABCMeta):
    ...


# Generic type for DictBackedConfig subclasses
DICT_CONFIG_TYPE = TypeVar("DICT_CONFIG_TYPE", bound=DictBackedConfig)


class ConfigDialog(qt.QDialog, ABC, Generic[DICT_CONFIG_TYPE], metaclass=_ABCQDialog):
    """
    QT Dialog built to be paired with a DictBackConfig.

    Provides some shared utilities to streamline the creation of a
    Config GUI, including:
      * Resetting the bound Config when the user backs out
      * Allow the user to reset the Config state explicitly
      * Asking the user if they want to save if they close the GUI
       after making changes
    """
    def __init__(self, bound_config: DICT_CONFIG_TYPE):
        # Initialize the QT Dialogue first
        super().__init__()

        # Track the bound config so we can modify it later
        self.bound_config: DICT_CONFIG_TYPE = bound_config

        # Track a copy of that config's backing dict as a backup
        self._restore_dict = bound_config.backing_dict.copy()

        # The layout which the user should place their widgets within
        layout = qt.QFormLayout()
        self.setLayout(layout)

        # Track a list of "sync" functions; each is called
        # iteratively when a synchronization is done
        self._sync_func_list: dict[qt.QWidget, list[Callable[[], None]]] = dict()

        # Build the GUI
        self.buildGUI(layout)

        # Add a suite of buttons w/ standardized functionality
        self._addButtons(layout)

        # Sync the GUI to match the config
        self.sync()

    ## GUI Elements ##
    @abstractmethod
    def buildGUI(self, layout: qt.QFormLayout):
        """
        Add any QT widgets to the GUI here; ensures that they are placed
        appropriately within the dialogue (namely, above the button panel)
        """
        ...

    def _addButtons(self, layout: qt.QFormLayout):
        # The button box itself
        buttonBox = qt.QDialogButtonBox()
        buttonBox.setStandardButtons(
            qt.QDialogButtonBox.Reset | qt.QDialogButtonBox.Cancel | qt.QDialogButtonBox.Ok
        )

        # Function to map the button press to our functionality
        def onButtonPressed(button: qt.QPushButton):
            # Get the role of the button
            button_role = buttonBox.buttonRole(button)
            # Match it to our corresponding function
            # TODO: Replace this with a `match` statement when porting to Slicer 5.9
            if button_role == qt.QDialogButtonBox.AcceptRole:
                self.onConfirm()
            elif button_role == qt.QDialogButtonBox.RejectRole:
                self.onCancel()
            elif button_role == qt.QDialogButtonBox.ResetRole:
                self.onReset()
            else:
                raise ValueError("Pressed a button with an invalid role somehow...")

        buttonBox.clicked.connect(onButtonPressed)

        layout.addRow(buttonBox)

    ## Config Synchronization ##
    def register_sync_function(self, widget: qt.QWidget, func: Callable[[], None]):
        """
        Register a synchronization function to be associated with a given widget
        """
        func_list = self._sync_func_list.get(widget, [])
        func_list.append(func)
        self._sync_func_list[widget] = func_list

    def sync(self):
        """
        Runs each registered sync function in turn, synchronizing their state with the
        GUI (however the registered function chose to do so) while blocking signals
        from the associated widget in the process (to prevent redundant config update
        calls).
        """
        for widget, func_list in self._sync_func_list.items():
            widget.blockSignals(True)
            for f in func_list: f()
            widget.blockSignals(False)

    ## User Interactions ##
    def onConfirm(self):
        """
        Called when the user confirms the changes they made (if any).
        """
        self.bound_config.save()
        self.accept()

    def onCancel(self):
        """
        Called when the user tries to cancel out of the prompt w/o saving.
        """
        # If the user hasn't made any changes, just close
        if not self.bound_config.has_changed:
            self.accept()
            return

        # Prompt the user if they made changes they may want to save
        reply = qt.QMessageBox.question(
            self,
            "Unsaved Changes",
            "You have not saved your changes; would you like to now?",
            qt.QMessageBox.Yes, qt.QMessageBox.No
        )

        # Save to file only if the user confirms it
        if reply == qt.QMessageBox.Yes:
            self.bound_config.save()
            self.accept()
        else:
            self.bound_config.backing_dict = self._restore_dict
            self.bound_config.has_changed = False
            self.reject()

    def onReset(self):
        """
        Called when the user explicitly requests the config be reset
        """
        self.bound_config.backing_dict = self._restore_dict
        self.sync()
        self.bound_config.has_changed = False

    ## QT Events ##
    def closeEvent(self, event):
        """
        Intercepts when the user closes the window by clicking the 'x' in the
        dialog; ensures any modifications don't get discarded by mistake.
        """
        self.onCancel()
        event.accept()


## Backing Config Managers ##
class MasterProfileConfig(DictBackedConfig):
    ## Attributes ##
    AUTHOR_KEY = "author"

    @property
    def author(self) -> Optional[str]:
        return self.backing_dict.get(self.AUTHOR_KEY, None)

    @author.setter
    def author(self, new_author: str):
        self.backing_dict[self.AUTHOR_KEY] = new_author
        self.has_changed = True

    POSITION_KEY = "position"

    @property
    def position(self) -> Optional[str]:
        return self.backing_dict.get(self.POSITION_KEY, None)

    @position.setter
    def position(self, new_position):
        self.backing_dict[self.POSITION_KEY] = new_position
        self.has_changed = True

    @position.setter
    def position(self, new_position):
        self.backing_dict[self.POSITION_KEY] = new_position
        self.has_changed = True

    REGISTERED_JOB_KEY = "registered_jobs"

    @property
    def registered_jobs(self) -> dict[str, str]:
        """
        Map of registered jobs, in "name: path" format.
        """
        job_map = self.get_or_default(self.REGISTERED_JOB_KEY, {})
        return job_map

    def register_new_job(self, job_config: "JobProfileConfig"):
        # Register the new job
        k = job_config.name
        p = str(job_config.file.resolve())
        job_map = self.get_or_default(self.REGISTERED_JOB_KEY, {})
        job_map[k] = p
        # Mark ourselves as being changed
        self.has_changed = True

    @property
    def last_job(self) -> Optional[tuple[str, Path]]:
        """
        Returns the name and path to the job last used, as detailed within this config.
        """
        job_registry = self.registered_jobs
        if len(self.registered_jobs) < 1:
            return None
        first_key = next(iter(job_registry.keys()))
        return first_key, job_registry[first_key]

    def set_last_job(self, job_name: str):
        old_job_registry = self.get_or_default(self.REGISTERED_JOB_KEY, {})
        job_path = old_job_registry.get(job_name, None)
        if job_path is None:
            raise ValueError(
                f"Job '{job_name}' has not been registered! Cannot make it the last-used job."
            )
        # Re-build our job map using the new setup
        new_registry = {job_name: job_path}
        for k, v in old_job_registry.items():
            # Skip adding the job again; it's already inserted
            if k == job_name:
                continue
            new_registry[k] = v
        self.backing_dict[self.REGISTERED_JOB_KEY] = new_registry
        self.has_changed = True

    VERSION_KEY = "version"

    @property
    def version(self):
        return self.get_or_default(self.VERSION_KEY, CART_VERSION)

    @version.setter
    def version(self, new_version: str):
        """
        WARNING: You really shouldn't change this yourself. The version
        used
        """
        self.backing_dict[self.VERSION_KEY] = new_version

    REGISTERED_TASK_PATHS_KEY = "registered_task"

    @property
    def registered_task_paths(self) -> Optional[dict[str, Path]]:
        registered_task_vals: dict[str, str]  = self.backing_dict.get(self.REGISTERED_TASK_PATHS_KEY)
        if registered_task_vals is None:
            return None
        return_dict = {}
        for k, v in registered_task_vals.items():
            p = Path(v)
            if not p.is_file():
                print(f"WARNING: Task file '{v}' does not exist!")
                return_dict[k] = None
            else:
                return_dict[k] = p
        return return_dict

    def add_task_path(self, task_name: str, task_path: Path):
        registered_task_vals = self.get_or_default(self.REGISTERED_TASK_PATHS_KEY, {})
        registered_task_vals[task_name] = str(task_path.resolve())
        self.has_changed = True

    def clear_task_paths(self):
        # Clear the task paths entirely!
        self.backing_dict[self.REGISTERED_TASK_PATHS_KEY] = {}
        self.has_changed = True

    ## Utilities ##
    def save_without_parent(self) -> None:
        """
        Save the in-memory contents of the configuration back to our JSON file
        """
        with open(GLOBAL_CONFIG_PATH, "w") as fp:
            json.dump(self.backing_dict, fp, indent=2)

    def reload(self):
        if not GLOBAL_CONFIG_PATH.exists():
            print(f"Could not load master config; configuration file does not exist!")
            return
        with open(GLOBAL_CONFIG_PATH, "r") as fp:
            self.backing_dict = json.load(fp)

    def show_gui(self) -> qt.QDialog:
        # TODO
        pass

    @classmethod
    def default_config_label(cls) -> str:
        return "cart_master_profile"


class JobProfileConfig(DictBackedConfig):
    NAME_KEY = "name"

    def __init__(
            self,
            parent_config: Optional["DictBackedConfig"] = None,
            config_key_override: Optional[str] = None,
            file_path: Optional[Path] = None
    ):
        super().__init__(parent_config, config_key_override)

        self._file_path = file_path

    @property
    def name(self) -> Optional[str]:
        return self.backing_dict.get(self.NAME_KEY, None)

    @name.setter
    def name(self, new_name: str):
        self.backing_dict[self.NAME_KEY] = new_name
        self.has_changed = True

    DATA_PATH_KEY = "data_path"

    @property
    def data_path(self) -> Optional[Path]:
        path_str = self.backing_dict.get(self.DATA_PATH_KEY, None)
        if path_str is None:
            return None
        return Path(path_str)

    @data_path.setter
    def data_path(self, new_path: Path):
        path_str = str(new_path)
        self.backing_dict[self.DATA_PATH_KEY] = path_str
        self.has_changed = True

    OUTPUT_PATH_KEY = "output_path"

    @property
    def output_path(self) -> Optional[Path]:
        path_str = self.backing_dict.get(self.OUTPUT_PATH_KEY, None)
        if path_str is None:
            return None
        return Path(path_str)

    @output_path.setter
    def output_path(self, new_path: Path):
        path_str = str(new_path)
        self.backing_dict[self.OUTPUT_PATH_KEY] = path_str
        self.has_changed = True

    COHORT_FILE_KEY = "cohort_file"

    @property
    def cohort_path(self) -> Optional[Path]:
        path_str = self.backing_dict.get(self.COHORT_FILE_KEY, None)
        if path_str is None:
            return None
        return Path(path_str)

    @cohort_path.setter
    def cohort_path(self, new_path: Path):
        path_str = str(new_path)
        self.backing_dict[self.COHORT_FILE_KEY] = path_str
        self.has_changed = True

    TASK_KEY = "task"

    @property
    def task(self) -> str:
        return self.get_or_default(self.TASK_KEY, None)

    @task.setter
    def task(self, new_task: str):
        self._backing_dict[self.TASK_KEY] = new_task
        self.has_changed = True

    ## Abstract Methods ##
    @classmethod
    def default_config_label(cls) -> str:
        return "job_profile"

    def show_gui(self) -> None:
        pass

    ## File I/O ##
    @property
    def file(self) -> Path:
        if self._file_path:
            return self._file_path
        else:
            # Format the job name to create our corresponding filename
            default_filename = self.name.replace(" ", "_") + ".json"
            new_file = JOB_PROFILE_DIR / default_filename
            self._file_path = new_file
            return new_file

    def reload(self):
        """
        (Re-)loads config's contents into memory.
        """
        # If there's no config file yet, there's nothing to load
        if not self.file.exists():
            print("Nothing to load!")
            return
        # Otherwise,
        with open(self.file, 'r') as fp:
            new_data = json.load(fp)
            self.backing_dict = new_data

    def save_without_parent(self) -> None:
        # Save this config to file.
        self.file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.file, 'w') as fp:
            json.dump(self.backing_dict, fp, indent=2)


class ProfileConfig(DictBackedConfig):
    """
    Configuration manager for a CART profile.

    Tracks the profile's settings, allowing for profiles of
    settings to be swapped on the fly.
    """
    DEFAULT_ROLE = "N/A"

    def __init__(self, label: str, backing_dict: dict, parent_config: "CARTConfig"):
        # Init w/o a parent config initially
        super().__init__()

        # Explicitly set our inherited attributes instead;
        # needed as Users are not handled like regular Config entries
        self._backing_dict = backing_dict
        self.parent_config: "CARTConfig" = parent_config

        # As each profile gets its own config entry, each with a unique label
        self.config_label = label

    @classmethod
    def default_config_label(cls) -> str:
        # Profiles are stored in a profile dict, and use their own label
        # within said dict instead of a shared label.
        pass

    @property
    def label(self):
        return self.config_label

    ## Last Used Settings ##
    LAST_USED_COHORT_KEY = "last_used_cohort_file"

    @property
    def last_used_cohort_file(self) -> Union[Path, None]:
        val = self._backing_dict.get(self.LAST_USED_COHORT_KEY, None)
        if val is None:
            return None
        # noinspection PyUnreachableCode
        return Path(val)

    @last_used_cohort_file.setter
    def last_used_cohort_file(self, new_path: Path):
        self._backing_dict[self.LAST_USED_COHORT_KEY] = str(new_path)
        self.has_changed = True

    LAST_USED_DATA_KEY = "last_used_data_path"

    @property
    def last_used_data_path(self) -> Union[Path, None]:
        val = self._backing_dict.get(self.LAST_USED_DATA_KEY, None)
        if val is None:
            return None
        # noinspection PyUnreachableCode
        return Path(val)

    @last_used_data_path.setter
    def last_used_data_path(self, new_path: Path):
        self._backing_dict[self.LAST_USED_DATA_KEY] = str(new_path)
        self.has_changed = True

    LAST_USED_TASK_KEY = "last_used_task"

    @property
    def last_used_task(self) -> str:
        val = self._backing_dict.get(self.LAST_USED_TASK_KEY, "")
        return val

    @last_used_task.setter
    def last_used_task(self, new_task: str):
        self._backing_dict[self.LAST_USED_TASK_KEY] = new_task
        self.has_changed = True

    ## Profile Role ##
    ROLE_KEY = "role"

    @property
    def role(self) -> str:
        return self.get_or_default(self.ROLE_KEY, self.DEFAULT_ROLE)

    @role.setter
    def role(self, new_role: str):
        self._backing_dict[self.ROLE_KEY] = new_role
        self.has_changed = True

    @property
    def valid_roles(self) -> list[str]:
        return self.parent_config.profile_roles

    ## Autosaving Management ##
    SAVE_ON_ITER_KEY = "save_on_iter"

    @property
    def save_on_iter(self) -> bool:
        return self.get_or_default(self.SAVE_ON_ITER_KEY, True)

    @save_on_iter.setter
    def save_on_iter(self, new_val: bool):
        # Validate that the value is a boolean, to avoid weird jank later
        assert isinstance(new_val, bool), f"'{self.SAVE_ON_ITER_KEY}' must be a boolean value."
        self._backing_dict[self.SAVE_ON_ITER_KEY] = new_val
        self.has_changed = True

    ## Retain Layout Between Cases ##
    RETAIN_LAYOUT_KEY = "retain_layout"

    @property
    def retain_layout(self) -> bool:
        return self.get_or_default(self.RETAIN_LAYOUT_KEY, True)

    @retain_layout.setter
    def retain_layout(self, new_val: bool):
        self._backing_dict[self.RETAIN_LAYOUT_KEY] = new_val
        self.has_changed = True

    ## Sub-Configurations ##
    SUB_CONFIGS_KEY = "sub_config"

    @property
    def sub_configs(self) -> dict:
        return self.get_or_default(self.SUB_CONFIGS_KEY, {})

    def get_sub_config(self, key: str):
        sub_entry = self.sub_configs.get(key, False)
        if not sub_entry:
            new_entry = {}
            self.sub_configs[key] = new_entry
            return new_entry
        else:
            return sub_entry

    ## Utils ##
    def show_gui(self):
        # Build the Config prompt
        prompt = ProfileConfigDialog(bound_config=self)
        # Show it, blocking other interactions until its resolved
        prompt.exec()

    def save(self):
        # If the selected role is new, add it to the config first
        if self.role not in self.parent_config.profile_roles:
            self.parent_config.profile_roles.append(self.role)

        super().save()


class CARTConfig(DictBackedConfig):
    """
    Global configuration for CART itself.

    Manages profiles, as well as tracking some simple metrics
    itself to allow for restoring the previous profile
    """
    DEFAULT_LABEL = "Default"
    CONFIG_KEY = "CART"

    def __init__(self, config_path: Path):
        # Initialize the dict-backed config attributes
        super().__init__()

        # Path to the file the config should be saved to
        self.config_path = config_path

    @classmethod
    def default_config_label(cls) -> str:
        return cls.CONFIG_KEY

    ## Profile Management ##
    PROFILE_KEY = "user_profiles"
    DEFAULT_ROLES = [ProfileConfig.DEFAULT_ROLE]

    @property
    def profiles(self) -> dict[str, dict]:
        return self.get_or_default(self.PROFILE_KEY, {})

    def new_profile(
            self,
            label: str,
            new_settings: dict = None,
            reference_profile: ProfileConfig = None
    ) -> ProfileConfig:
        """
        Create a new profile, copying config entries from a
        reference profile if provided.

        :param label: The label for this new profile
        :param new_settings: Settings specified by the user that should be
            applied to this new profile
        :param reference_profile: Reference profile; any settings not specified
            in `new_settings` above will be copied from here.
        """
        # Confirm that the provided profile label is available and valid
        stripped_name = label.strip()
        if not stripped_name:
            raise ValueError("Cannot create a profile without a label!")

        if stripped_name in GLOBAL_CONFIG.profiles.keys():
            raise ValueError(f"Profile with label '{stripped_name}' already exists!")

        # If a reference profile was provided, use its settings as our base
        if reference_profile:
            new_profile = reference_profile.backing_dict.copy()
        # Otherwise, start with a blank slate
        else:
            new_profile = {}

        # We can have a set of settings to override as well, if provided
        if new_settings:
            for k, v in new_settings.items():
                new_profile[k] = v

        # Assign it into our profile dictionary
        self.profiles[label] = new_profile

        # Return the result, wrapped in our ProfileConfig
        return ProfileConfig(label, new_profile, self)

    def get_profile_config(self, label: str) -> Optional[ProfileConfig]:
        profile_dict = self.profiles.get(label, None)
        if profile_dict is not None:
            return ProfileConfig(label, profile_dict, self)
        else:
            return None

    def promptNewProfile(self, reference_profile: ProfileConfig = None) -> Optional[str]:
        """
        Generate a QT prompt for the user to create a new profile entry.

        :param reference_profile: The profile to copy configuration settings from (if any)

        :return: The label of the new profile; None if the user backed out.
        """
        # Try to generate a new profile from the provided reference
        prompt = NewProfileDialog(reference_profile, GLOBAL_CONFIG)
        profile_added_successfully = prompt.exec()

        # If successful, return the profile label for easy reference
        if profile_added_successfully:
            # Mark oneself as having changed
            self.has_changed = True
            # Return the new profile label for reference elsewhere
            return prompt.profile
        # Otherwise, return nothing
        else:
            return None

    LAST_PROFILE_KEY = "last_profile"

    @property
    def last_profile(self):
        return self.get_or_default(
            self.LAST_PROFILE_KEY, self.DEFAULT_LABEL
        )

    @last_profile.setter
    def last_profile(self, new_label: str):
        self._backing_dict[self.LAST_PROFILE_KEY] = new_label
        self.has_changed = True

    PROFILE_ROLES_KEY = "profile_roles"

    @property
    def profile_roles(self) -> list[str]:
        return self.get_or_default(self.PROFILE_ROLES_KEY, self.DEFAULT_ROLES)

    def new_profile_role(self, new_role: str):
        if new_role in self.profile_roles:
            raise ValueError(f"Role '{new_role}' already exists!")

        self.profile_roles.append(new_role)
        self.has_changed = True

    def show_gui(self):
        raise NotImplementedError("You should configure CART on a per-profile basis!")

    ## I/O ##
    def load_from_json(self):
        """
        (Re-)Load the configuration from the file.

        Does NOT check whether the user has unsaved changes; that should be
        handled by whatever is requesting the configuration be loaded!
        """
        # If our specified configuration file doesn't exist, copy the default to make one
        if GLOBAL_CONFIG_PATH.exists():
            with open(self.config_path) as cf:
                self._backing_dict = json.load(cf)
        else:
            # If there isn't a file, just create a blank
            self._backing_dict = dict()

    def save_without_parent(self):
        """
        Save the in-memory contents of the configuration back to our JSON file
        """
        with open(GLOBAL_CONFIG_PATH, "w") as cf:
            json.dump(self._backing_dict, cf, indent=2)


## GUI elements ##
class NewProfileDialog(qt.QDialog):
    def __init__(self, reference_profile: "ProfileConfig", master_config: "CARTConfig"):
        # Initialize the QDialog base itself
        super().__init__()

        # A reference config to copy from if the user requests it
        self.reference_profile = reference_profile

        # The master config we want to save the profile too
        self.master_config = master_config

        # The text field widget for the profile label
        self.profileLabelEdit: qt.QLineEdit = None

        # Selection field for the role
        self.roleComboBox: qt.QComboBox = None

        # Toggle box which make the profile a blank slate if checked
        # (instead of copying the active profile's state, the default)
        self.blankSlateBox: qt.QCheckBox = None

        # Track the button box so we can react to them being pressed
        self.buttonBox: qt.QDialogButtonBox = None

        # Built the GUI contents
        self.buildUI()

    ## GUI components ##
    def addButtons(self):
        buttonBox = qt.QDialogButtonBox()
        buttonBox.setStandardButtons(
            qt.QDialogButtonBox.Cancel | qt.QDialogButtonBox.Ok
        )
        buttonBox.clicked.connect(self.onButtonPressed)
        return buttonBox

    def buildUI(self):
        # General window properties
        self.setWindowTitle("New Profile")

        # Create a form layout to hold everything in
        layout = qt.QFormLayout()
        self.setLayout(layout)

        # Add a field for submitting the profile label
        profileLabelEdit = qt.QLineEdit()
        profileLabelLabel = qt.QLabel("Label:")
        profileLabelLabel.setToolTip(
            "An ID label for this profile. Cannot match an existing profile label!"
        )
        self.profileLabelEdit = profileLabelEdit

        # Add them to our layout
        layout.addRow(profileLabelLabel, profileLabelEdit)

        # Add a combobox that lets the user select the profile's role
        roleComboBox = qt.QComboBox()
        roleLabel = qt.QLabel("Role:")
        roleLabel.setToolTip("What role the profile should be marked as having.")

        # Add the roles already available to the combobox
        roleComboBox.addItems(self.master_config.profile_roles)

        # Make the combo-box editable
        roleComboBox.setEditable(True)

        self.roleComboBox = roleComboBox

        # Add it to our GUI layout
        layout.addRow(roleLabel, roleComboBox)

        # Add the blank-state checkbox
        blankStateBox = qt.QCheckBox()
        blankStateLabel = qt.QLabel("Reset to Default?")
        blankStateLabel.setToolTip("""
            If selected, the new profile will have no configuration settings, 
            being a "blank slate". If unchecked, the configuration settings of the 
            current profile (including the last-used settings) are copied over instead.
        """)
        self.blankSlateBox = blankStateBox
        layout.addRow(blankStateLabel, blankStateBox)

        # Add our button array to the bottom of the GUI
        self.buttonBox = self.addButtons()
        layout.addRow(self.buttonBox)

        # Only enable the "confirm" button when a valid username is present
        okButton = self.buttonBox.button(qt.QDialogButtonBox.Ok)
        def syncOkButtonState(profile_label: str):
            stripped_name = profile_label.strip()
            if not stripped_name:
                okButton.setEnabled(False)
                okButton.setToolTip("Profiles must have a non-blank label")
            elif stripped_name in self.master_config.profiles.keys():
                okButton.setEnabled(False)
                okButton.setToolTip("The provided profile already exists!")
            else:
                okButton.setEnabled(True)
                okButton.setToolTip("")
        self.profileLabelEdit.textChanged.connect(syncOkButtonState)
        # Sync the OK button's state immediately
        syncOkButtonState(profileLabelEdit.text)

    def onButtonPressed(self, button: qt.QPushButton):
        # Get the role of the button
        button_role = self.buttonBox.buttonRole(button)
        # Match it to our corresponding function
        # TODO: Replace this with a `match` statement when porting to Slicer 5.9
        if button_role == qt.QDialogButtonBox.AcceptRole:
            self.createNewProfile()
            self.accept()
        elif button_role == qt.QDialogButtonBox.RejectRole:
            self.reject()
        else:
            raise ValueError("Pressed a button with an invalid role somehow...")

    ## Access Management ##s
    @property
    def profile(self) -> str:
        return self.profileLabelEdit.text

    @property
    def selected_role(self) -> str:
        return self.roleComboBox.currentText.strip()

    @property
    def shouldBlankState(self) -> bool:
        return self.blankSlateBox.isChecked()

    ## Utils
    def createNewProfile(self):
        # Build the profile config dict from our GUI
        profile_dict = {
            ProfileConfig.ROLE_KEY: self.selected_role
        }

        # Add a new entry into the config file
        if self.shouldBlankState:
            self.master_config.new_profile(
                self.profile,
                profile_dict
            )
        else:
            self.master_config.new_profile(
                self.profile,
                profile_dict,
                self.reference_profile
            )

        # If the role is new, add it to the master config list
        if self.selected_role not in self.master_config.profile_roles:
            self.master_config.profile_roles.append(self.selected_role)


class ProfileConfigDialog(ConfigDialog[ProfileConfig]):
    """
    Configuration dialog which allows the user to configure a
    profile's CART settings.
    """

    def buildGUI(self, layout: qt.QFormLayout):
        # General window properties
        self.setWindowTitle("CART Configuration")

        # Build the widget for the user's role
        self._roleWidget(layout)

        # Build the widget for the Iterative Save attribute
        self._iterSaveWidget(layout)

        # Build the widget for whether user layout preservation
        self._layoutSettingsWidget(layout)

    def _roleWidget(self, layout: qt.QFormLayout):
        # Add a combobox that lets the user select a profile's role
        roleComboBox = qt.QComboBox()
        roleLabel = qt.QLabel("Role:")
        roleLabel.setToolTip("What role the profile should be marked as having.")

        # Make the combo-box editable
        roleComboBox.setEditable(True)

        # When a new role is selected, update our backing dict
        def changeRole(new_role: str):
            self.bound_config.role = new_role
        roleComboBox.currentTextChanged.connect(changeRole)

        # Register the corresponding sync function
        def syncRole():
            roleComboBox.clear()
            roleComboBox.addItems(self.bound_config.valid_roles)
            roleComboBox.currentText = self.bound_config.role
        self.register_sync_function(roleComboBox, syncRole)

        # Add it to our layout
        layout.addRow(roleLabel, roleComboBox)

    def _iterSaveWidget(self, layout: qt.QFormLayout):
        # Add a checkbox for the state of autosaving
        iterSaveCheck = qt.QCheckBox()
        iterSaveLabel = qt.QLabel("Save on Iteration:")
        iterSaveLabel.setToolTip(
            "If checked, the Task will try to save when you change cases automatically."
        )

        # Update the config's state when it changes
        def setSaveOnIter(new_state: bool):
            self.bound_config.save_on_iter = bool(new_state)
        iterSaveCheck.stateChanged.connect(setSaveOnIter)

        # Register a synchronization function
        def syncSaveOnIter():
            # Iterative save checkbox
            iterSaveCheck.setChecked(self.bound_config.save_on_iter)
        self.register_sync_function(iterSaveCheck, syncSaveOnIter)

        # Add it to our layout
        layout.addRow(iterSaveLabel, iterSaveCheck)

    def _layoutSettingsWidget(self, layout: qt.QFormLayout):
        # Add a checkbox for the state of autosaving
        layoutPreserveCheck = qt.QCheckBox()
        layoutPreserveLabel = qt.QLabel("Retain Layout Across Cases:")
        layoutPreserveLabel.setToolTip(
            "If checked, the layout settings (shown orientations and presentation style) "
            "will be retained when the current case is changed. Otherwise, the settings "
            "are reset to default when the case changes."
        )

        # Update the config's state when it changes
        def setRetainLayout(new_state: bool):
            self.bound_config.retain_layout = bool(new_state)
        layoutPreserveCheck.stateChanged.connect(setRetainLayout)

        # Register a synchronization function
        def syncRetainLayout():
            layoutPreserveCheck.setChecked(self.bound_config.retain_layout)
        self.register_sync_function(layoutPreserveCheck, syncRetainLayout)

        # Add it to our layout
        layout.addRow(layoutPreserveLabel, layoutPreserveCheck)

# The location of the config file for this installation of CART.
GLOBAL_CONFIG_PATH = CART_PATH / "configuration.json"

GLOBAL_CONFIG = CARTConfig(GLOBAL_CONFIG_PATH)
