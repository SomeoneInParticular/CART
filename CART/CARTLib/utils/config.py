import json
from pathlib import Path

# The location of the default config used by a fresh installation of CART.
#  DO NOT TOUCH IT UNLESS YOU KNOW WHAT YOU'RE DOING.
DEFAULT_FILE = Path(__file__).parent / "default_config.json"


class Config:
    """
    Configuration manager for CART.
    """
    # Contains the actual configuration values, loaded from and saved to JSON
    _config_dict: dict = {}

    # Whether a change has been made to the config that the user might want to save
    _has_changed: bool = False

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
            with open(DEFAULT_FILE, "r") as cf:
                # Load the data
                self._backing_dict = json.load(cf)
                # And immediately save it, creating a copy
                self.save()
        # Otherwise, load the configuration as-is
        else:
            with open(self.config_path, "r") as cf:
                self._config_dict = json.load(cf)

        # Mark that there are no longer any changes between the config and file
        self._has_changed = False

    def save(self):
        """
        Save the in-memory contents of the configuration back to our JSON file
        """
        with open(MAIN_CONFIG, "w") as cf:
            json.dump(self._config_dict, cf, indent=2)

        # Mark that there are no longer any changes between the config and file
        self._has_changed = False

    def get_users(self) -> list[str]:
        key = "users"
        # Attempt to get the users entry
        user_entry = self._config_dict.get(key, None)

        # If it didn't exist, add an empty list instead
        if user_entry is None:
            user_entry = []
            print(f"No '{key}' entry existed, setting it to {user_entry}.")
            self._config_dict[key] = user_entry
            self._has_changed = True

        # Otherwise, return it as-is
        return user_entry

# The location of the config file for this installation of CART.
MAIN_CONFIG = Path(__file__).parent.parent.parent / "configuration.json"

config = Config(MAIN_CONFIG)
