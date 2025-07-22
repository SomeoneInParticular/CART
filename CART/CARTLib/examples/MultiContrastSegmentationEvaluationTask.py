import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import ctk
import qt
import slicer
from slicer.i18n import tr as _
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import ctk
import qt
import slicer
from slicer.i18n import tr as _
from .MultiContrastSegmentationEvaluationDataUnit import MultiContrastSegmentationEvaluationDataUnit
from ..core.TaskBaseClass import TaskBaseClass, DataUnitFactory
from ..utils.widgets import CARTSegmentationEditorWidget
from ..utils.data import save_segmentation_to_nifti, save_volume_to_nifti
from ..LayoutLogic import CaseIteratorLayoutLogic


VERSION = 0.01

class MultiContrastSegmentationEvaluationGUI:
    def __init__(self, bound_task: 'MultiContrastSegmentationEvaluationTask'):
        self.bound_task = bound_task
        self.data_unit: Optional[MultiContrastSegmentationEvaluationDataUnit] = None

        # Layout logic for creating linked slice views
        self.layoutLogic = CaseIteratorLayoutLogic()
        self.currentOrientation: str = 'Axial'

        # Widgets we’ll need to reference later:
        self.segmentEditorWidget: Optional[CARTSegmentationEditorWidget] = None
        self.saveButton: Optional[qt.QPushButton] = None
        # self.volumeCombo: Optional[qt.QComboBox] = None

    def setup(self) -> qt.QFormLayout:
        """
        Build the GUI's contents, returning the resulting layout for use
        """
        # Initialize the layout we'll insert everything into
        formLayout = qt.QFormLayout()


        # 2) Orientation buttons
        self._addOrientationButtons(formLayout)

        # 3) Segmentation editor
        self.segmentEditorWidget = CARTSegmentationEditorWidget()
        formLayout.addRow(self.segmentEditorWidget)

        # 4) Save controls
        # self._addOutputSelectionButton(formLayout)
        # self._addSaveButton(formLayout)
        # self.promptSelectOutput()

        return formLayout

    def _addOrientationButtons(self, layout: qt.QFormLayout) -> None:
        """
        Buttons to set Axial/Sagittal/Coronal for all slice views.
        """
        hbox = qt.QHBoxLayout()
        for name in ("Axial", "Sagittal", "Coronal"):
            btn = qt.QPushButton(name)
            btn.clicked.connect(lambda _, o=name: self.onOrientationChanged(o))
            hbox.addWidget(btn)
        layout.addRow(qt.QLabel("View Orientation:"), hbox)


    def onOrientationChanged(self, orientation: str) -> None:
        self.currentOrientation = orientation
        if not self.data_unit:
            return
        # recreate layout with new orientation
        self.layoutLogic.create_linked_slice_views(
            volume_nodes=list(self.data_unit.volume_nodes.values()),
            label=self.data_unit.segmentation_node,
            orientation=self.currentOrientation
        )

    # def _addOutputSelectionButton(self, layout: qt.QFormLayout) -> None:
    #     btn = qt.QPushButton("Change Output Directory")
    #     btn.clicked.connect(self.promptSelectOutput)
    #     layout.addRow(btn)

    # def _addSaveButton(self, layout: qt.QFormLayout) -> None:
    #     btn = qt.QPushButton("Save")
    #     btn.clicked.connect(self._save)
    #     layout.addRow(btn)
    #     self.saveButton = btn

    def update(self, data_unit: MultiContrastSegmentationEvaluationDataUnit) -> None:
        self.data_unit = data_unit
        # update combo
        # self.volumeCombo.clear()
        # for key in data_unit.volume_keys:
        #     self.volumeCombo.addItem(key)
        # initial orientation layout for all volumes
        self.layoutLogic.create_linked_slice_views(
            volume_nodes=list(data_unit.volume_nodes.values()),
            label=data_unit.segmentation_node,
            orientation=self.currentOrientation
        )
        # sync segmentation editor
        self.segmentEditorWidget.setSegmentationNode(data_unit.segmentation_node)
        # self._updatedSaveButtonState()


    def saveCompletePrompt(self, err_msg: Optional[str]) -> None:
        if err_msg is None:
            msg = qt.QMessageBox()
            msg.setWindowTitle("Success!")
            seg_out, _ = self.bound_task.output_manager.get_output_destinations(
                self.bound_task.data_unit
            )
            msg.setText(
                f"Segmentation '{self.bound_task.data_unit.uid}' saved to:\n{seg_out.resolve()}"
            )
            msg.addButton(_("Confirm"), qt.QMessageBox.AcceptRole)
            msg.exec()
        else:
            errBox = qt.QErrorMessage()
            errBox.setWindowTitle("ERROR!")
            errBox.showMessage(err_msg)
            errBox.exec()

    ## GUI SYNCHRONIZATION ##
    def enter(self) -> None:
        # Ensure the segmentation editor widget it set up correctly
        if self.segmentEditorWidget:
            self.segmentEditorWidget.enter()

    def exit(self) -> None:
        # Ensure the segmentation editor widget handles itself before hiding
        if self.segmentEditorWidget:
            self.segmentEditorWidget.exit()

    def _updatedSaveButtonState(self) -> None:
        # Ensure the button is active on when we're ready to save
        can_save = self.bound_task.can_save()
        self.saveButton.setEnabled(can_save)
        tip = _("Saves the current segmentation!") if can_save \
              else _("Cannot save: no valid output directory.")
        self.saveButton.setToolTip(tip)

