import json
from pathlib import Path
from typing import Optional

import qt

# The location of the default config used by a fresh installation of CART.
#  DO NOT TOUCH IT UNLESS YOU KNOW WHAT YOU'RE DOING.
DEFAULT_FILE = Path(__file__).parent / "default_config.json"


## GUI elements ##
class NewUserDialog(qt.QDialog):
    def __init__(self, reference_profile: "UserConfig", master_config: "CARTConfig"):
        # Initialize the QDialog base itself
        super().__init__()

        # The dictionary actually containing what we'll be saving
        self.profile_dict: dict = {}

        # A reference config to copy from if the user requests it
        self.reference_profile = reference_profile

        # The master config we want to save the profile too
        self.master_config = master_config

        # The text field widget for the username
        self.usernameEdit: qt.QLineEdit = None

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
        self.setWindowTitle("New User")

        # Create a form layout to hold everything in
        layout = qt.QFormLayout()
        self.setLayout(layout)

        # Add a field for submitting the username
        usernameEdit = qt.QLineEdit()
        usernameLabel = qt.QLabel("Username:")
        usernameLabel.setToolTip(
            "The ID for this profile. Cannot match an existing username!"
        )
        self.usernameEdit = usernameEdit

        # Add them to our layout
        layout.addRow(usernameLabel, usernameEdit)

        # Add the blank-state checkbox
        blankStateBox = qt.QCheckBox()
        blankStateLabel = qt.QLabel("Reset to Default?")
        blankStateLabel.setToolTip("""
            If selected, the new user profile will have no configuration settings, 
            being a "blank slate". If unchecked, the configuration settings of the 
            current profile (including the last-used settings) are copied over instead.
        """)
        self.blankSlateBox = blankStateBox
        layout.addRow(blankStateLabel, blankStateBox)

        # Add our button array to the bottom of the GUI
        self.buttonBox = self.addButtons()
        layout.addRow(self.buttonBox)

        # Connect everything together
        # TODO

    def onButtonPressed(self, button: qt.QPushButton):
        # Get the role of the button
        button_role = self.buttonBox.buttonRole(button)
        # Match it to our corresponding function
        # TODO: Replace this with a `match` statement when porting to Slicer 5.9
        if button_role == qt.QDialogButtonBox.AcceptRole:
            self.saveNewProfile()
            self.accept()
        elif button_role == qt.QDialogButtonBox.RejectRole:
            self.reject()
        else:
            raise ValueError("Pressed a button with an invalid role somehow...")

    ## Access Management ##s
    @property
    def username(self) -> str:
        return self.usernameEdit.text

    @property
    def shouldBlankState(self) -> bool:
        return self.blankSlateBox.isChecked()

    ## Utils
    def saveNewProfile(self):
        if self.shouldBlankState:
            self.master_config.new_user_profile(
                self.username,
                self.profile_dict
            )
        else:
            self.master_config.new_user_profile(
                self.username,
                self.profile_dict,
                self.reference_profile
            )


class ConfigGUI(qt.QDialog):
    """
    Configuration dialog which allows the user to configure CART.
    """
    def __init__(self, bound_config: "UserConfig"):
        # Initialize the QDialog base itself
        super().__init__()

        # Track the bound configuration to ourselves
        self.bound_config = bound_config

        # Track the backing dict of the config at this state to restore
        # if the user backs out; we're not copying here because the
        # config's 'backing_dict' config does that for us already.
        self._reserve_state = bound_config.backing_dict

        # Track the button box so we can react to them being pressed
        self.buttonBox: qt.QDialogButtonBox = None

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
        iterSaveCheck.stateChanged.connect(setSaveOnIter)

        # Add it to our layout
        layout.addRow(iterSaveLabel, iterSaveCheck)

        # Add our button array to the bottom of the GUI
        self.buttonBox = self.addButtons()
        layout.addRow(self.buttonBox)

    def addButtons(self):
        buttonBox = qt.QDialogButtonBox()
        buttonBox.setStandardButtons(
            qt.QDialogButtonBox.Reset | qt.QDialogButtonBox.Cancel | qt.QDialogButtonBox.Ok
        )
        buttonBox.clicked.connect(self.onButtonPressed)
        return buttonBox

    def onButtonPressed(self, button: qt.QPushButton):
        # Get the role of the button
        button_role = self.buttonBox.buttonRole(button)
        # Match it to our corresponding function
        # TODO: Replace this with a `match` statement when porting to Slicer 5.9
        if button_role == qt.QDialogButtonBox.AcceptRole:
            self.bound_config.save_to_file()
            self.accept()
        elif button_role == qt.QDialogButtonBox.RejectRole:
            self.preCloseCheck()
            self.reject()
        elif button_role == qt.QDialogButtonBox.ResetRole:
            self.bound_config.backing_dict = self._reserve_state
            self.reject()
        else:
            raise ValueError("Pressed a button with an invalid role somehow...")

    def preCloseCheck(self):
        """
        Before the prompt closes, check to confirm no changes were made
        that the user might want to save beforehand!

        :return: Whether the save request was accepted.
        """
        if self.bound_config.has_changed:
            reply = qt.QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have not saved your changes; would you like to now?",
                qt.QMessageBox.Yes, qt.QMessageBox.No
            )
            # Save to file only if the user confirms it
            if reply == qt.QMessageBox.Yes:
                self.bound_config.save_to_file()
                return True
            else:
                self.bound_config.backing_dict = self._reserve_state
                return False

    def closeEvent(self, event):
        """
        Intercepts when the user closes the window outside by clicking the 'x'
        in the top right; ensures any modifications don't get discarded by mistake.
        """
        self.preCloseCheck()
        event.accept()


