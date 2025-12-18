from pathlib import Path
from typing import TYPE_CHECKING

import qt
from slicer.i18n import tr as _

from CARTLib.utils.widgets import CohortTableModel, CohortTableWidget


if TYPE_CHECKING:
    import numpy.typing as npt
    # Try to use a reference PyQT5 install if it's available
    import PyQt5.Qt as qt


class CohortEditorDialog(qt.QDialog):
    """
    GUI Dialog for editing a given cohort file.

    Can search for files associated with each case based on a search bar,
    allowing for automated creation of the table columns.

    Alternatively, the user can manually add, remove, edit the rows/columns
    within the table widget itself.
    """
    def __init__(
        self,
        csv_path: Path,
        parent: qt.QObject = None,
    ):
        super().__init__(parent)

        # Backing IO Manager
        self._io = CohortIO(csv_path)

        # Initial setup
        self.setWindowTitle(_("Cohort Editor"))
        self.setMinimumSize(900, 700)
        layout = qt.QVBoxLayout(self)

        # Main table widget
        cohortWidget = CohortTableWidget(self._io.model)
        cohortWidget.setFrameShape(qt.QFrame.Panel)
        cohortWidget.setFrameShadow(qt.QFrame.Sunken)
        cohortWidget.setLineWidth(3)
        layout.addWidget(cohortWidget)

        # Ok/Cancel Buttons
        buttonBox = qt.QDialogButtonBox()
        buttonBox.setStandardButtons(
            qt.QDialogButtonBox.Ok | qt.QDialogButtonBox.Cancel
        )
        def onButtonClicked(button: qt.QPushButton):
            button_role = buttonBox.buttonRole(button)
            if button_role == qt.QDialogButtonBox.RejectRole:
                self.reject()
            elif button_role == qt.QDialogButtonBox.AcceptRole:
                self.accept()
            else:
                raise ValueError("Pressed a button with an invalid role!")
        buttonBox.clicked.connect(onButtonClicked)
        layout.addWidget(buttonBox)


class CohortIO:
    def __init__(self, csv_path: Path, save_sidecar: bool = True):
        # Tracker for the model tracking the CSV data
        self._model: CohortTableModel = CohortTableModel(csv_path)

        # JSON sidecar management
        self.save_sidecar = save_sidecar
        self._sidecar_path: Path = csv_path.with_stem(".json")
        self._sidecar_data: dict = dict()

    @property
    def model(self) -> CohortTableModel:
        # Get-only to avoid desync
        return self._model

    @property
    def csv_path(self) -> Path:
        return self._model.csv_path

    @csv_path.setter
    def csv_path(self, new_path: Path):
        self._model.csv_path = new_path
        self._sidecar_path = new_path.with_stem(".json")
        self._sidecar_data = dict()

    @property
    def sidecar_path(self) -> Path:
        # Get-only to avoid desync
        return self._sidecar_path

    @property
    def sidecar_data(self) -> dict:
        # Get only to avoid desync
        return self._sidecar_data