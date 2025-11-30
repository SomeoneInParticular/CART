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

from CARTLib.core.DataManager import DataManager
from CARTLib.core.TaskBaseClass import TaskBaseClass, DataUnitFactory
from CARTLib.utils.config import GLOBAL_CONFIG, ProfileConfig, GLOBAL_CONFIG_PATH
from CARTLib.utils.task import CART_TASK_REGISTRY, initialize_tasks

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
        GLOBAL_CONFIG.load_from_json()

        # Add CARTLib to the Python Path for ease of (re-)use
        import sys

        cartlib_path = (Path(__file__) / "CARTLib").resolve()
        sys.path.append(str(cartlib_path))

        # Register all tasks currently configured in our CART Config
        initialize_tasks()


#
# CARTWidget
#
class CARTWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    def __init__(self, parent=None) -> None:
        """
        Called when the module is initialized by Slicer
        """
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)

        # Initialize our logic instance
        self.logic: CARTLogic = CARTLogic()

        # "Dummy" widget, in which the Task GUI will be placed
        self.taskWidget: qt.QWidget = None

        # Start button; fallback to start CART setup if the user backs out
        self.setupWidgetsGroup: ctk.ctkCollapsibleGroupBox = None
        self.startButton: qt.QPushButton = None

    def setup(self) -> None:
        """
        Called when the user opens the CART module within Slicer for the first time.
        """
        ScriptedLoadableModuleWidget.setup(self)

        # Dropdown to contain setup widgets, so they can be hidden once we're done
        setupWidgetsGroup = ctk.ctkCollapsibleGroupBox()
        setupWidgetsGroup.setTitle(_("Job Setup"))
        layout = qt.QFormLayout()
        setupWidgetsGroup.setLayout(layout)

        # A button to manually start (or change) a CART job
        if GLOBAL_CONFIG_PATH.exists():
            button_text = _("Start/Resume Job")
        else:
            button_text = _("Set Up CART")
        startButton = qt.QPushButton(button_text)
        startButton.clicked.connect(self.startButtonPressed)
        layout.addWidget(startButton)

        # Track everything for later
        self.setupWidgetsGroup = setupWidgetsGroup
        self.startButton = startButton

        # Add it to our overall GUI
        self.layout.addWidget(self.setupWidgetsGroup)

    ## Connections ##
    def startButtonPressed(self):
        # Immediately prompt the user to start a CART job
        if not GLOBAL_CONFIG_PATH.exists():
            self.setupPrompt()
        else:
            self.resumePrompt()

    ## User Prompts ##
    def setupPrompt(self):
        response = qt.QMessageBox.question(
            None,
            _("Initialize CART?"),
            _("CART has not been run before. Would you like to do so now?"),
            qt.QMessageBox.Yes | qt.QMessageBox.No,
            qt.QMessageBox.Yes
        )

        if response == qt.QMessageBox.Yes:
            print("+" * 100)
        else:
            print("-" * 100)

    def resumePrompt(self):
        response = qt.QMessageBox.question(
            None,
            _("Resume?"),
            _("Would you like to resume the last job you ran within CART?"),
            qt.QMessageBox.Yes | qt.QMessageBox.No,
            qt.QMessageBox.Yes
        )

        if response == qt.QMessageBox.Yes:
            print("+" * 100)
        else:
            print("-" * 100)

    ## View Management ##
    def cleanup(self) -> None:
        """
        Called when the application closes and this widget is about to be destroyed.
        """
        pass

    def enter(self):
        # Delegate to our logic to have tasks properly update
        self.logic.enter()

    def exit(self):
        # Delegate to our logic to have tasks properly update
        self.logic.exit()

#
# CARTLogic
#
class CARTLogic(ScriptedLoadableModuleLogic):

    def __init__(self):
        ScriptedLoadableModuleLogic.__init__(self)

        # Attribute declaration
        self.job_config: Optional[ProfileConfig] = None
        self._data_manager: Optional[DataManager] = None
        self._task_instance: Optional[TaskBaseClass] = None
        self._data_unit_factory: Optional[DataUnitFactory] = None

    def enter(self):
        """
        Called when the CART module is loaded (through our CARTWidget).

        Just signals to the current task that CART is now in view again, and it
        should synchronize its state to the MRML scene. This can include:
          * Installing any shortcuts
          * Restoring any active processes
          * Re-synchronizing with the MRML scene
        """
        if self._task_instance:
            self._task_instance.enter()

    def exit(self):
        """
        Called when the CART module is un-loaded (through our CARTWidget).

        Just signals to the current task that CART is no longer in view, and it
        should pause any active processes in the GUI. This can include:
          * Uninstalling any shortcuts
          * Pausing/killing any active processes
        """
        if self._task_instance:
            self._task_instance.exit()


