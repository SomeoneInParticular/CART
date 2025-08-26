import qt

from CARTLib.utils.config import DictBackedConfig, UserConfig


class MultiContrastSegmentationConfig(DictBackedConfig):
    """
    Configuration manager for the MultiContrast task
    """
    CONFIG_KEY = "multi_contrast_segmentation"

    def __init__(self, parent_config: UserConfig):
        super().__init__(parent_config=parent_config)

    @classmethod
    def default_config_label(cls) -> str:
        return cls.CONFIG_KEY

    ## Configuration Options ##
    SHOW_ON_LOAD_KEY = "show_on_load"

    @property
    def show_on_load(self) -> bool:
        return self._backing_dict.get(self.SHOW_ON_LOAD_KEY, False)

    @show_on_load.setter
    def show_on_load(self, new_state: bool):
        self._backing_dict[self.SHOW_ON_LOAD_KEY] = new_state
        self.has_changed = True

    ## Utils ##
    def show_gui(self):
        # Build the Config prompt
        prompt = MultiContrastSegmentationConfigGUI(bound_config=self)
        # Show it, blocking other interactions until its resolved
        prompt.exec()


class MultiContrastSegmentationConfigGUI(qt.QDialog):
    """
    Configuration dialog which allows the user to configure this task.
    """
    def __init__(self, bound_config: MultiContrastSegmentationConfig):
        # Initialize the QDialog base itself
        super().__init__()

        # Track the config we are abound too
        self.bound_config: MultiContrastSegmentationConfig = bound_config

        # Button box to reference later
        self.buttonBox: qt.QDialogButtonBox = None

        # Build the UI elements for this dialog
        self.build_ui()

    def build_ui(self):
        # General window properties
        self.setWindowTitle("CART Configuration")

        # Create a form layout to hold everything in
        layout = qt.QFormLayout()
        self.setLayout(layout)

        # Add a checkbox for "show_on_load"
        loadOnShowCheckBox = qt.QCheckBox()
        loadOnShowLabel = qt.QLabel("Show Segmentation on Load:")
        loadOnShowLabel.setToolTip(
            "If checked, the primary segmentation (if present) will be shown immediately."
        )

        # Ensure it is synchronized with the configuration settings
        loadOnShowCheckBox.setChecked(self.bound_config.show_on_load)
        def onLoadShowCheckBoxChanged(new_val: bool):
            self.bound_config.show_on_load = new_val
        loadOnShowCheckBox.stateChanged.connect(onLoadShowCheckBoxChanged)

        # Add it to our layout
        layout.addRow(loadOnShowLabel, loadOnShowCheckBox)

        # Add our button array to the bottom of the GUI
        self.buttonBox = self.addButtons()
        layout.addRow(self.buttonBox)

    def addButtons(self) -> qt.QDialogButtonBox:
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
            self.bound_config.save()
            self.accept()
        elif button_role == qt.QDialogButtonBox.RejectRole:
            self.preCloseCheck()
            self.reject()
        elif button_role == qt.QDialogButtonBox.ResetRole:
            self.bound_config.backing_dict = self._reserve_state
            self.reject()
        else:
            raise ValueError("Pressed a button with an invalid role somehow...")

    ## On-close calls ##
    def preCloseCheck(self):
        """
        Before the prompt closes, check to confirm no changes were made
        that the user might want to save beforehand!

        :return: Whether the save request was accepted.
        """
        # Only run checks if the config has changed at all
        if self.bound_config.has_changed:
            reply = qt.QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have not saved your changes; would you like to now?",
                qt.QMessageBox.Yes, qt.QMessageBox.No
            )
            # Save to file only if the user confirms it
            if reply == qt.QMessageBox.Yes:
                self.bound_config.save()
                return True
            else:
                self.bound_config.backing_dict = self._reserve_state
                return False
        # Otherwise, just pass successfully
        return True

    def closeEvent(self, event):
        """
        Intercepts when the user closes the window outside by clicking the 'x'
        in the top right; ensures any modifications don't get discarded by mistake.
        """
        self.preCloseCheck()
        event.accept()
