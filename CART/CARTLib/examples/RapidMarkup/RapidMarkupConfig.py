from pathlib import Path
from typing import Optional

import qt
from slicer.i18n import tr as _


from CARTLib.utils.config import DictBackedConfig, ConfigDialog


class RapidMarkupConfigDialog(ConfigDialog["RapidMarkupConfig"]):
    def sync(self):
        # Update the auto-start checkbox to match the config state
        self.autoStartCheckBox.blockSignals(True)

        self.autoStartCheckBox.setChecked(self.bound_config.start_automatically)

        self.autoStartCheckBox.blockSignals(False)

    def buildGUI(self, layout: qt.QFormLayout):
        # General window properties
        self.setWindowTitle(_("Rapid Markup Configuration"))

        # Build checkboxes for the GUI
        self._buildCheckboxes(layout)

    def _buildCheckboxes(self, layout: qt.QFormLayout):
        # Checkbox for automated markup placement start
        autoStartCheckBox = qt.QCheckBox()
        autoStartLabel = qt.QLabel(_("Start Automatically"))
        autoStartLabel.setToolTip(_(
            "If checked, markup placement for the next unplaced label will "
            "begin automatically when a new case is loaded."
        ))

        # When the checkbox changes, change the values
        def onAutoStartChanged(new_val: bool):
            self.bound_config.start_automatically = new_val
        autoStartCheckBox.stateChanged.connect(onAutoStartChanged)

        # Add it to the layout
        layout.addRow(autoStartCheckBox, autoStartLabel)

        # Track it for later
        self.autoStartCheckBox = autoStartCheckBox


class RapidMarkupConfig(DictBackedConfig):

    CONFIG_KEY = "rapid_markup"

    @classmethod
    def default_config_label(cls) -> str:
        return cls.CONFIG_KEY

    ## Configuration Options ##
    LAST_USED_MARKUPS = "last_used_markup_labels"

    @property
    def last_used_markups(self) -> Optional[list[str]]:
        return self._backing_dict.get(self.LAST_USED_MARKUPS, None)

    @last_used_markups.setter
    def last_used_markups(self, new_markups: list[str]):
        self._backing_dict[self.LAST_USED_MARKUPS] = new_markups
        self.has_changed = True

    LAST_USED_OUTPUT = "last_used_output"

    @property
    def last_used_output(self) -> Optional[Path]:
        path_str = self._backing_dict.get(self.LAST_USED_OUTPUT, None)
        if path_str is None:
            return None
        return Path(path_str)

    @last_used_output.setter
    def last_used_output(self, new_path: Path):
        if new_path is None:
            self._backing_dict[self.LAST_USED_OUTPUT] = None
        else:
            self._backing_dict[self.LAST_USED_OUTPUT] = str(new_path.resolve())
        self.has_changed = True

    START_AUTOMATICALLY = "start_automatically"

    @property
    def start_automatically(self) -> bool:
        return self.get_or_default(self.START_AUTOMATICALLY, False)

    @start_automatically.setter
    def start_automatically(self, new_val: bool) -> None:
        self._backing_dict[self.START_AUTOMATICALLY] = new_val
        self.has_changed = True

    ## Utils ##
    def show_gui(self) -> None:
        dialog = RapidMarkupConfigDialog(self)
        dialog.exec()

