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

    def __init__(self, bound_config: "UserConfig"):
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
        iterSaveCheck.setChecked(self.bound_config.save_on_iter)
        def setSaveOnIter(new_state: bool):
            self.bound_config.save_on_iter = bool(new_state)
        iterSaveCheck.stateChanged.connect(
            lambda x: setSaveOnIter(x)
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


class UserConfig:
    """
    Configuration manager for a CART user profile.

    Tracks the user's settings, allowing for them to be
    swapped on the fly.
    """

    def __init__(self, config_dict: dict, cart_config: "CARTConfig"):
        # Cross-reference attributes
        self._backing_dict = config_dict
        self._cart_config = cart_config

        # Track whether something has changed, so other processes can reference it
        self._has_changed = False

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
    SAVE_ON_ITER_KEY = "save_on_iter"

    @property
    def save_on_iter(self) -> bool:
        return self._get_or_default(self.SAVE_ON_ITER_KEY, True)

    @save_on_iter.setter
    def save_on_iter(self, new_val: bool):
        # Validate that the value is a boolean, to avoid weird jank later
        assert isinstance(new_val, bool), f"'{self.SAVE_ON_ITER_KEY}' must be a boolean value."
        self._backing_dict[self.SAVE_ON_ITER_KEY] = new_val
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
        
    def save_to_file(self):
        # Only do the (relatively) expensive I/O when we have changes
        if self._has_changed:
            self._cart_config.save()

class CARTConfig:
    """
    Global configuration for CART itself.

    Manages user profiles, as well as tracking some simple metrics
    itself to allow for restoring the previous user
    """

    DEFAULT_USERNAME = "Default"

    def __init__(self, config_path: Path):
        # Path to the file the config should be saved to
        self.config_path = config_path

        # The dictionary containing the configuration's contents
        self._backing_dict: dict = None

    ## User Management ##
    PROFILE_KEY = "user_profiles"

    @property
    def profiles(self) -> dict[str, dict]:
        return self._get_or_default(self.PROFILE_KEY, {})

    def new_user(self, username: str):
        # Strip leading and trailing whitespace in the username
        username = username.strip()

        # Confirm they actually provided a (non-whitespace only) string
        if not username:
            raise ValueError("The username cannot be blank!")

        # Check if the user already exists
        if username in self.profiles.keys():
            raise ValueError(f"The username '{username}' already exists!")

        # Create a new user profile for this user
        self.profiles[username] = {}

        # Save the configuration automatically, as it's a "core" attribute
        self.save()

    def get_user_config(self, username: str):
        user_dict = self.profiles.get(username, {})
        if user_dict:
            return UserConfig(user_dict, self)
        else:
            return None

    LAST_USER_KEY = "last_user"

    @property
    def last_user(self):
        return self._get_or_default(
            self.LAST_USER_KEY, self.DEFAULT_USERNAME
        )

    ## I/O ##
    def load(self):
        """
        (Re-)Load the configuration from the file.

        Does NOT check whether the user has unsaved changes; that should be
        handled by whatever is requesting the configuration be loaded!
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

    def save(self):
        """
        Save the in-memory contents of the configuration back to our JSON file
        """
        with open(MAIN_CONFIG, "w") as cf:
            json.dump(self._backing_dict, cf, indent=2)

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


# The location of the config file for this installation of CART.
MAIN_CONFIG = Path(__file__).parent.parent.parent / "configuration.json"

config = CARTConfig(MAIN_CONFIG)