class MultiContrastSegmentationEvaluationTask(TaskBaseClass[MultiContrastSegmentationEvaluationDataUnit]):
    def __init__(self, user: str):
        super().__init__(user)
        self.gui: Optional[MultiContrastSegmentationEvaluationGUI] = None
        self.output_dir: Optional[Path] = None
        self.output_manager: Optional[_MultiContrastOutputManager] = None
        self.data_unit: Optional[MultiContrastSegmentationEvaluationDataUnit] = None

    def setup(self, container: qt.QWidget) -> None:
        print(f"Running {self.__class__.__name__} setup!")
        self.gui = MultiContrastSegmentationEvaluationGUI(self)
        layout = self.gui.setup()
        container.setLayout(layout)
        if self.data_unit:
            self.gui.update(self.data_unit)
        self.gui.enter()

    def receive(self, data_unit: MultiContrastSegmentationEvaluationDataUnit) -> None:
        # Track the data unit for later
        self.data_unit = data_unit
        # Display primary volume + segmentation overlay
        slicer.util.setSliceViewerLayers(
            background=data_unit.primary_volume_node,
            foreground=data_unit.segmentation_node,
            fit=True
        )
        # If we have GUI, update it as well
        if self.gui:
            self.gui.update(data_unit)

    def cleanup(self) -> None:
        # Break the cyclical link with our GUI so garbage collection can run
        self.gui = None

    def save(self) -> Optional[str]:
        if self.can_save():
            return self.output_manager.save_segmentation(self.data_unit)
        return None

    def can_save(self) -> bool:
        """
        Shortcut for checking whether we can save the current segmentation or
         not. Checks three things:
        * We have set an output path,
        * That output path exists, and
        * That output path is a directory (and thus, files can be placed within it)
        :return: True if we are ready to save, false otherwise
        """
        return self.output_dir and self.output_dir.exists() and self.output_dir.is_dir()

    def autosave(self) -> Optional[str]:
        result = super().autosave()
        if self.gui:
            self.gui.saveCompletePrompt(result)

    def enter(self) -> None:
        if self.gui:
            self.gui.enter()

    def exit(self) -> None:
        if self.gui:
            self.gui.exit()

    @classmethod
    def getDataUnitFactories(cls) -> dict[str, DataUnitFactory]:
        """
        We currently only support one data unit type, so we only provide it to
         the user
        """
        return {"Segmentation": MultiContrastSegmentationEvaluationDataUnit}

    ## Utils ##
    def set_output_dir(self, new_path: Path) -> Optional[str]:
        """
        Update the output directory; returns an error message if it failed!
        """
        # Confirm the directory exists
        if not new_path.exists():
            err = f"Error: Data path does not exist: {new_path}"
            return err

        # Confirm that it is a directory
        if not new_path.is_dir():
            err = f"Error: Data path was not a directory: {new_path}"
            return err

        # If that all ran, update our data path to the new data path
        self.output_dir = new_path
        print(f"Output path set to: {self.output_dir}")
        self.output_manager = _MultiContrastOutputManager(self.output_dir, self.user)
        return None


