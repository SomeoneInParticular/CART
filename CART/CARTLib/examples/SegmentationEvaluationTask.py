import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import ctk
import qt
import slicer
from slicer.i18n import tr as _
from .SegmentationEvaluationDataUnit import SegmentationEvaluationDataUnit
from ..core.TaskBaseClass import TaskBaseClass, DataUnitFactory


VERSION = 0.01


class SegmentationEvaluationGUI:
    def __init__(self, bound_task: 'SegmentationEvaluationTask'):
        # Track the task, so we can reference it later
        self.bound_task = bound_task

        # Segmentation editor widget
        self.segmentEditorWidget = None

        # The manual "save" button; whether it is enabled/disabled depends on
        #  the current state of our bound task
        self.saveButton = None

    ## GUI CONSTRUCTION ##
    def setup(self) -> qt.QFormLayout:
        """
        Build the GUI's contents, returning the resulting layout for use
        """
        # Initialize the layout we'll insert everything into
        formLayout = qt.QFormLayout()

        # Add the output selection button
        self.addOutputSelectionButton(formLayout)

        # Add a panel w/ some configuration options
        self.addOptionsPanel(formLayout)

        # Add the segmentation editor widget
        self.addSegmentationEditor(formLayout)

        # Save button
        self.addSaveButton(formLayout)

        # Prompt the user for an output directory
        self.promptSelectOutput()

        return formLayout

    def addOutputSelectionButton(self, formLayout):
        # Create the save button
        outputChangeButton = qt.QPushButton("Change Output Directory")
        formLayout.addRow(outputChangeButton)
        outputChangeButton.clicked.connect(self.promptSelectOutput)

    def addOptionsPanel(self, formLayout):
        # Add a check-box for hiding segmentations on-load
        hideSegmentsOnLoadBox = qt.QCheckBox(_("Show Segmentations on Load"))

        # Synchronize it to our logic
        hideSegmentsOnLoadBox.setChecked(self.bound_task.show_segment_on_load)

        # When the checkbox changes state, update our logic to match
        def update_hide_segments():
            self.bound_task.show_segment_on_load = hideSegmentsOnLoadBox.isChecked()

        hideSegmentsOnLoadBox.stateChanged.connect(update_hide_segments)

        # Add it to the form layout
        formLayout.addRow(hideSegmentsOnLoadBox)

    def addSegmentationEditor(self, formLayout):
        # Build the editor widget
        # TODO: Fix this "stealing" from the original Segment Editor widget
        self.segmentEditorWidget = \
            slicer.modules.segmenteditor.widgetRepresentation().self().editor

        formLayout.addRow(self.segmentEditorWidget)

    def addSaveButton(self, formLayout):
        # Create the save button
        saveButton = qt.QPushButton("Save")
        formLayout.addRow(saveButton)
        saveButton.clicked.connect(self._save)
        self.saveButton = saveButton

    ## USER PROMPTS ##
    def promptSelectOutput(self):
        """
        Prompt the user to select an output directory.

        The prompt will validate that the chosen output directory is valid,
         and lock the save button if the user cancel's out of it without
         selecting such a directory.
        """
        # Initialize the prompt
        prompt = self._buildOutputDirPrompt()

        # Show the prompt with "exec", blocking the main window until resolved
        result = prompt.exec()

        # If the user cancelled out of the prompt, notify them that they will
        #  need to specify an output directory later!
        if result == 0:
            notif = qt.QErrorMessage()
            if self.bound_task.can_save():
                notif.setWindowTitle(_("REVERTING!"))
                notif.showMessage(_("Cancelled out of window; falling back to previous "
                                    "output directory "
                                    f"({str(self.bound_task.output_dir)})"))
                notif.exec()
            else:
                notif.setWindowTitle(_("NO OUTPUT!"))
                notif.showMessage(_("No output directory selected! You will need to "
                                    "specify this before segmentations can be saved."))
                notif.exec()

        # Update the save button to match the current saving capability
        self._updatedSaveButtonState()

    def _buildOutputDirPrompt(self):
        prompt = qt.QDialog()
        prompt.setWindowTitle("Select Output Directory")
        # Add a basic layout to hold widgets in this prompt
        layout = qt.QVBoxLayout()
        prompt.setLayout(layout)

        # Add a label describing what's being asked
        label = qt.QLabel("Please select an output directory:")
        layout.addWidget(label)

        # Add an output file selection widget
        outputFileEdit = ctk.ctkPathLineEdit()
        outputFileEdit.setToolTip(_(
            "The directory the modified segmentations (and corresponding "
            "metadata) will be placed."
        ))
        # Set the widget to only accept directories
        outputFileEdit.filters = ctk.ctkPathLineEdit.Dirs
        # Add it to our layout
        layout.addWidget(outputFileEdit)

        # Add a button box to confirm/cancel out
        buttonBox = qt.QDialogButtonBox()
        buttonBox.addButton(_("Confirm"), qt.QDialogButtonBox.AcceptRole)
        layout.addWidget(buttonBox)

        # When the user confirms, ensure we have a valid path first
        buttonBox.accepted.connect(
            lambda: self._attemptOutputPathUpdate(prompt, outputFileEdit)
        )

        # Resize the prompt to be wider, as by default its very tiny
        prompt.resize(500, prompt.minimumHeight)

        return prompt

    def _linkedPathErrorPrompt(self, err_msg, prompt):
        """
        Prompt the user with an error message
        """
        # Prompt the user with the error, locking the original prompt until
        #  acknowledged by the user
        failurePrompt = qt.QErrorMessage(prompt)

        # Add some details on what's happening for the user
        failurePrompt.setWindowTitle("PATH ERROR!")

        # Show the message
        failurePrompt.showMessage(err_msg)
        failurePrompt.exec()

    ## GUI SYNCHRONIZATION ##
    def _updatedSaveButtonState(self):
        # Ensure the button is active on when we're ready to save
        can_save = self.bound_task.can_save()
        self.saveButton.setEnabled(can_save)

        # Change the tooltip of the button to inform the user what's wrong

        if can_save:
            tooltip_text = _("Saves the current segmentation!")
        else:
            tooltip_text = _("Cannot save currently; no output directory set!")
        self.saveButton.setToolTip(tooltip_text)

    ## TASK LINKS ##
    def _attemptOutputPathUpdate(
            self,
            prompt: qt.QDialog,
            widget: ctk.ctkPathLineEdit
    ):
        """
        Validates the output path provided by a user, only closing the
         associated prompt if it was valid.
        """
        # Strip whitespace to avoid a "space" path
        output_path_str = widget.currentPath.strip()

        if not output_path_str:
            # Prompt the user with the error
            err_msg = "Output path was empty"
            self._linkedPathErrorPrompt(err_msg, prompt)

            # Reset it to our prior managed directory for convenience sakes
            widget.currentPath = str(self.bound_task.output_dir)

            # Return early, which keeps the prompt active
            return

        # Convert it to a Path for ease of use
        output_path = Path(output_path_str)

        # Otherwise, try to update the task's path; we rely on its validation
        #  to ensure parity with any other checks
        err_msg = self.bound_task.set_output_dir(output_path)

        # If we got an error message, prompt the user about why and return
        if err_msg:
            self._linkedPathErrorPrompt(err_msg, prompt)

            # Return, keeping the prompt alive
            return
        # Otherwise, close the prompt with an "accepted" signal
        else:
            prompt.accept()

    def update(self, data_unit: SegmentationEvaluationDataUnit):
        """
        Update the GUI to match the contents of the new data unit.

        Currently only selects the volume + segmentation node associated with
         the provided data node, allowing the user to immediately start editing.
        """
        # As the volume node is tied to the segmentation node, this will also
        #  set the selected volume node automagically for us!
        self.segmentEditorWidget.setSegmentationNode(data_unit.segmentation_node)

    def _save(self):
        """
        Wrapper for task saving, which just enables us to prompt the user
        on success/failure
        """
        # Attempt to save
        err_msg = self.bound_task.save()

        # If successful, prompt the user to acknowledge
        if err_msg is None:
            msgBox = qt.QMessageBox()
            msgBox.setWindowTitle("Success!")
            seg_out, __ = self.bound_task.output_manager.get_output_destinations(
                self.bound_task.data_unit
            )
            msgBox.setText(f"The segmentation for '{self.bound_task.data_unit.uid}' "
                           f"was successfully saved!\n\n"
                           f"Saved to: {str(seg_out.resolve())}!")
            msgBox.addButton(_("Confirm"), qt.QMessageBox.AcceptRole)
            msgBox.exec()
        else:
            errBox = qt.QErrorMessage()
            errBox.setWindowTitle("ERROR!")
            errBox.showMessage(err_msg)
            errBox.exec()

    def _update_hide_segments(self):
        self.bound_task.show_segment_on_load