## Backing Config Managers ##
class UserConfig:
    """
    Configuration manager for a CART user profile.

    Tracks the user's settings, allowing for them to be
    swapped on the fly.
    """

    DEFAULT_ROLE = "N/A"

    def __init__(self, username: str, config_dict: dict, cart_config: "CARTConfig"):
        # The username for this profile
        self._username = username

        # Cross-reference attributes
        self._backing_dict = config_dict
        self._cart_config = cart_config

        # Track whether something has changed, so other processes can reference it
        self._has_changed = False

    @property
    def username(self):
        return self._username

    @property
    def has_changed(self):
        return self._has_changed

    @property
    def backing_dict(self):
        # KO: We really don't want direct access to the dict itself,
        #  so we return a copy instead
        return self._backing_dict.copy()

    @backing_dict.setter
    def backing_dict(self, new_dict: dict):
        # KO: we can't just assign, otherwise it would
        #  de-sync with the global config
        self._backing_dict.clear()
        for k, v in new_dict.items():
            self._backing_dict[k] = v
        # We presume direct assignment = not changed;
        # the dev can explicitly specify otherwise if need be
        self._has_changed = False

    ## Last Used Settings ##
    LAST_USED_COHORT_KEY = "last_used_cohort_file"

    @property
    def last_used_cohort_file(self) -> Path:
        val = Path(self._backing_dict.get(self.LAST_USED_COHORT_KEY, ""))
        return val

    @last_used_cohort_file.setter
    def last_used_cohort_file(self, new_path: Path):
        self._backing_dict[self.LAST_USED_COHORT_KEY] = str(new_path)
        self._has_changed = True

    LAST_USED_DATA_KEY = "last_used_data_path"

    @property
    def last_used_data_path(self) -> Path:
        val = Path(self._backing_dict.get(self.LAST_USED_DATA_KEY, ""))
        return val

    @last_used_data_path.setter
    def last_used_data_path(self, new_path: Path):
        self._backing_dict[self.LAST_USED_DATA_KEY] = str(new_path)
        self._has_changed = True

    LAST_USED_TASK_KEY = "last_used_task"

    @property
    def last_used_task(self) -> str:
        val = self._backing_dict.get(self.LAST_USED_TASK_KEY, "")
        return val

    @last_used_task.setter
    def last_used_task(self, new_task: str):
        self._backing_dict[self.LAST_USED_TASK_KEY] = new_task

    ## User Role ##
    ROLE_KEY = "role"

    @property
    def role(self) -> str:
        return self._get_or_default(self.ROLE_KEY, self.DEFAULT_ROLE)

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
        if self.has_changed:
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
    DEFAULT_ROLES = [UserConfig.DEFAULT_ROLE]

    @property
    def profiles(self) -> dict[str, dict]:
        return self._get_or_default(self.PROFILE_KEY, {})

    def new_user_profile(
            self,
            username: str,
            user_settings: dict = None,
            reference_profile: UserConfig = None
    ) -> UserConfig:
        """
        Create a new user profile, copying config entries from a
        reference profile if provided.
        """
        # Confirm that the provided username is available and valid
        stripped_name = username.strip()
        if not stripped_name:
            raise ValueError("Cannot create a user without a username!")

        if stripped_name in GLOBAL_CONFIG.profiles.keys():
            raise ValueError(f"User with username '{stripped_name}' already exists!")

        # If a reference profile was provided, use its settings as our base
        if reference_profile:
            # Note; this is implicitly copied via the profile's setter property
            new_profile = reference_profile.backing_dict
        # Otherwise, start with a blank slate
        else:
            new_profile = {}

        # We can have a set of settings to override as well, if provided
        if user_settings:
            for k, v in user_settings.items():
                new_profile[k] = v

        # Assign it into our profile dictionary
        self.profiles[username] = new_profile

        # Return the result, wrapped in our UserConfig
        return UserConfig(username, new_profile, self)

    def get_user_config(self, username: str) -> Optional[UserConfig]:
        user_dict = self.profiles.get(username, None)
        if user_dict is not None:
            return UserConfig(username, user_dict, self)
        else:
            return None

    def promptNewUser(self, reference_profile: UserConfig = None) -> Optional[str]:
        """
        Generate a QT prompt for the user to create a new profile entry.

        :param reference_profile: The profile to copy configuration settings from (if any)

        :return: The username of the new user; None if the user backed out.
        """
        # Try to generate a new user from the settings
        prompt = NewUserDialog(reference_profile, GLOBAL_CONFIG)
        user_added_successfully = prompt.exec()

        # If successful, return the username for easy reference
        if user_added_successfully:
            # Return the new username for reference elsewhere
            return prompt.username
        # Otherwise, return nothing
        else:
            return None

    LAST_USER_KEY = "last_user"

    @property
    def last_user(self):
        return self._get_or_default(
            self.LAST_USER_KEY, self.DEFAULT_USERNAME
        )

    @last_user.setter
    def last_user(self, new_user: str):
        self._backing_dict[self.LAST_USER_KEY] = new_user

    USER_ROLES_KEY = "user_roles"

    @property
    def user_roles(self) -> list[str]:
        return self._get_or_default(self.USER_ROLES_KEY, self.DEFAULT_ROLES)

    def new_user_role(self, new_role: str):
        if new_role in self.user_roles:
            raise ValueError(f"Role '{new_role}' already exists!")

        self.user_roles.append(new_role)

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

GLOBAL_CONFIG = CARTConfig(MAIN_CONFIG)
