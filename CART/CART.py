import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

import vtk
import ctk
import qt
import slicer
from slicer import vtkMRMLScalarVolumeNode
from slicer.ScriptedLoadableModule import *
from slicer.i18n import tr as _
from slicer.util import VTKObservationMixin

from CARTLib.utils.config import GLOBAL_CONFIG, UserConfig
from CARTLib.core.DataManager import DataManager
from CARTLib.core.DataUnitBase import DataUnitBase
from CARTLib.core.TaskBaseClass import TaskBaseClass, DataUnitFactory


from CARTLib.examples.SegmentationEvaluation.SegmentationEvaluationTask import (
    SegmentationEvaluationTask,
)
from CARTLib.examples.RegistrationReview.RegistrationReviewTask import (
    RegistrationReviewTask,
)
from CARTLib.examples.MultiContrastSegmentation.MultiContrastSegmentationEvaluationTask import (
    MultiContrastSegmentationEvaluationTask,
)

CURRENT_DIR = Path(__file__).parent
CONFIGURATION_FILE_NAME = CURRENT_DIR / "configuration.json"
sample_data_path = CURRENT_DIR.parent / "sample_data"
sample_data_cohort_csv = sample_data_path / "example_cohort.csv"


#
# CART
#


class CART(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "CART"  # It's an acronym title, not really translate-able
        self.parent.categories = ["Utilities"]
        self.parent.dependencies = []  # No dependencies
        # TODO: Move these metadata contents into a standalone file which can
        #  be updated automatically as new PRs are made
        self.parent.contributors = [
            "Kalum Ost (Montréal Polytechnique)",
            "Kuan Yi (Montréal Polytechnique)",
            "Ivan Johnson-Eversoll (University of Iowa)",
        ]
        self.parent.helpText = _(
            """
                CART (Case Annotation and Review Tool) provides a set
                of abstract base classes for creating streamlined annotation
                workflows in 3D Slicer. The framework enables efficient
                iteration through medical imaging cohorts with customizable
                tasks and flexible data loading strategies.

                See more information on the
                <a href="https://github.com/SomeoneInParticular/CART/tree/main">GitHub repository</a>.
            """
        )
        # TODO: replace with organization, grant and thanks
        self.parent.acknowledgementText = _(
            """
                Originally created during Slicer Project Week #43.

                Special thanks the many members of the Slicer community who
                contributed to this work, including the many projects which
                were used as reference. Of note:
                <a href="https://github.com/neuropoly/slicercart">SlicerCART</a> (the name and general framework),
                <a href="https://github.com/JoostJM/SlicerCaseIterator">SlicerCaseIterator</a> (inspired much of our logic),
                <a href="https://github.com/SlicerUltrasound/SlicerUltrasound">SlicerUltrasound/AnnotateUltrasound</a> (basis for our UI design),
                and the many other projects discussed during the breakout session (notes
                <a href="https://docs.google.com/document/d/12XuYPVuRgy4RTuIabSIjy_sRrYSliewKhcbB1zJgXVI/">here.</a>)
            """
        )

        # Load our configuration
        GLOBAL_CONFIG.load()

        # Add CARTLib to the Python Path for ease of (re-)use
        import sys

        cartlib_path = (Path(__file__) / "CARTLib").resolve()
        sys.path.append(str(cartlib_path))


#
# CARTParameterNode
#


#
# CARTWidget
#


class CARTWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    ## Utils ##

    # The size constraints which should be used for small buttons;
    #  these match the size of the '...' button in a ctk.ctkPathLineEdit
    # TODO: Remove when we swap the button to be a QToolButton
    MICRO_BUTTON_WIDTH = 24
    MICRO_BUTTON_HEIGHT = 25

    ## Initialization ##
    def __init__(self, parent=None) -> None:
        """Called when the user opens the module the first time and the widget is initialized."""
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)  # needed for parameter node observation

        # Initialize our logic instance
        self.logic: CARTLogic = CARTLogic()
        self._parameterNode = None
        self._parameterNodeGuiTag = None

        # A "dummy" widget, which holds the TaskGUI. Allows us to swap tasks on the fly.
        self.dummyTaskWidget: qt.QWidget = None

    def setup(self) -> None:
        """Called when the user opens the module the first time and the widget is initialized."""
        ScriptedLoadableModuleWidget.setup(self)

        ## Setup ##

        # The collapsible button to contain everything in
        mainGUI = ctk.ctkCollapsibleButton()
        # Not the best translation, but it'll do...
        mainGUI.text = "CART " + _("Setup")
        mainLayout = qt.QFormLayout(mainGUI)

        # User selection/registration
        self.buildUserUI(mainLayout)

        # Cohort Selection
        self.buildCohortUI(mainLayout)

        # Base Path input UI
        self.buildBasePathUI(mainLayout)

        # Task UI
        self.buildTaskUI(mainLayout)

        # Button panel
        self.buildButtonPanel(mainLayout)

        # Add this "main" widget to our panel
        self.layout.addWidget(mainGUI)

        # Make the GUI accessible
        self.mainGUI = mainGUI

        ## Progress Tracker ##
        # Case Iterator UI
        self.buildCaseIteratorUI(self.layout)

        # Add a (currently empty) collapsable tab, in which the Task GUI will be placed later
        taskGUI = ctk.ctkCollapsibleButton()

        # As its empty, and meaningless to the user, start it out collapsed
        #  and disabled; it will be re-enabled (and expanded) when a task
        #  is selected and the iterator set up.
        # KO: While the header for the associated CTK class has a `setCollapsed`
        #  function to match the pattern of every other attribute, it doesn't
        #  work for some reason, hence use breaking the pattern here.
        taskGUI.collapsed = True
        taskGUI.setEnabled(False)

        # Not the best translation, but it'll do...
        taskGUI.text = _("Task Steps")

        # Using a stacked layout, in preparation for future multitask setups
        qt.QStackedLayout(taskGUI)

        self.layout.addWidget(taskGUI)
        self.taskGUI = taskGUI

        # Add a vertical "stretch" at the bottom, forcing everything to the top;
        #  now it doesn't look like garbage!
        self.layout.addStretch()

        # Connections

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(
            slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose
        )
        self.addObserver(
            slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose
        )

        # Synchronize our state with the logic
        self.sync_with_logic()

    ## Core ##
    def sync_with_logic(self):
        # Update the user selection widget with the contents of the logic instance
        users = self.logic.get_available_usernames()
        self.userSelectButton.clear()
        self.userSelectButton.addItems(users)

        # Select the user currently selected by the logic
        try:
            user_idx = users.index(self.logic.active_username)
            self.userSelectButton.currentIndex = user_idx
        except ValueError:
            # Value error indicates the user was not in the list, which is fine
            pass

        # Pull the currently selected cohort file next
        self.cohortFileSelectionButton.currentPath = self.logic.cohort_path

        # Pull the currently selected data path next
        self.dataPathSelectionWidget.currentPath = self.logic.data_path

        # Finally, attempt to update our task from the config
        self.taskOptions.currentText = self.logic.task_id

        # Update our button state to match the new setup
        self.updateButtons()
        self.updateTaskGUI()

    @contextmanager
    def freeze(self):
        """
        Python context manager which 'freezes' the GUI while in use.

        Prevents the user from modifying the GUI elements while some
        process is running (such as a task initializing), avoiding
        de-synchronization or race condition errors

        Also ensures that the GUI is re-enabled after, regardless of
        how the context is terminated.
        """
        # Disable our GUI initially
        self.mainGUI.setEnabled(False)
        self.taskGUI.setEnabled(False)

        # Yield, waiting for the context to be finished
        yield

        # Re-enable the GUI
        self.mainGUI.setEnabled(True)
        self.taskGUI.setEnabled(True)

    ## GUI builders ##
    def buildUserUI(self, mainLayout: qt.QFormLayout):
        """
        Builds the GUI for the user management section of the Widget
        :return:
        """
        # HBox to ensure everything is draw horizontally
        userHBox = qt.QHBoxLayout()

        # Insert this layout in the "main" GUI
        mainLayout.addRow(_("User:"), userHBox)

        # Prior users list
        userSelectButton = qt.QComboBox()
        userSelectButton.placeholderText = _("[Not Selected]")

        # Set the name of the button to the "UserSelectionButton"
        userSelectButton.toolTip = _("Select a previous user.")

        # When the user selects an existing entry, update the program to match
        userSelectButton.activated.connect(self.userSelected)

        # Add it to the HBox
        userHBox.addWidget(userSelectButton)

        # Make the spacing between widgets (the button and dropdown) 0
        userHBox.spacing = 0

        # New user button
        # TODO: Make this a QToolButton instead
        newUserButton = qt.QPushButton("+")

        # When the button is pressed, prompt them to fill out a form
        newUserButton.clicked.connect(self.promptNewUser)

        # Force its size to not change dynamically
        newUserButton.setSizePolicy(qt.QSizePolicy.Fixed, qt.QSizePolicy.Fixed)

        # Force it to be square
        # KO: We can't just use "resize" here, because either Slicer or QT
        #  overrides it later; really appreciate 2 hours of debugging to figure
        #  that out!
        newUserButton.setMaximumWidth(CARTWidget.MICRO_BUTTON_WIDTH)
        newUserButton.setMaximumHeight(CARTWidget.MICRO_BUTTON_HEIGHT)

        # Add it to the layout!
        userHBox.addWidget(newUserButton)

        # Make the user selection button accessible
        self.userSelectButton = userSelectButton

    def buildCohortUI(self, mainLayout: qt.QFormLayout):
        # Directory selection button
        cohortFileSelectionButton = ctk.ctkPathLineEdit()

        # Set file filters to only show readable file types
        cohortFileSelectionButton.filters = ctk.ctkPathLineEdit.Files
        cohortFileSelectionButton.nameFilters = [
            "CSV files (*.csv)",
        ]

        # When the cohort is changed, update accordingly
        cohortFileSelectionButton.currentPathChanged.connect(self.onCohortChanged)

        # TODO: Optionally set a default filter

        # Add it to our layout
        mainLayout.addRow(_("Cohort File:"), cohortFileSelectionButton)

        # Make the button easy-to-access
        self.cohortFileSelectionButton = cohortFileSelectionButton

    def buildBasePathUI(self, mainLayout: qt.QFormLayout):
        """
        Extends the GUI to add widgets for data directory selection
        """
        # Base path selection
        dataPathSelectionWidget = ctk.ctkPathLineEdit()
        dataPathSelectionWidget.filters = ctk.ctkPathLineEdit.Dirs
        dataPathSelectionWidget.toolTip = _(
            "Select the base directory path. Leave empty to use None as base path."
        )

        # Add it to our layout
        mainLayout.addRow(_("Data Path:"), dataPathSelectionWidget)

        # Connect the signal to handle base path changes
        dataPathSelectionWidget.currentPathChanged.connect(self.onDataPathChanged)

        # Make it accessible
        self.dataPathSelectionWidget = dataPathSelectionWidget

    def buildTaskUI(self, mainLayout: qt.QFormLayout):
        # Prior users list
        taskOptions = qt.QComboBox()
        taskOptions.placeholderText = _("[Not Selected]")

        # TODO: Have this pull from configuration instead
        taskOptions.addItems(list(self.logic.task_map.keys()))
        mainLayout.addRow(_("Task"), taskOptions)

        # Make it accessible
        self.taskOptions = taskOptions

        # When the task is changed, update everything to match
        taskOptions.currentIndexChanged.connect(self.onTaskChanged)

    def buildButtonPanel(self, mainLayout: qt.QFormLayout):
        # Add a state to track whether cohort is in preview mode
        self.isPreviewMode = False

        # A button to preview the cohort, without starting on a task
        previewButton = qt.QPushButton(_("Preview"))
        previewButton.setToolTip(
            _(
                """
            Reads the contents of the cohort.csv for review, without starting the task
            """
            )
        )

        # On click, attempt to load the cohort file and its contents into the GUI
        previewButton.clicked.connect(self.onPreviewCohortClicked)

        # Disable the button by default; we need a valid cohort first!
        previewButton.setEnabled(False)

        # A button to open the Configuration dialog, which changes how CART operates
        configButton = qt.QPushButton(_("Configure"))
        configButton.toolTip = _("Change how CART is configured to iterate through your data.")

        # Clicking the config button shows the Config prompt
        configButton.clicked.connect(self.logic.config.show_gui)

        # A button which confirms the current settings and attempts to start
        #  task iteration!
        confirmButton = qt.QPushButton(_("Confirm"))
        confirmButton.toolTip = _("Begin doing this task on your cases.")

        # Disable the button by default; the user needs to fill out everything first!
        confirmButton.setEnabled(False)

        # Attempt to load the task, assuming everything is ready
        confirmButton.clicked.connect(self.loadTaskWhenReady)

        # Place them equally spaced in a single row
        buttonLayout = qt.QHBoxLayout()
        for b in [previewButton, configButton, confirmButton]:
            buttonLayout.addWidget(b)
        mainLayout.addRow(buttonLayout)

        # Make them accessible
        self.previewButton = previewButton
        self.configButton = configButton
        self.confirmButton = confirmButton

    def buildCaseIteratorUI(self, mainLayout: qt.QFormLayout):
        # Layout
        iteratorWidget = qt.QWidget()
        self.taskLayout = qt.QVBoxLayout(iteratorWidget)

        # Add the task "widget" (just a frame to hold everything in) to the global layout
        mainLayout.addWidget(iteratorWidget)

        # Hide this by default, only showing it when we're ready to iterate
        iteratorWidget.setVisible(False)

        # Iterator buttons, in a horizontal layout
        buttonLayout = self.buildIteratorButtonPanel()
        # Add the button layout to the main vertical layout
        self.taskLayout.addLayout(buttonLayout)

        # Add a text field to display the current case name under the buttons
        self.currentCaseNameLabel = qt.QLineEdit()
        self.currentCaseNameLabel.readOnly = True
        self.currentCaseNameLabel.placeholderText = _(
            "Current case name will appear here"
        )
        self.taskLayout.addWidget(self.currentCaseNameLabel)

        # Make the groupbox accessible elsewhere, so it can be made visible later
        self.iteratorWidget = iteratorWidget

    def buildIteratorButtonPanel(self):
        # Button should be laid out left-to-right
        buttonLayout = qt.QHBoxLayout()

        # "Prior Incomplete" Button
        priorIncompleteButton = qt.QPushButton(_("Prior Incomplete"))
        priorIncompleteButton.toolTip = _("Jump back to a previous case which has not been completed yet.")
        priorIncompleteButton.clicked.connect(lambda: self.previousCase(True))

        # "Previous" Button
        previousButton = qt.QPushButton(_("Previous"))
        previousButton.toolTip = _("Return to the previous case.")
        previousButton.clicked.connect(lambda: self.previousCase(False))

        # "Save" Button
        saveButton = qt.QPushButton(_("Save"))
        saveButton.toolTip = _("Save the task for the current case.")
        saveButton.clicked.connect(self.saveTask)

        # "Next" Button
        nextButton = qt.QPushButton(_("Next"))
        nextButton.toolTip = _("Move onto the next case.")
        nextButton.clicked.connect(lambda: self.nextCase(False))

        # "Next Incomplete" Button
        nextIncompleteButton = qt.QPushButton(_("Next Incomplete"))
        nextIncompleteButton.toolTip = \
            _("Jump back to the next case which has not been completed yet.")
        nextIncompleteButton.clicked.connect(lambda: self.nextCase(True))

        # Add them to the layout in our desired order
        for b in [priorIncompleteButton, previousButton, saveButton, nextButton, nextIncompleteButton]:
            buttonLayout.addWidget(b)

        # Track them for later
        self.priorIncompleteButton = priorIncompleteButton
        self.previousButton = previousButton
        self.nextButton = nextButton
        self.nextIncompleteButton = nextIncompleteButton

        return buttonLayout

    ## Connected Functions ##

    ### Setup Widgets ###
    def promptNewUser(self):
        """
        Creates a pop-up, prompting the user to enter their name into a
        text box to register themselves as a new user.
        """
        # Create a new widget
        new_name = qt.QInputDialog().getText(
            self.mainGUI, _("Add New User"), _("New User Name:")
        )

        # Attempt to add the new user to the Logic
        try:
            self.logic.new_user_profile(new_name)
            self.sync_with_logic()
        except Exception as exc:
            self.pythonExceptionPrompt(exc)

    def userSelected(self):
        # Update the logic with this newly selected user
        new_username = self.userSelectButton.currentText
        self.logic.active_username = new_username

        # Rebuild the GUI to match
        self.sync_with_logic()

        # Update the button states to match our current state
        self.updateButtons()

    def _refreshUserList(self):
        """
        Rebuild the list in the GUI from scratch, ensuring everything is
        maintained in order.

        KO: an insertion policy only applies to insertions made into an
         editable combo-box; insertions made by us are always inserted
         last. Therefore, this song and dance is needed
        """
        # Clear all entries
        self.userSelectButton.clear()

        # Rebuild its contents from scratch
        self.userSelectButton.addItems(self.logic.get_available_usernames())

        # Select the first (most recent) entry in the list
        self.userSelectButton.currentIndex = 0

    def onDataPathChanged(self):
        """
        Handles changes to the base path selection.
        Falls back the previous base path if the user specified an empty space.
        """
        # Get the current path from the GUI
        current_path = self.dataPathSelectionWidget.currentPath

        # Strip it of leading/trailing whitespace
        current_path = current_path.strip()

        # If the data path is now empty, reset to the previous path and end early
        if not current_path:
            print("Error: Base path was empty, retaining previous base path.")
            self.dataPathSelectionWidget.currentPath = str(self.logic._data_path)
            self.updateButtons()
            return

        try:
            # Try to update the logic's path to match
            self.logic.data_path = Path(current_path)
        except Exception as exc:
            # Show the user an error
            self.pythonExceptionPrompt(exc)
        finally:
            # In both cases, synchronize with our logic after
            self.sync_with_logic()

    def onCohortChanged(self):
        # Get the currently selected cohort file from the widget
        new_cohort = Path(self.cohortFileSelectionButton.currentPath)

        # Attempt to update the cohort in our logic instance
        try:
            self.logic.cohort_path = new_cohort

            # Disable cohort preview until the user wants it again
            self.isPreviewMode = False

            # Un-toggle the cohort preview button
            self.previewButton.setStyleSheet("")

            # Update relevant GUI elements
            self.updateCohortTable()
        except Exception as exc:
            # Show the error to the user
            self.pythonExceptionPrompt(exc)
        finally:
            # Always sync to the logic after
            self.sync_with_logic()

    def onPreviewCohortClicked(self):
        """
        Load the cohort explicitly, so it can be reviewed.
        """
        # Check if the user is in the middle of changing cohorts and data path doesn't match the cohort yet
        # self.validateDataPathAndCohortMatch()

        # Update preview mode state
        self.isPreviewMode = not self.isPreviewMode

        if self.isPreviewMode:
            # Change the color of the preview button to indicate preview mode
            self.previewButton.setStyleSheet(
                "background-color: #777eb4; color: #777eb4;"
            )
            # Load the file's cases into memory
            self.logic.load_cohort()

        else:
            # Reset preview button
            self.previewButton.setStyleSheet("")

        # Update the cohort table
        self.updateCohortTable()

    def onTaskChanged(self):
        try:
            # Update the currently selected task in our logic
            task_id = self.taskOptions.currentText
            self.logic.task_id = task_id

            # Purge the current task widget, as it is no longer valid
            if self.dummyTaskWidget:
                # Disconnect the widget, and all of its children, from the GUI
                self.dummyTaskWidget.setParent(None)
                # Delete our reference to it as well
                self.dummyTaskWidget = None
        except Exception as exc:
            # If an error occurs, show it to the user
            self.pythonExceptionPrompt(exc)
        finally:
            # Regardless of what happens, ensure we are synced to our logic
            self.sync_with_logic()

    def buildCohortTable(self):

        # Rebuilds the table using the most updated cohort data
        self.destroyCohortTable()

        csv_data_raw = self.logic.data_manager.case_data

        self.headers = list(csv_data_raw[0].keys())
        csv_data_list = [[row[key] for key in self.headers] for row in csv_data_raw]
        self.rowCount = len(csv_data_list)
        self.colCount = len(self.headers)

        self.cohortTable = qt.QTableWidget()

        self.cohortTable.setSizePolicy(
            qt.QSizePolicy.Expanding, qt.QSizePolicy.Expanding
        )

        self.cohortTable.setRowCount(self.rowCount)
        self.cohortTable.setColumnCount(self.colCount)
        self.cohortTable.setHorizontalHeaderLabels([_(h) for h in self.headers])
        self.cohortTable.horizontalHeader().setSectionResizeMode(
            qt.QHeaderView.ResizeToContents
        )

        self.cohortTable.setHorizontalScrollBarPolicy(qt.Qt.ScrollBarAsNeeded)

        # Define a special color for the first column, including the header
        first_col_brush = qt.QBrush(qt.QColor("#8f6ae7"))
        self.cohortTable.horizontalHeaderItem(0).setBackground(first_col_brush)

        for row in range(self.rowCount):
            for col in range(self.colCount):
                item = qt.QTableWidgetItem(csv_data_list[row][col])
                item.setTextAlignment(qt.Qt.AlignLeft | qt.Qt.AlignVCenter)
                if col == 0:
                    item.setToolTip(_("Data Unit"))
                    item.setBackground(first_col_brush)
                else:
                    item.setToolTip(_("Resource of : " + str(csv_data_list[row][0])))

                self.cohortTable.setItem(row, col, item)

        self.cohortTable.setAlternatingRowColors(True)
        self.cohortTable.setShowGrid(True)
        self.cohortTable.verticalHeader().setVisible(False)

        self.cohortTable.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
        self.cohortTable.setSelectionBehavior(qt.QAbstractItemView.SelectRows)
        self.cohortTable.setFocusPolicy(qt.Qt.NoFocus)

        # Disable selection of rows in the table, which may be confused for a highlight
        self.cohortTable.setSelectionMode(qt.QAbstractItemView.NoSelection)

        self.taskLayout.addWidget(self.cohortTable)
        self.iteratorWidget.setVisible(True)

    def destroyCohortTable(self):
        if hasattr(self, "cohortTable"):
            self.taskLayout.removeWidget(self.cohortTable)
        self.iteratorWidget.setVisible(False)

    def updateCohortTable(self):
        # Remove any existing table if not in preview or task mode, e.g. when the cohort csv is changed
        if not self.isPreviewMode and not self.logic.has_active_task:
            self.destroyCohortTable()
            return

        # Disable buttons if in task mode
        if self.logic.has_active_task:
            self.previewButton.setEnabled(False)
            self.confirmButton.setEnabled(False)

        # Disable navigation buttons if only in preview mode
        if self.isPreviewMode and not self.logic.has_active_task:
            self.enablePriorButtons(False)
            self.enableNextButtons(False)

        # Always (re)build the table if in preview or task mode
        self.buildCohortTable()

    ### Iterator Widgets ###
    def unHighlightRow(self, row):
        # Remove the highlight from the current row before proceeding to the following
        # The first column remains unchanged, as it is the uid
        for column in range(1, self.colCount):
            item = self.cohortTable.item(row, column)
            item.setBackground(qt.QColor())

    def highlightRow(self, row):
        # Add the highlight to the following current row
        # The first column remains unchanged, as it is the uid
        for column in range(1, self.colCount):
            item = self.cohortTable.item(row, column)
            item.setBackground(qt.QColor(255, 255, 0, 100))

    def updateIteratorGUI(self):
        # Update the current UID label
        new_label = f"Data Unit {self.logic.current_uid()}"
        self.currentCaseNameLabel.text = new_label

        # Check if we have a next case, and enable/disable the button accordingly
        self.enableNextButtons(self.logic.has_next_case())

        # Check if we have a previous case, and enable/disable the button accordingly
        self.enablePriorButtons(self.logic.has_previous_case())

        # Highlight the following (previous or next) row to indicate the current case
        self.highlightRow(self.logic.data_manager.current_case_index)

    def _loadingCasePrompt(self):
        prompt = qt.QDialog()
        prompt.setWindowTitle("Loading...")

        layout = qt.QVBoxLayout()
        prompt.setLayout(layout)

        description = qt.QLabel(
            "Reading the contents of a new case into memory; please wait."
        )
        layout.addWidget(description)

        return prompt

    def nextCase(self, skip_complete: bool = False) :
        """
        Request the iterator step into the next case.

        :param skip_complete: Whether to skip over already completed
            cases wherever possible
        """
        # Freeze the GUI while running to avoid desync
        with self.freeze():
            try:
                # Confirm we have a next case to step into first
                if not self.logic.has_next_case():
                    self.showErrorPopup(
                        "No Prior Case",
                        "You somehow requested the next case, despite there being none!"
                    )
                    return

                # Create a loading prompt
                loadingPrompt = self._loadingCasePrompt()
                loadingPrompt.show()

                # Remove highlight from the current row
                self.unHighlightRow(self.logic.data_manager.current_case_index)

                # Step into the next case
                self.logic.next_case(skip_complete)

                # Update our GUI to match the new state
                self.updateIteratorGUI()

                # Close the loading prompt
                loadingPrompt.done(qt.QDialog.Accepted)
            except Exception as e:
                # Close the loading prompt, if it was created
                if loadingPrompt:
                    loadingPrompt.done(qt.QDialog.Rejected)
                # Create a new error prompt in its place
                self.pythonExceptionPrompt(e)

    def previousCase(self, skip_complete: bool = False):
        # Freeze the GUI until we are done
        with self.freeze():
            try:
                # Confirm we have a next case to step into first
                if not self.logic.has_previous_case():
                    self.showErrorPopup(
                        "No Prior Case",
                        "You somehow requested the previous case, despite there being none!")
                    return
                # Create a loading prompt
                loadingPrompt = self._loadingCasePrompt()
                loadingPrompt.show()

                # Remove highlight from the current row
                self.unHighlightRow(self.logic.data_manager.current_case_index)

                # Step into the previous case
                self.logic.previous_case(skip_complete)

                # Update our GUI to match the new state
                self.updateIteratorGUI()

                # Close the loading prompt
                loadingPrompt.done(qt.QDialog.Accepted)
            except Exception as e:
                # Close the loading prompt, if it was created
                if loadingPrompt:
                    loadingPrompt.done(qt.QDialog.Rejected)
                # Create a new error prompt in its place
                self.pythonExceptionPrompt(e)

    ### Task Related ###
    def updateTaskGUI(self):
        """
        Show/hide the Task GUI depending on whether our logic
        has an actively running task or not.
        """
        new_state = self.logic.has_active_task
        self.taskGUI.setEnabled(new_state)
        self.taskGUI.collapsed = not new_state

    def updateButtons(self):
        """
        Updates the state of our buttons to reflect the state of our bound logic
        """
        # If our logic is running a task,
        # disable the "confirm" and "preview" buttons and end here
        if self.logic.has_active_task:
            self.previewButton.setEnabled(False)
            self.confirmButton.setEnabled(False)
            return

        # If we have a cohort file, it can be previewed
        if self.logic.cohort_path:
            self.previewButton.setEnabled(True)

        # If the logic says we're ready to start, enable the "confirm" button
        if self.logic.is_ready():
            self.confirmButton.setEnabled(True)

    def _loadingTaskPrompt(self):
        prompt = qt.QDialog()
        prompt.setWindowTitle("Loading...")

        layout = qt.QVBoxLayout()
        prompt.setLayout(layout)

        description = qt.QLabel(
            "Initializing the selected task; please be patient."
        )
        layout.addWidget(description)

        return prompt

    def loadTaskWhenReady(self):
        # If we're not ready to load a task, leave everything untouched
        if not self.logic.is_ready():
            return

        # If cohort csv and data path aren't matching, display a comprehensive error box
        error_message = self.logic.validate_cohort_and_data_path_match()
        if error_message:
            self.showErrorPopup("Cannot Start Task", error_message)
            return  # Stop execution if validation fails

        # Disable the GUI, as to avoid de-synchronization
        with self.freeze():
            try:
                # Create a loading prompt
                loadingPrompt = self._loadingTaskPrompt()
                loadingPrompt.show()

                # Try to initialize the new task
                self.logic.init_task()

                # Create a "dummy" widget that the task can fill
                self.resetTaskDummyWidget()
                # Build the Task GUI, using the prior widget as a foundation
                self.logic.current_task_instance.setup(self.dummyTaskWidget)
                # Add the widget to our layout
                self.taskGUI.layout().addWidget(self.dummyTaskWidget)

                # Expand the task GUI, if it wasn't already
                self.taskGUI.collapsed = False

                # Attempt to read a data unit
                # KO: This needs to be done after GUI init, as many task's (including our
                #  segmentation review) will either load configurations and/or prompt the
                #  user for things required to determine whether a task is "complete" or
                #  not for a given case.
                self.logic.load_initial_unit()

                # Load the cohort csv data into the table, if it wasn't already
                self.updateCohortTable()

                # Reveal the iterator GUI, if it wasn't already
                self.iteratorWidget.setVisible(True)

                # Update the current UID in the iterator
                self.updateIteratorGUI()

                # Collapse the main (setup) GUI, if it wasn't already
                self.mainGUI.collapsed = True

                # Disable preview and confirm buttons, as task has started
                self.updateButtons()

                # Close the loading prompt
                loadingPrompt.done(qt.QDialog.Accepted)
            except Exception as exc:
                # Close the loading prompt, if it was created
                if loadingPrompt:
                    loadingPrompt.done(qt.QDialog.Rejected)
                # Notify the user of the exception
                self.pythonExceptionPrompt(exc)
            finally:
                # Synchronize with our logic
                self.sync_with_logic()

    def resetTaskDummyWidget(self):
        if self.dummyTaskWidget:
            self.dummyTaskWidget.setParent(None)
        self.dummyTaskWidget = qt.QWidget()

    def pythonExceptionPrompt(self, exc: Exception):
        """

        Prompts the user with the contents of an exception. Also logs the
         stack-trace to console for debugging purposes

        Should be used to catch exceptions cause by the GUI, so the user can
         respond appropriately.

        :param exc: The exception that should be handled
        """
        # Print out the exception to the Python log, with traceback.
        print(traceback.format_exc())

        # Display an error message notifying the user
        errorPrompt = qt.QErrorMessage()

        # Add some details on what's happening for the user
        errorPrompt.setWindowTitle("PYTHON ERROR!")

        # Show the message
        errorPrompt.showMessage(exc)
        errorPrompt.exec_()

        # Disable the confirm button, as the current setup didn't work
        self.confirmButton.setEnabled(False)

    def saveTask(self):
        try:
            result = self.logic.current_task_instance.save()
            if not result:
                print("Saved!")
            else:
                print(result)
        except Exception as e:
            self.pythonExceptionPrompt(e)

    ## Management ##
    def enablePriorButtons(self, state: bool):
        for b in [self.priorIncompleteButton, self.previousButton]:
            b.setEnabled(state)

    def enableNextButtons(self, state: bool):
        for b in [self.nextButton, self.nextIncompleteButton]:
            b.setEnabled(state)

    def cleanup(self) -> None:
        """Called when the application closes and the module widget is destroyed."""
        pass

    def enter(self):
        # Delegate to our logic to have tasks properly update
        self.logic.enter()

    def exit(self):
        # Delegate to our logic to have tasks properly update
        self.logic.exit()

    def onSceneStartClose(self, caller, event) -> None:
        """Called just before the scene is closed."""
        pass

    def onSceneEndClose(self, caller, event) -> None:
        """Called just after the scene is closed."""
        pass

    def showErrorPopup(self, title: str, message: str):
        """
        Displays a standardized critical error message box.
        """
        msgBox = qt.QMessageBox()
        msgBox.setIcon(qt.QMessageBox.Critical)
        msgBox.setText(f"<b>{title}</b>")
        msgBox.setInformativeText(message)
        msgBox.setWindowTitle("Validation Error")
        msgBox.setStandardButtons(qt.QMessageBox.Ok)
        # Allows for selectable text in the error message
        msgBox.setTextInteractionFlags(qt.Qt.TextSelectableByMouse)
        msgBox.exec()