class SegmentationEvaluationTask(TaskBaseClass[SegmentationEvaluationDataUnit]):
    def __init__(self, user: str):
        super().__init__(user)
        # Variable for tracking the active GUI instance
        self.gui: Optional[SegmentationEvaluationGUI] = None

        # Variable for tracking the output directory
        self.output_dir: Optional[Path] = None

        # Output manager to handling saving/loading of modified segmentations
        self.output_manager: _OutputManager = None

        # Placeholder to track the currently-in-use Data Unit
        self.data_unit: Optional[SegmentationEvaluationDataUnit] = None

        # Whether to show segmentations on load; by default, we do.
        self.show_segment_on_load = True

    def setup(self, container: qt.QWidget):
        print(f"Running {self.__class__.__name__} setup!")

        # Initialize the GUI instance for this task
        self.gui = SegmentationEvaluationGUI(self)

        # Build its GUI and install it into the container widget
        gui_layout = self.gui.setup()
        container.setLayout(gui_layout)

        # If we have GUI, update the GUI with our current data unit
        self.gui.update(self.data_unit)

    def receive(self, data_unit: SegmentationEvaluationDataUnit):
        # Track the data unit for later
        self.data_unit = data_unit

        # Bring the volume and associated segmentation into view again
        # TODO: Only do this if a GUI exists
        slicer.util.setSliceViewerLayers(
            background=self.data_unit.volume_node,
            foreground=self.data_unit.segmentation_node,
            label=self.data_unit.uid,
            fit=True
        )

        # Only show segmentations on-load if we're set to do so.
        self.set_segment_visibility(
            self.data_unit.segmentation_node,
            self.show_segment_on_load,
            0  # We only have 1 segment, making always in position 0
        )

        # If we have GUI, update it as well
        if self.gui:
            self.gui.update(self.data_unit)

    def cleanup(self):
        # Break the cyclical link with our GUI so garbage collection can run
        self.gui = None

    def save(self) -> Optional[str]:
        # Have the output manager save the result
        return self.output_manager.save_segmentation(self.data_unit)

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

    @classmethod
    def getDataUnitFactories(cls) -> dict[str, DataUnitFactory]:
        """
        We currently only support one data unit type, so we only provide it to
         the user
        """
        return {
            "Single Segmentation": SegmentationEvaluationDataUnit
        }

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

        # Create a new output manager with this directory
        self.output_manager = _OutputManager(self.output_dir, self.user)

        return None

    @staticmethod
    def set_segment_visibility(segmentation_node, state: bool, idx: int = 0):
        """
        As a "segment" within a SegmentationNode isn't a node, using
        `SetSegmentVisibility` on it directly will not work. Instead, we need
        to get the SegmentationNode's DisplayNode, and tell it to change the
        visibility of the segment. Rather roundabout, but this properly
        synchronizes everything with the GUI (and, more importantly, ensures
        our Segment Editor GUI can toggle the segment's visibility as well).

        :param segmentation_node: The segmentation node to user
        :param state: The new visibility state to put the segment into
        :param idx: The segment's "index"; by default, we assume there is always
            at least one segment in the node, the first (0-index).

        TODO: Make this a shared utility
        """
        segment_data = segmentation_node.GetSegmentation()
        segment_id = segment_data.GetNthSegmentID(idx)
        segmentation_node.GetDisplayNode().SetSegmentVisibility(segment_id, state)


