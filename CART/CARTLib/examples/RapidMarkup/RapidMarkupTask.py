from pathlib import Path
from typing import Optional

import qt
import slicer
from CARTLib.core.TaskBaseClass import TaskBaseClass, DataUnitFactory
from CARTLib.utils.config import ProfileConfig
from CARTLib.utils.task import cart_task
from slicer.i18n import tr as _

from RapidMarkupConfig import RapidMarkupConfig
from RapidMarkupGUI import RapidMarkupGUI, RapidMarkupSetupPrompt
from RapidMarkupOutputManager import RapidMarkupOutputManager
from RapidMarkupUnit import RapidMarkupUnit


@cart_task("Rapid Markup")
class RapidMarkupTask(TaskBaseClass[RapidMarkupUnit]):
    def __init__(self, profile: ProfileConfig):
        super().__init__(profile)

        # GUI and data
        self.gui: Optional[RapidMarkupGUI] = None
        self.data_unit: Optional[RapidMarkupUnit] = None

        # Annotation tracking
        self.markup_labels: list[str] = []
        # None -> nothing done, True -> has been placed, False -> has been skipped
        self.markup_placed: list[Optional[bool]] = []

        # Output management
        self._output_dir: Optional[Path] = None
        self._output_manager: Optional[RapidMarkupOutputManager] = None

        # Config management
        self.config = RapidMarkupConfig(parent_config=self.profile)

    def setup(self, container: qt.QWidget) -> None:
        print(f"Running {self.__class__.__name__} setup!")

        if self.config.last_used_output and self.config.last_used_markups:
            if slicer.util.confirmYesNoDisplay(
                "A previous run of this task was found; would you like to load it?"
            ):
                self.markup_labels = self.config.last_used_markups
                self.markup_placed = [None for _ in self.markup_labels]
                self.output_dir = self.config.last_used_output

        if self.output_dir is None:
            # Prompt the user with the setup GUI
            prompt = RapidMarkupSetupPrompt(self)
            setup_successful = prompt.exec()

            # If the setup failed, error out to prevent further task init
            if not setup_successful:
                raise AssertionError(
                    f"Failed to set up for {self.__class__.__name__}")

            self.output_dir = prompt.get_output()

        if self.output_dir is None:
            raise ValueError("Cannot initialize task without an output directory!")

        # Initialize our GUI
        self.gui = RapidMarkupGUI(self)
        layout = self.gui.setup()

        # Insert it into CART's GUI
        container.setLayout(layout)

        # If we have a data unit at this point, synchronize the GUI to it
        if self.data_unit:
            self.gui.update(self.data_unit)

        # Enter the GUI
        self.gui.enter()

        # Build the output manager
        self._output_manager = None

        # Update our config with this annotation set and save it
        self.config.last_used_markups = self.markup_labels
        self.config.last_used_output = self.output_dir
        self.config.save()

    ## Properties
    @property
    def output_dir(self) -> Path:
        return self._output_dir

    @output_dir.setter
    def output_dir(self, new_path: Path):
        """
        Made this a property to ensure that it isn't overridden by an
        invalid directory; also notifies the user that this occurred
        (via GUI prompt if available) so that they can respond
        appropriately
        """
        # If the path exists and is valid, set it and end
        if new_path and new_path.exists() and new_path.is_dir():
            self._output_dir = new_path
            self._output_manager = None
            return
        # Otherwise, update the user so that they may respond appropriately
        self.on_bad_output()

    @property
    def output_manager(self):
        # If the output manager hasn't been generated yet or was reset,
        # and we have an output directory, create a new one
        if not self._output_manager:
            self._output_manager = RapidMarkupOutputManager(
                self.profile,
                self.output_dir
            )

        return self._output_manager

    ## Unit Management ##
    def add_markup_at(self, idx: int, new_label: str):
        self.markup_labels.insert(idx, new_label)
        self.markup_placed.insert(idx, None)

        # Update the config to match
        self.config.last_used_markups = self.markup_labels

    def remove_markup_at(self, idx: int):
        del self.markup_labels[idx]
        del self.markup_placed[idx]

        # Update the config to match
        self.config.last_used_markups = self.markup_labels

    def update_on_new_markup(self, idx: int):
        """
        Updates the reference to the control point ("markup") at
        the specified index to match the attributes of the most
        newly placed control point.

        If no associated control point exists for the index yet,
        it will just update the new control point's label to match
        the label specified by this logic, and track it for later.

        If one does, however, it will replace the old control point
        in the MRML scene, effectively "moving" it.
        """
        # Change the name of the newly added node to the label
        markup_node = self.data_unit.markup_node
        newest_cp_idx = markup_node.GetNumberOfControlPoints() - 1
        markup_label = self.markup_labels[idx]
        markup_node.SetNthControlPointLabel(newest_cp_idx, markup_label)

        # Update the logic that it has been placed
        self.markup_placed[idx] = True

    ## Utils ##
    def on_bad_output(self):
        # Determine which error message to show
        if not self.output_dir:
            msg = _("No valid output provided! Will not be able to save your results!")
        else:
            msg = _("No output provided, falling back to previous output directory.")
        # Log it to the console for later reference
        print(msg)
        # If we have a GUI, prompt the user as well
        if self.gui:
            prompt = qt.QErrorMessage()
            prompt.setWindowTitle("Bad Output!")
            prompt.showMessage(msg)
            prompt.exec()

    ## Overrides ##
    def receive(self, data_unit: RapidMarkupUnit):
        # Track the data unit for later
        self.data_unit = data_unit

        # Display the data unit's contents
        slicer.util.setSliceViewerLayers(
            background=self.data_unit.primary_volume_node,
            fit=True
        )

        # Re-build our set of to-be-placed of fiducials
        self.markup_placed = [None for _ in self.markup_labels]
        # Mark those the data unit already has as already being annotated
        for i in range(data_unit.markup_node.GetNumberOfControlPoints()):
            fiducial_label = data_unit.markup_node.GetNthControlPointLabel(i)
            if fiducial_label in self.markup_labels:
                for j, k in enumerate(self.markup_labels):
                    if k == fiducial_label and not self.markup_placed[i]:
                        self.markup_placed[j] = True
                        break  # End so that the next iteration can work

        # Save any changes to our config
        self.config.save()

        # If we have a GUI, update it as well
        if self.gui:
            self.gui.update(data_unit)

    def save(self) -> Optional[str]:
        if not self.data_unit:
            raise ValueError("Cannot save, nothing to save!")
        self.output_manager.save_markups(self.data_unit)

    def enter(self):
        if self.gui:
            self.gui.enter()

    def exit(self):
        if self.gui:
            self.gui.exit()

    @classmethod
    def getDataUnitFactories(cls) -> dict[str, DataUnitFactory]:
        return {
            "Default": RapidMarkupUnit
        }