#
# CARTLogic
#


class CARTLogic(ScriptedLoadableModuleLogic):
    """This class should implement all the actual
    computation done by your module.  The interface
    should be such that other python code can import
    this class and make use of the functionality without
    requiring an instance of the Widget.
    Uses ScriptedLoadableModuleLogic base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self) -> None:
        """Called when the logic class is instantiated. Can be used for initializing member variables."""
        ScriptedLoadableModuleLogic.__init__(self)

        # Current username
        self._active_username: str = None

        # Current configuration
        self.config: UserConfig = None

        # Path to the cohort file currently in use
        self._cohort_path: Path = None

        # Path to where the user specified their data is located
        self._data_path: Path = None

        # The data manager currently managing case iteration
        self._data_manager: Optional[DataManager] = None

        # The currently selected task Label
        self._task_id: str = None

        # A map of task IDs to their corresponding task type
        # TODO: Load this from our global config
        self.task_map = {
            "Segmentation": SegmentationEvaluationTask,
            "MultiContrast Segmentation": MultiContrastSegmentationEvaluationTask,
            "Registration Review": RegistrationReviewTask,
        }

        # The current task instance
        self.current_task_instance: Optional[TaskBaseClass] = None

        # Current data unit factory
        self.data_unit_factory: Optional[DataUnitFactory] = None

        # Load our last state from the config file
        self._load_user_state(GLOBAL_CONFIG.last_user)

    ## User Management ##
    @property
    def active_username(self) -> str:
        return self._active_username

    @active_username.setter
    def active_username(self, new_name: str):
        # Validate the specified user is valid first
        stripped_name = new_name.strip()

        if not stripped_name:
            raise ValueError("Cannot set the active user to blank!")

        if not stripped_name in GLOBAL_CONFIG.profiles.keys():
            raise ValueError(f"Cannot select user '{stripped_name}'; they don't have a profile!")

        # Set the user's profile as our own
        self._active_username = stripped_name

        # Sync ourselves with this new user
        self._load_user_state(self._active_username)

        # Clear any active task, as its no longer relevant
        self.clear_task()

        # Update the config to designate that this user is now the most recent
        GLOBAL_CONFIG.last_user = stripped_name

    def _load_user_state(self, username: str):
        """
        Attempt to load our last state from the configuration file
        """
        # If a previous user doesn't exist, leave as-is
        if not username:
            raise ValueError("Cannot load a blank user!")

        # Try to load that user's configuration
        self.config = GLOBAL_CONFIG.get_user_config(username)

        # If that config is empty, terminate here
        if not self.config:
            raise ValueError(f"No profile exists for username '{username}'")

        # Try to synchronize the config's state with our own
        self._active_username = username
        self._data_path = self.config.last_used_data_path
        self._cohort_path = self.config.last_used_cohort_file
        self._task_id = self.config.last_used_task

    def get_available_usernames(self) -> list[str]:
        # Simple wrapper for our config
        return [str(x) for x in GLOBAL_CONFIG.profiles.keys()]

    def new_user_profile(self, username: str) -> UserConfig:
        """
        Attempts to create a new user w/ the provided username,
        using the previously active user's profile as reference.

        We also immediately change to this new profile to give the
        user some feedback
        """
        new_profile = GLOBAL_CONFIG.new_user_profile(username, self.config)
        self._load_user_state(username)
        return new_profile

    ## Cohort File Management ##
    @property
    def cohort_path(self) -> Path:
        return self._cohort_path

    @cohort_path.setter
    def cohort_path(self, new_path: Path):
        # Confirm the file exists
        if not new_path.exists():
            raise ValueError(f"Cohort file '{new_path}' does not exist!")

        # Confirm it is a CSV
        if new_path.suffix.lower() != ".csv":
            raise ValueError(f"Selected file '{new_path}' is not a `.csv` file!")

        # Warn the user if they're reloading the same file
        if self._cohort_path is not None and str(new_path.resolve()) == str(
                self._cohort_path.resolve()
        ):
            print("Warning: Reloaded the same cohort file!")

        # If all checks pass, update our state
        self._cohort_path = new_path
        self.clear_task()

        # Update the config to match
        self.config.last_used_cohort_file = new_path

    def load_cohort(self):
        """
        Load the contents of the currently selected cohort file into memory
        """
        # If we don't have a data manager yet, create one
        if self.data_manager is None:
            self.rebuild_data_manager()

        # Load the cases from the CSV into memory
        self.data_manager.load_cases()

    ## Data Path Management ##
    @property
    def data_path(self) -> Path:
        return self._data_path

    @data_path.setter
    def data_path(self, new_path: Path):
        # Confirm the directory exists
        if not new_path.exists():
            raise ValueError(f"Data path '{new_path}' does not exist!")

        # Confirm that it is a directory
        if not new_path.is_dir():
            raise ValueError(f"Data path '{new_path}' was not a directory!")

        # Warn the user if they're reloading the same file
        if self._data_path is not None and str(new_path.resolve()) == str(
                self._data_path.resolve()
        ):
            print("Warning: Selected the same data path!")

        # If that all ran, update our state
        self._data_path = new_path

        # Reset our state, as the task + data manager is likely no longer valid
        self.clear_task()
        self.rebuild_data_manager()

        # Update the config to match
        self.config.last_used_data_path = new_path

    ## Task Management ##
    @property
    def task_id(self) -> str:
        return self._task_id

    @task_id.setter
    def task_id(self, new_id: str):
        # Confirm that the ID isn't blank
        if not new_id:
            raise ValueError("Cannot assign to a blank task!")

        # Confirm that the task ID is in our task map
        task_type = self.task_map.get(new_id, None)
        if not task_type:
            raise ValueError(f"Task '{new_id}' hasn't been registered!")

        # Update our state
        self._task_id = new_id

        # Get this task's preferred DataUnitFactory method
        # TODO: Allow the user to select the specific method, rather than always
        #  using the first in the map
        data_factory_method_map = task_type.getDataUnitFactories()
        duf = list(data_factory_method_map.values())[0]

        # Update the data manager to use this task's preferred DataUnitFactory
        self.data_unit_factory = duf

        # New task selected means the old manager + task is no longer relevant
        self.rebuild_data_manager()
        self.clear_task()

        # Update the config state as well
        self.config.last_used_task = new_id

    @property
    def has_active_task(self) -> bool:
        # Wrapper property to avoid the need for syncing a bool
        return self.current_task_instance is not None

    def clear_task(self):
        """
        Clears the current task instance, ensuring its cleaned itself up before
        its removed from memory
        """
        if self.current_task_instance:
            self.current_task_instance.exit()
            self.current_task_instance.cleanup()
            self.current_task_instance = None

    def validate_cohort_and_data_path_match(self) -> Optional[str]:
        """
        Returns all errors between the cohort CSV file and the data path, if they exist. Else, returns None.
        """
        # If we don't have a data manager, create one
        if not self.data_manager:
            self.rebuild_data_manager()

        validation_result = self.data_manager.validate_cohort_and_data_path_match()
        if validation_result:
            return validation_result
        return None

    def is_ready(self) -> bool:
        """
        Check if we're ready to run a task!
        :return: True if so, False otherwise.
        """
        # We can't proceed if we don't have a selected user
        if not self.active_username:
            print("Missing a valid user!")
            return False
        # We can't proceed if a data path has not been specified
        elif not self.data_path:
            print("Missing a valid data path!")
            return False
        # We can't proceed if we're missing a cohort path
        elif not self.cohort_path:
            print("Missing a valid cohort path!")
            return False
        # We can't proceed if we don't have a selected task type
        elif not self.task_id:
            print("No task has been selected!")
            return False
        elif not self.data_unit_factory:
            print("No data unit factory has been selected!")
            return False

        # If all checks passed, we can proceed!a
        return True

    def init_task(self):
        """
        Initialize a new Task instance using current settings.

        The task will NOT receive a data unit at this point; that is deferred until after the GUI is built, in case
        the task needs to prompt the user for details which help determine if a given data unit is complete or not
        (i.e. output directories); see `CARTLogic:load_first_unit` for details.
        """
        # Safety gate: if we're not ready to start a task, return None
        if not self.is_ready():
            return

        # Rebuild our data manager
        self.rebuild_data_manager()

        # Load the cohort file into memory using the new DataManager
        self.load_cohort()

        # Ensure the current task has cleaned itself up.
        self.clear_task()

        # Create the new task instance
        task_constructor = self.task_map.get(self.task_id)
        self.current_task_instance = task_constructor(self.active_username)

        # Save any changes made to the configuration
        # (Usually saves the user and
        self.config.save_to_file()

        # Act as though CART has just been reloaded so the task can initialize
        #  properly
        self.enter()

    def load_initial_unit(self):
        """
        Attempts to load the first data unit into memory and update our task with it
        """
        # Pass our first data unit to the task
        data_unit = self.data_manager.first()
        # TODO: Add a configuration option for skipping to first incomplete unit
        # data_unit = self.data_manager.first_incomplete(self.current_task_instance)
        self.current_task_instance.receive(data_unit)

    def enter(self):
        """
        Called when the CART module is loaded (through our CARTWidget).

        Just signals to the current task that CART is now in view again, and it
        should synchronize its state to the MRML scene.
        """
        if self.current_task_instance:
            self.current_task_instance.enter()

    def exit(self):
        """
        Called when the CART module is un-loaded (through our CARTWidget).

        Just signals to the current task that CART is no longer in view, and it
        should pause any active processes in the GUI.
        """
        if self.current_task_instance:
            self.current_task_instance.exit()

    ## DataUnit Management ##
    @property
    def data_manager(self):
        return self._data_manager

    def rebuild_data_manager(self):
        # If we had a prior data manager, clean it up first
        if self.data_manager:
            self.data_manager.clean()

        # Build a new data manager with the current state
        self._data_manager = DataManager(
            cohort_file=self._cohort_path,
            data_source=self._data_path,
            data_unit_factory=self.data_unit_factory,
        )

    def current_uid(self):
        if self.data_manager:
            return self.data_manager.current_uid()
        # In the off chance where we don't have cases loaded, return none
        else:
            return ""

    def has_next_case(self):
        if self.data_manager:
            return self.data_manager.has_next_case()
        else:
            return False

    def has_previous_case(self):
        if self.data_manager:
            return self.data_manager.has_previous_case()
        else:
            return False

    def select_current_case(self) -> Optional[DataUnitBase]:
        """
        Select the current unit managed by the Data Manager, if we have one
        """
        # If we don't have a data manager yet, return none
        if not self.data_manager:
            return None

        # Otherwise, select the current data unit
        current_unit = self.data_manager.select_current_unit()

        # Pass it to the current task, so it can update anything it needs to
        self._update_task_with_new_case(current_unit)

        # Return it for further user
        return current_unit

    def next_case(self, skip_complete: bool = False) -> Optional[DataUnitBase]:
        """
        Try to step into the next case managed by the cohort, pulling it
        into memory if needed.

        :param skip_complete: Whether to skip over already completed cases

        :return: The next valid case. 'None' if no valid case could be found.
        """
        # Grab the next data unit
        if skip_complete:
            next_unit = self.data_manager.next_incomplete(self.current_task_instance)
        else:
            next_unit = self.data_manager.next()

        # Pass it to the current task, so it can update anything it needs to
        self._update_task_with_new_case(next_unit)

        # Return it; the data manager is self-managing, no need to do any further checks
        return next_unit

    def previous_case(self, skip_complete: bool = False):
        """
        Try to step into the previous case managed by the cohort, pulling it
        into memory if needed.

        :param skip_complete: Whether completed cases should be skipped over

        :return: The previous valid case. 'None' if no valid case could be found.
        """
        # Get the previous valid case
        if skip_complete:
            previous_case = self.data_manager.prior_incomplete(self.current_task_instance)
        else:
            previous_case = self.data_manager.previous()

        # Pass it to the current task, so it can update anything it needs to
        self._update_task_with_new_case(previous_case)

        # Return it; the data manager is self-managing, no need to do any further checks
        return previous_case

    def _update_task_with_new_case(self, new_case: DataUnitBase):
        # Only update the task if exists
        task = self.current_task_instance
        if not task:
            return

        # If autosaving is on, have the task save its current case before proceeding
        if self.config.save_on_iter:
            task.save_on_iter()

        # Have the task receive the new case
        task.receive(new_case)
