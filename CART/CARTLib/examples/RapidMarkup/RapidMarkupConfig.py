from pathlib import Path
from typing import Optional

import qt
from slicer.i18n import tr as _


from CARTLib.utils.config import DictBackedConfig, ConfigDialog


class RapidMarkupConfigDialog(ConfigDialog["RapidMarkupConfig"]):
    def sync(self):
        # Disable our signals while we synchronize
        with self.block_signals():
            self.autoStartCheckBox.setChecked(self.bound_config.start_automatically)
            self.chainPlacementCheckBox.setChecked(self.bound_config.chain_placement)

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

        # When the checkbox changes, change the corresponding config value
        def onAutoStartChanged(new_val: bool):
            self.bound_config.start_automatically = new_val
        autoStartCheckBox.stateChanged.connect(onAutoStartChanged)

        # Add it to the layout
        layout.addRow(autoStartLabel, autoStartCheckBox)

        # Track it for later
        self.autoStartCheckBox = autoStartCheckBox

        # Checkbox for chaining markup placements
        chainPlacementCheckBox = qt.QCheckBox()
        chainPlacementLabel = qt.QLabel(_("Chain Placements"))
        chainPlacementLabel.setToolTip(_(
            "If checked, placing or skipping a markup label will initiate the  "
            "placement of the next markup label in the list. "
            "Repeats until all unplaced labels have been placed or skipped."
        ))

        # When the checkbox changes, change the values
        def onChainPlacementChanged(new_val: bool):
            self.bound_config.chain_placement = new_val
        chainPlacementCheckBox.stateChanged.connect(onChainPlacementChanged)

        # Add it to the layout
        layout.addRow(chainPlacementLabel, chainPlacementCheckBox)

        # Track it for later
        self.chainPlacementCheckBox = chainPlacementCheckBox


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

    CHAIN_PLACEMENT = "chain_placement"

    @property
    def chain_placement(self) -> bool:
        return self.get_or_default(self.CHAIN_PLACEMENT, False)

    @chain_placement.setter
    def chain_placement(self, new_val: bool):
        self._backing_dict[self.CHAIN_PLACEMENT] = new_val
        self.has_changed = True

    ## Utils ##
    def show_gui(self) -> None:
        dialog = RapidMarkupConfigDialog(self)
        dialog.exec()

