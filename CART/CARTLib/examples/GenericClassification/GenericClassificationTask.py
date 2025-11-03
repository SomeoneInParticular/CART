from pathlib import Path
from typing import Optional

import ctk
import qt

from CARTLib.core.TaskBaseClass import TaskBaseClass, DataUnitFactory, D
from CARTLib.examples.GenericClassification.GenericClassificationUnit import GenericClassificationUnit
from CARTLib.utils.config import ProfileConfig
from CARTLib.utils.task import cart_task


class GenericClassificationGUI:
    def __init__(self, bound_task: "GenericClassificationTask"):
        # The task (logic) this GUI should be bound too
        self.bound_task = bound_task

    def setup(self) -> qt.QFormLayout:
        """
        Build the GUI's contents, returning its layout for later use
        """
        # Initialize the layout
        formLayout = qt.QFormLayout()

        # Build the combobox
        self._setupCheckbox(formLayout)

        # Return the layout
        return formLayout

    def _setupCheckbox(self, layout: qt.QFormLayout):
        # Generate a label for this combobox
        label = qt.QLabel("Classifications:")
        layout.addWidget(label)

        # Make a sub-layout to align everything within
        subLayout = qt.QHBoxLayout()

        # Generate the CTK checkbox combobox
        comboBox = ctk.ctkCheckableComboBox()

        # Ensure that changes to the combobox reflect in the data unit
        comboBox.checkedIndexesChanged.connect(
            lambda c=comboBox: print(c.currentText.split("\n"))
        )

        # Track it for later
        self.comboBox = comboBox

        # Insert it into the layout
        subLayout.addWidget(comboBox)

        # Add an "addition" button
        addButton = qt.QToolButton()
        addButton.setText("+")

        # When the button is pressed, generate the new class prompt
        addButton.clicked.connect(
            # TODO
            lambda: print("=" * 100)
        )

        # Add it to the sub-layout
        subLayout.addWidget(addButton)

        # Place the sub layout into the main one
        dummyWidget = qt.QWidget()
        dummyWidget.setLayout(subLayout)
        layout.addWidget(dummyWidget)

    @property
    def current_unit(self) -> GenericClassificationUnit:
        return self.bound_task.current_unit

    def syncWithTask(self):
        # Disable signals to reduce spam
        self.comboBox.blockSignals(True)

        # Reset the combobox with the current contents of the task + data unit
        self.comboBox.clear()

        # Add all elements from the bound task, checking those already present in the data unit
        new_options = self.bound_task.class_options
        for i, o in enumerate(new_options):
            self.comboBox.addItem(i)
            if i in self.current_unit.classes:
                self.comboBox.setCheckState(i, True)

        # Restore signals to allow implicit synchronization
        self.comboBox.blockSignals(False)

        # TODO; Depending on config, adding classes in data unit not already registered

@cart_task("Generic Classification")
class GenericClassificationTask(TaskBaseClass[GenericClassificationUnit]):
    """
    Task for classifying cases.

    Can be run in two modes:
    * Single Class: Only one classification can be selected per case
    * Multi-class: Multiple classifications can be selected per case

    Saves the classification(s) into a CSV folder
    """
    def __init__(self, profile: ProfileConfig):
        super().__init__(profile)

        # Track the active GUI instance, if any
        self.gui: Optional[GenericClassificationGUI] = None

        # CSV Log (path + contents)
        self.csv_log_path: Optional[Path] = None
        self.csv_log = None

        # Currently managed data unit
        self.current_unit: Optional[GenericClassificationUnit] = None

        # Currently available classes
        self.class_options: set[str] = set()

    def setup(self, container: qt.QWidget):
        # Create and track the GUI
        self.gui = GenericClassificationGUI(self)
        gui_layout = self.gui.setup()
        container.setLayout(gui_layout)

        # Update the GUI to match our state
        self.gui.syncWithTask()

    def receive(self, data_unit: GenericClassificationUnit):
        # Track the data unit for later
        self.current_unit = data_unit

        # Refresh the GUI to match the new data unit's contents
        if self.gui:
            self.gui.syncWithTask()


    def save(self) -> Optional[str]:
        pass

    @classmethod
    def getDataUnitFactories(cls) -> dict[str, DataUnitFactory]:
        return {
            "Default": GenericClassificationUnit
        }
