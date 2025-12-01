from pathlib import Path
from typing import TYPE_CHECKING

import qt
from slicer.i18n import tr as _

from CARTLib.utils.task import CART_TASK_REGISTRY


if TYPE_CHECKING:
    # Avoid a cyclical import
    from CART import CARTLogic
    # NOTE: this isn't perfect (this only exposes Widgets, and Slicer's QT impl
    # isn't the same as PyQT5 itself), but it's a LOT better than constant
    # cross-referencing
    import PyQt5.Qt as qt


class CARTSetupWizard(qt.QWizard):
    """
    Linear setup wizard for CART; walks the user through
    setting up their master profile, creating the initial
    configuration file once completed.
    """

    LOGO_PIXMAP = qt.QPixmap(Path("../../Resources/Icons/CART.png"))

    AUTHOR_KEY = "author"
    POSITION_KEY = "position"
    SELECTED_TASK_KEY = "selected_task"

    def __init__(self, parent):
        super().__init__(parent)

        # Standard elements
        self.setWindowTitle("CART " + _("Setup"))
        self.setPixmap(
            qt.QWizard.LogoPixmap,
            self.LOGO_PIXMAP
        )

        # Add pages
        self.addPage(self.createIntroPage())
        self.addPage(self.createProfileCreationPage())
        self.addPage(self.createSelectTaskPage())

    ## Pages ##
    @staticmethod
    def createIntroPage():
        # Basic Attributes
        page = qt.QWizardPage()
        page.setTitle(_("Introduction"))
        layout = qt.QVBoxLayout()
        page.setLayout(layout)

        # Introduction text
        label = qt.QLabel(_(
            "Welcome to CART! This wizard will help you get started with your first job."
        ))
        label.setWordWrap(True)
        layout.addWidget(label)

        return page

    def createProfileCreationPage(self):
        # Basic Attributes
        page = qt.QWizardPage()
        page.setTitle(_("Profile Creation"))
        layout = qt.QFormLayout()
        page.setLayout(layout)

        # Instruction text
        instructionLabel = qt.QLabel(_(
            "Please fill out the following fields:"
        ))
        instructionLabel.setWordWrap(True)
        layout.addRow(instructionLabel)

        # Author name
        authorLabel = qt.QLabel(_("Author:"))
        authorLineEdit = qt.QLineEdit()
        authorLineEdit.setPlaceholderText(_("How you want to be identified."))
        authorLabel.setBuddy(authorLineEdit)
        layout.addRow(authorLabel, authorLineEdit)
        # The asterisk marks this field as "mandatory"
        page.registerField(self.AUTHOR_KEY + "*", authorLineEdit)

        # Position
        positionLabel = qt.QLabel(_("Position"))
        positionLineEdit = qt.QLineEdit()
        positionLineEdit.setPlaceholderText(_(
            "Clinician, Research Associate, Student etc."
        ))
        positionLabel.setBuddy(positionLineEdit)
        layout.addRow(positionLabel, positionLineEdit)
        page.registerField(self.POSITION_KEY, positionLineEdit)

        return page

    def createSelectTaskPage(self):
        # Basic Attributes
        page = qt.QWizardPage()
        page.setTitle(_("Task Selection"))
        layout = qt.QVBoxLayout()
        page.setLayout(layout)

        # Instruction text
        instructionLabel = qt.QLabel(_(
            "Please select the task you want to run:"
        ))
        instructionLabel.setWordWrap(True)
        layout.addWidget(instructionLabel)

        # Task selection
        taskSelectionWidget = qt.QComboBox()
        taskSelectionWidget.placeholderText = _("[None Selected]")
        taskSelectionWidget.addItems(list(
            CART_TASK_REGISTRY.keys()
        ))
        page.registerField(self.SELECTED_TASK_KEY, taskSelectionWidget)
        layout.addWidget(taskSelectionWidget)

        # Task description
        taskDescriptionWidget = qt.QTextEdit(_(
            "Details about the selected task will appear here."
        ))
        # Make it fill out all available space
        taskDescriptionWidget.setSizePolicy(
            qt.QSizePolicy.Expanding, qt.QSizePolicy.Expanding
        )
        # Add a border around it to visually distinguish it
        taskDescriptionWidget.setFrameShape(qt.QFrame.Panel)
        taskDescriptionWidget.setFrameShadow(qt.QFrame.Sunken)
        taskDescriptionWidget.setLineWidth(3)
        # Align text to the upper-left
        taskDescriptionWidget.setAlignment(qt.Qt.AlignLeft | qt.Qt.AlignTop)
        # Make it read-only
        taskDescriptionWidget.setReadOnly(True)
        # When the selected task changes, update the description text to match
        def onSelectedTaskChanged(new_task: str):
            task = CART_TASK_REGISTRY.get(new_task)
            taskDescriptionWidget.setMarkdown(task.description())
        taskSelectionWidget.currentTextChanged.connect(onSelectedTaskChanged)
        # Add it to the layout
        layout.addWidget(taskDescriptionWidget)

        return page

    ## Fields/Properties ##
    @property
    def author(self) -> str:
        return self.field(self.AUTHOR_KEY)

    @property
    def position(self) -> str:
        return self.field(self.POSITION_KEY)

    @property
    def selected_task(self) -> str:
        return self.field(self.SELECTED_TASK_KEY)

    ## Utils ##
    def update_logic(self, logic: "CARTLogic"):
        # Update the logic's attributes
        logic.author = self.author
        logic.position = self.position

        # Have the logic save its config immediately
        logic.save_master_config()
