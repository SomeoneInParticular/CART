from contextlib import contextmanager

import qt

from GenericClassificationUnit import GenericClassificationUnit


# Type hint guard; only risk the cyclic import if type hints are running
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    # noinspection PyUnusedImports
    from GenericClassificationTask import GenericClassificationTask


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

        # Build the button panel
        self._setupButtonPanel(formLayout)

        # Build the combobox
        self._setupCheckboxList(formLayout)

        # Initialize the list entries to match our bound task
        self._syncListEntriesWithTask()

        # Return the layout
        return formLayout

    def _setupButtonPanel(self, layout: qt.QFormLayout):
        # Sub-layout to make the buttons equally sized
        subLayout = qt.QHBoxLayout()

        # Add an "addition" button
        addButton = qt.QPushButton()
        addButton.setText("Add New Class")

        # When the button is pressed, generate the new class prompt
        def addNewClass():
            # TODO: Create a UI prompt instead
            with self.block_signals():
                self.addNewClass(str(len(self.bound_task.class_map)), "New!")

        addButton.clicked.connect(
            addNewClass
        )

        # Add it to our layout
        subLayout.addWidget(addButton)

        # Add a "Drop" button, allowing existing classes to be removed
        dropButton = qt.QPushButton()
        dropButton.setText("Drop Selected Class")

        # Initially disable
        dropButton.enabled = False

        # When the button is pressed, drop the currently selected class
        dropButton.clicked.connect(self.dropSelectedClass)

        # Track it for later, and add it to the sub-layout
        self.dropButton = dropButton
        subLayout.addWidget(dropButton)

        # Place the buttons into a dummy widget and place it in the layout
        dummyWidget = qt.QWidget()
        dummyWidget.setLayout(subLayout)
        layout.addWidget(dummyWidget)

    def _setupCheckboxList(self, layout: qt.QFormLayout):
        # Generate a label for this list
        label = qt.QLabel("Classifications:")
        layout.addWidget(label)

        # Create the list widget
        listWidget = qt.QListWidget()

        # Ensure that any changes to each item in the list sync with the current data unit
        def onItemChanged(item: qt.QListWidgetItem):
            self.current_unit.toggle_class(
                item.text(),
                item.checkState()
            )
        listWidget.itemChanged.connect(onItemChanged)

        # Enable the "drop selected" button only when a row is selected
        listWidget.currentRowChanged.connect(
            lambda i: self.dropButton.setEnabled(i != -1)
        )

        # Add it to the layout and track it for later
        layout.addWidget(listWidget)
        self.classList = listWidget

    def _syncListEntriesWithTask(self):
        # Block signals to avoid error spam
        with self.block_signals():
            # Add each entry in the class map to our list widget
            for k, v in self.bound_task.class_map.items():
                self._addListEntry(k, v)

    @property
    def current_unit(self) -> GenericClassificationUnit:
        # Shortcut to avoid repeated chained calls
        return self.bound_task.current_unit

    @contextmanager
    def block_signals(self):
        # Disable the list from sending signals
        self.classList.blockSignals(True)

        # Do whatever we need
        yield

        # Restore signal emission
        self.classList.blockSignals(False)

    def _addListEntry(self, label: str, desc: str = None):
        # Add the entry to the list directly
        newEntry = qt.QListWidgetItem(label, self.classList)

        # Ensure it has a checkbox
        newEntry.setFlags(
            newEntry.flags() | qt.Qt.ItemIsUserCheckable
        )
        newEntry.setCheckState(
            qt.Qt.Unchecked
        )

        # Make its tooltip the description
        if not desc:
            desc = f"Default description for {label}"
        newEntry.setToolTip(desc)

        # Return the new entry for further processing
        return newEntry

    def syncWithDataUnit(self):
        # Calculate the sets of items to check
        checked_items = self.current_unit.classes
        with self.block_signals():
            for i in range(self.classList.count):
                item = self.classList.item(i)
                if item.text() in checked_items:
                    item.setCheckState(
                        qt.Qt.Checked
                    )
                else:
                    item.setCheckState(
                        qt.Qt.Unchecked
                    )

    def addNewClass(self, label: str, desc: str = None):
        # Skip if we already have a class with this label
        if label in self.bound_task.class_map.keys():
            raise ValueError(f"Cannot add class {label}, already exists!")

        # Add it to our list
        self._addListEntry(label, desc)

        # Add it to our bound logic as well
        self.bound_task.class_map[label] = desc

    def dropSelectedClass(self):
        # "Pop" the currently selected from the list widget
        row_idx = self.classList.currentRow
        droppedItem = self.classList.takeItem(row_idx)

        # Remove the corresponding class from our logic as well
        class_label = droppedItem.text()
        del self.bound_task.class_map[class_label]

        # De-select other entries in the list to avoid "double-click double-delete"
        self.classList.currentRow = -1