class _MultiContrastOutputManager:
    # TODO Make this more general as it is nearly identical to the original "OutputManager"
    def __init__(self, output_dir: Path, user: str):
        self.output_dir = output_dir
        self.user = user

    def save_segmentation(self, data_unit: MultiContrastSegmentationEvaluationDataUnit) \
            -> Optional[str]:
        # Calculate the designation paths for our files
        segmentation_out, sidecar_out = self.get_output_destinations(data_unit)

        # Create the directories needed for these outputs
        segmentation_out.parent.mkdir(parents=True, exist_ok=True)
        sidecar_out.parent.mkdir(parents=True, exist_ok=True)

        # Attempt to save our results
        try:
            # Save the node
            self._save_segmentation(data_unit, segmentation_out)

            # Save/update the side-car file, if it exists
            self._save_sidecar(data_unit, sidecar_out)

            # Return nothing, indicating a successful save
            return None
        except Exception as e:
            # If any error occurred, return a string version of it for reporting
            return str(e)

    def get_output_destinations(self, data_unit: MultiContrastSegmentationEvaluationDataUnit) -> \
            (Path, Path):
        """
        Get the output paths for the files managed by this manager
        :param data_unit: The data unit whose data will be saved
        :return: Two paths, one per output file:
            * The path to the (.nii.gz) segmentation file
            * The path to the (.json) sidecar file, corresponding to the prior
        """
        # Define the "target" output directory
        target_dir = self.output_dir / f"{data_unit.uid}/anat/"

        # File name, before extensions
        fname = f"{data_unit.uid}_{self.user}_seg"

        # Define the target output file placement
        segmentation_out = target_dir / f"{fname}.nii.gz"

        # Define the path for our side-care
        sidecar_out = target_dir / f"{fname}.json"

        return segmentation_out, sidecar_out

    @staticmethod
    def _save_segmentation(
            data_unit: MultiContrastSegmentationEvaluationDataUnit,
            target_file: Path
    ):
        """
        Save the data unit's currently tracked segmentation to the designated
        output
        """
        # Extract the relevant node data from the data unit
        seg_node = data_unit.segmentation_node
        vol_node = data_unit.primary_volume_node # THIS IS THE MAIN DIFFERENCE BETWEEN THIS MULTICONTRAST OUTPUT MANAGER
        # AND THE ORIGINAL OUTPUT MANAGER

        # Try to save the segmenattion using them
        save_segmentation_to_nifti(seg_node, vol_node, target_file)

    def _save_sidecar(
            self,
            data_unit: MultiContrastSegmentationEvaluationDataUnit,
            target_file: Path
    ):
        # Check for an existing sidecar, and use it as our basis if it exists
        fname = str(data_unit.segmentation_path).split('.')[0]

        # Read in the existing side-car file first, if possible
        sidecar_file = Path(f"{fname}.json")
        if sidecar_file.exists():
            with open(sidecar_file, 'r') as fp:
                sidecar_data = json.load(fp)
        else:
            sidecar_data = dict()

        # New entry
        entry_time = datetime.now()
        new_entry = {
            "Name": "Segmentation Review [CART]",
            "Author": self.user,
            "Version": VERSION,
            "Date": entry_time.strftime('%Y-%m-%d %H:%M:%S')
        }

        # Add a new entry to the side-car's contents
        generated_by = sidecar_data.get("GeneratedBy", [])
        generated_by.append(new_entry)
        sidecar_data["GeneratedBy"] = generated_by

        # Write the sidecar file to our target file
        with open(target_file, 'w') as fp:
            json.dump(sidecar_data, fp, indent=2)
