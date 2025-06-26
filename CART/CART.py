import logging
import os
from typing import Annotated, Optional
from CARTLib.VolumeOnlyDataIO import VolumeOnlyDataUnit


import vtk
import ctk
import qt
from pathlib import Path
import slicer
from slicer.i18n import tr as _
from slicer.i18n import translate
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
from slicer.parameterNodeWrapper import (
    parameterNodeWrapper,
    WithinRange,
)

from slicer import vtkMRMLScalarVolumeNode


#
# CART
#


class CART(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = _("CART")  # TODO: make this more human readable by adding spaces
        # TODO: set categories (folders where the module shows up in the module selector)
        self.parent.categories = [translate("qSlicerAbstractCoreModule", "Examples")]
        self.parent.dependencies = []  # TODO: add here list of module names that this module requires
        self.parent.contributors = ["John Doe (AnyWare Corp.)"]  # TODO: replace with "Firstname Lastname (Organization)"
        # TODO: update with short description of the module and a link to online module documentation
        # _() function marks text as translatable to other languages
        self.parent.helpText = _("""
This is an example of scripted loadable module bundled in an extension.
See more information in <a href="https://github.com/organization/projectname#CART">module documentation</a>.
""")
        # TODO: replace with organization, grant and thanks
        self.parent.acknowledgementText = _("""
This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc., Andras Lasso, PerkLab,
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
""")

        # Additional initialization step after application startup is complete




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

    ## Initialization ##

    def __init__(self, parent=None) -> None:
        """Called when the user opens the module the first time and the widget is initialized."""
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)  # needed for parameter node observation
        self.logic = None

    def setup(self) -> None:
        """Called when the user opens the module the first time and the widget is initialized."""
        ScriptedLoadableModuleWidget.setup(self)

        # User UI
        self.userUIWidget = self.buildUserUI()
        # self.userUIWidget.setMRMLScene(slicer.mrmlScene)
        self.layout.addWidget(self.userUIWidget)

        # Cohort UI
        self.cohortUIWidget = self.buildCohortUI()
        self.layout.addWidget(self.cohortUIWidget)

        # Case Iterator UI
        self.caseIteratorUI = self.buildCaseIteratorUI()
        self.layout.addWidget(self.caseIteratorUI)

        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = CARTLogic()

        # Connections

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

        self.base_path = Path("/Users/iejohnson/NAMIC/CART/sample_data")
        # Set the base path for data storage
        hardcoded_dict = {
            "uid": "TEST_UID",
            "T2W": self.base_path / "11188/11188_1001211_t2w.nrrd",
            "HBV": self.base_path /  "11188/11188_1001211_hbv.nrrd",
            "ADC": self.base_path / "11188/11188_1001211_adc.nrrd",
        }

        try:
            du = VolumeOnlyDataUnit(
                hardcoded_dict
            )
            print("YAY! DataUnit created successfully")
            print(du)

        except Exception as e:
            logging.error("*" *100)
            logging.error(e)
            logging.error("*" *100)

    ## GUI builders ##

    def buildUserUI(self):
        """
        Builds the GUI for the user management section of the Widget
        :return:
        """
        # Layout management
        userCollapsibleButton = ctk.ctkCollapsibleButton()
        userCollapsibleButton.text = _("User Selection")
        formLayout = qt.QFormLayout(userCollapsibleButton)

        # User entry
        newUserHBox = qt.QHBoxLayout()
        newUserTextWidget = qt.QLineEdit()
        newUserTextWidget.toolTip = _("Your name, or an equivalent identifier")
        newUserHBox.addWidget(newUserTextWidget)
        formLayout.addRow(_("New User:"), newUserHBox)

        # When the user confirms their entry (with enter), add it to the
        #  prior users list
        newUserTextWidget.returnPressed.connect(self.newUserEntered)

        # Make it accessible
        self.newUserTextWidget = newUserTextWidget

        # Prior users list
        priorUsersCollapsibleButton = qt.QComboBox()
        priorUsersCollapsibleButton.placeholderText = _("[Not Selected]")
        # TODO Make this list dynamically loaded from a config/manifest
        priorUsersCollapsibleButton.addItems(["Kalum", "Kuan", "Ivan"])
        formLayout.addRow(_("Prior User"), priorUsersCollapsibleButton)

        # When the user selects an existing entry, update the program to match
        priorUsersCollapsibleButton.currentIndexChanged.connect(self.userSelected)

        # Make it accessible
        self.priorUsersCollapsibleButton = priorUsersCollapsibleButton

        return userCollapsibleButton

    def buildCohortUI(self):
        # Layout management
        cohortCollapsibleButton = ctk.ctkCollapsibleButton()
        cohortCollapsibleButton.text = _("Cohort Selection")
        formLayout = qt.QFormLayout(cohortCollapsibleButton)

        # Directory selection button
        cohortFileSelectionButton = ctk.ctkPathLineEdit()
        # TODO Fix/ Ensure this works as expected
        # Set file filters to only show readable file types
        cohortFileSelectionButton.filters = ctk.ctkPathLineEdit.Files
        cohortFileSelectionButton.nameFilters = [
            "CSV files (*.csv)",
        ]

        # Optionally set a default filter
        # TODO

        formLayout.addRow(_("Cohort File:"), cohortFileSelectionButton)

        # When the cohort selects a directory, update everything to match
        cohortFileSelectionButton.currentPathChanged.connect(self.onCohortChanged)

        # Make the button easy-to-access
        self.cohortFileSelectionButton = cohortFileSelectionButton

        return cohortCollapsibleButton

    def buildCaseIteratorUI(self):
        # Layout
        groupBox = qt.QGroupBox("Iteration Manager")
        layout = qt.QHBoxLayout(groupBox)

        # Hide this by default, only showing it when we're ready to iterate
        groupBox.setEnabled(False)

        # Next + previous buttons
        previousButton = qt.QPushButton(_("Previous"))
        previousButton.toolTip = _("Return to the previous case.")

        nextButton = qt.QPushButton(_("Next"))
        nextButton.toolTip = _("Move onto the next case.")

        # Add them to the layout "backwards" so previous is on the left
        layout.addWidget(previousButton)
        layout.addWidget(nextButton)

        # Connections
        nextButton.clicked.connect(self.nextCase)
        previousButton.clicked.connect(self.previousCase)

        # Make the buttons easy-to-access
        self.nextButton = nextButton
        self.previousButton = previousButton

        return groupBox


    ## Connected Functions ##

    def newUserEntered(self):
        # TODO: Connect functionality
        print(f"NEW USER: {self.newUserTextWidget.text}")
        self.newUserTextWidget.text = ""

        # Show the hidden parts of the GUI if we're ready to proceed
        self.checkIteratorReady()

    def userSelected(self):
        index = self.priorUsersCollapsibleButton.currentIndex
        text = self.priorUsersCollapsibleButton.currentText
        print(f"User selected: {text} ({index})")

    def onCohortChanged(self):
        """
        Runs when a new cohort CSV is selected.

        Currently only run when the Cohort button finishes selecting
         a directory
        """
        # TMP: Print the selected directory to console
        print(self.cohortFileSelectionButton.currentPath)

        # Show the hidden parts of the GUI if we're ready to proceed
        self.checkIteratorReady()

    def checkIteratorReady(self):
        # If there is a specified user
        if self.priorUsersCollapsibleButton.currentIndex != -1:
            # If there is a valid cohort
            if self.cohortFileSelectionButton.currentPath != "":
                self.caseIteratorUI.setEnabled(True)

    def nextCase(self):
        # TODO: Implement something here
        print("NEXT CASE!")
        self.nextButton.setEnabled(False)
        self.previousButton.setEnabled(True)

    def previousCase(self):
        # TODO: Implement something here
        print("PREVIOUS CASE!")
        self.nextButton.setEnabled(True)
        self.previousButton.setEnabled(False)

    ## Management ##

    def cleanup(self) -> None:
        """Called when the application closes and the module widget is destroyed."""
        pass

    def onSceneStartClose(self, caller, event) -> None:
        """Called just before the scene is closed."""
        pass

    def onSceneEndClose(self, caller, event) -> None:
        """Called just after the scene is closed."""
        pass


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


