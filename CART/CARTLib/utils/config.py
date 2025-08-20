import json
from pathlib import Path

import qt

# The location of the default config used by a fresh installation of CART.
#  DO NOT TOUCH IT UNLESS YOU KNOW WHAT YOU'RE DOING.
DEFAULT_FILE = Path(__file__).parent / "default_config.json"


class ConfigGUI(qt.QDialog):
    """
    Configuration dialog which allows the user to configure CART.
    """

    def __init__(self, bound_config: "Config"):
        # Initialize the QDialog base itself
        super().__init__()

        # Track the bound configuration to ourselves
        self.bound_config = bound_config

        # Built the GUI contents
        self.build_ui()

    def build_ui(self):
        # General window properties
        self.setWindowTitle("CART Configuration")

        # Create a form layout to hold everything in
        layout = qt.QFormLayout()
        self.setLayout(layout)

        # Add a checkbox for the state of autosaving
        iterSaveCheck = qt.QCheckBox()
        iterSaveLabel = qt.QLabel("Save on Iteration:")
        iterSaveLabel.setToolTip(
            "If checked, the Task will try to save when you change cases automatically."
        )

        # Ensure it is synchronized with the configuration settings
        iterSaveCheck.setChecked(self.bound_config.autosave)
        def setAutosave(new_state: bool):
            self.bound_config.autosave = bool(new_state)
        iterSaveCheck.stateChanged.connect(
            lambda x: setAutosave(x)
        )
        layout.addRow(iterSaveLabel, iterSaveCheck)

        buttonBox = self.addButtons()
        layout.addRow(buttonBox)

    def addButtons(self):
        buttonBox = qt.QDialogButtonBox()
        buttonBox.setStandardButtons(
            qt.QDialogButtonBox.Reset | qt.QDialogButtonBox.Cancel | qt.QDialogButtonBox.Ok
        )
        buttonBox.clicked.connect(
            lambda b: print(buttonBox.buttonRole(b))
        )
        return buttonBox


class Config:
    """
    Configuration manager for CART.
    """

    def __init__(self, config_path: Path):
        # Attributes
        self.config_path = config_path

        # Hidden attributes
        self._backing_dict = {}
        self._has_changed = False

    ## I/O ##
    def load(self):
        """
        (Re-)Load the configuration from the file.

        Does NOT check whether the user has unsaved changes; that should be
        handled by the logic requesting the configuration be loaded!
        """
        # If our specified configuration file doesn't exist, copy the default to make one
        if not MAIN_CONFIG.exists():
            print("No configuration file found, creating a new one!")
            with open(DEFAULT_FILE) as cf:
                # Load the data
                self._backing_dict = json.load(cf)
                # And immediately save it, creating a copy
                self.save()
        # Otherwise, load the configuration as-is
        else:
            with open(self.config_path) as cf:
                self._backing_dict = json.load(cf)

        # Mark that there are no longer any changes between the config and file
        self._has_changed = False

    def save(self):
        """
        Save the in-memory contents of the configuration back to our JSON file
        """
        with open(MAIN_CONFIG, "w") as cf:
            json.dump(self._backing_dict, cf, indent=2)

        # Mark that there are no longer any changes between the config and file
        self._has_changed = False

    ## User Management ##
    @property
    def users(self) -> list[str]:
        return self._get_or_default("users", [])

    def add_user(self, new_user: str):
        # Strip leading and trailing whitespace in the username
        new_user = new_user.strip()

        # TODO: Make these checks raise an error which can be capture

        # Confirm they actually provided a (non-whitespace only) string
        if not new_user:
            print("Something must be entered as a name!")
            return False

        # Check if the user already exists
        if new_user in self.users:
            print("User name already exists!")
            return False

        # Add the username to our list, in the first position (most recent)
        self.users.insert(0, new_user)

        # Save the configuration automatically, as it's a "core" attribute
        self.save()
        return True

    ## Last Used Settings ##
    @property
    def last_used_cohort_file(self) -> Path:
        key = "last_used_cohort_file"
        val = Path(self._backing_dict.get(key, ""))
        return val

    @last_used_cohort_file.setter
    def last_used_cohort_file(self, new_path: Path):
        self._backing_dict["last_used_cohort_file"] = str(new_path)
        self._has_changed = True

    @property
    def last_used_data_path(self) -> Path:
        key = "last_used_data_path"
        val = Path(self._backing_dict.get(key, ""))
        return val

    @last_used_data_path.setter
    def last_used_data_path(self, new_path: Path):
        self._backing_dict["last_used_data_path"] = str(new_path)
        self._has_changed = True

    @property
    def last_used_task(self) -> str:
        key = "last_used_task"
        val = self._backing_dict.get(key, "")
        return val

    @last_used_task.setter
    def last_used_task(self, new_task: str):
        self._backing_dict["last_used_task"] = new_task

    ## Autosaving Management ##
    @property
    def autosave(self) -> bool:
        return self._get_or_default("autosave", True)

    @autosave.setter
    def autosave(self, new_val: bool):
        # Validate that the value is a boolean, to avoid weird jank later
        assert isinstance(new_val, bool), "Autosave must be a boolean value."
        self._backing_dict["autosave"] = new_val
        self._has_changed = True

    ## Utils ##
    def _get_or_default(self, key, default):
        # Try to get the specified value
        val = self._backing_dict.get(key, None)

        # If it didn't exist, set it to our default and make a logged note
        if val is None:
            print(f"No '{key}' entry existed, setting it to {default}.")
            val = default
            self._backing_dict[key] = val
            self._has_changed = True

        return val

    def show_gui(self):
        # Build the Config prompt
        prompt = ConfigGUI(bound_config=self)
        # Show it, blocking other interactions until its resolved
        prompt.exec()


# The location of the config file for this installation of CART.
MAIN_CONFIG = Path(__file__).parent.parent.parent / "configuration.json"

config = Config(MAIN_CONFIG)