class _OutputManager:
    """
    Manages the output of the Segmentation Evaluation task
    """
    def __init__(self, output_dir: Path, user: str):
        self.output_dir = output_dir
        self.user = user

    def save_segmentation(self, data_unit: SegmentationEvaluationDataUnit) \
            -> Optional[str]:
        # Calculate the designation paths for our files
        segmentation_out, sidecar_out = self.get_output_destinations(data_unit)

        # Create the directories needed for these outputs
        segmentation_out.parent.mkdir(parents=True, exist_ok=True)
        sidecar_out.parent.mkdir(parents=True, exist_ok=True)

        # Attempt to save our results
        try:
            # Save the node
            self._save_segmentation_node(
                data_unit.segmentation_node, data_unit.volume_node, segmentation_out
            )

            # Save/update the side-car file, if it exists
            self._save_sidecar(
                data_unit, sidecar_out
            )

            # Return nothing, indicating a successful save
            return None
        except Exception as e:
            # If any error occurred, return a string version of it for reporting
            return str(e)

    def get_output_destinations(self, data_unit: SegmentationEvaluationDataUnit) -> \
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

    def _save_segmentation_node(self, seg_node, volume_node, target_file):
        """
        Save a segmentation node's contents to file; this gets its own utility
         function because you can't do so directly. Instead, you need to convert
         it back to a label-type node w/ reference to a volume node first, then
         save it.
        """
        # Convert the Segmentation back to a Label (for Nifti export)
        label_node = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLLabelMapVolumeNode"
        )
        slicer.modules.segmentations.logic().ExportVisibleSegmentsToLabelmapNode(
            seg_node, label_node, volume_node
        )

        # Save the active segmentation node to this directory
        slicer.util.saveNode(label_node, str(target_file))

        # Clean up the node after so it doesn't pollute the scene
        slicer.mrmlScene.RemoveNode(label_node)

    def _save_sidecar(self, data_node, target_file: Path):
        # Check for an existing sidecar, and use it as our basis if it exists
        fname = str(data_node.segmentation_path).split('.')[0]

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
