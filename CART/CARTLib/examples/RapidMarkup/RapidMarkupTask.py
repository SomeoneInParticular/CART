from pathlib import Path
from typing import Optional

import qt
import slicer
from CARTLib.core.TaskBaseClass import TaskBaseClass, DataUnitFactory
from CARTLib.utils.config import ProfileConfig
from CARTLib.utils.task import cart_task
from CARTLib.utils.widgets import showSuccessPrompt
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

        # Markup tracking
        self.markups: list[tuple[str, Optional[str]]] = []
        self.untracked_markups: dict[str, list[str]] = {}

        # Output management
        self._output_format: Optional[RapidMarkupOutputManager.OutputFormat] = None
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
                self.markups = [
                    (l, None) for l in self.config.last_used_markups
                ]
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

            # If the user still didn't provide an output, end here
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

        # Update our config with this annotation set and save it
        self.config.last_used_markups = self.markup_labels
        self.config.last_used_output = self.output_dir
        self.config.save()

    ## Properties
    @property
    def markup_labels(self) -> list[str]:
        return [l for l, __ in self.markups]

    @property
    def output_dir(self) -> Path:
        return self._output_dir

    @output_dir.setter
    def output_dir(self, new_path: Path):
        """
        This setter handles a few things:
          * Ensures the directory is valid before overwriting it
          * Invalidates relevant cached values
        """
        # if the path doesn't exist, or is invalid, notify the user and end
        if not (new_path and new_path.exists() and new_path.is_dir()):
            self.on_bad_output()
            return

        # Update our output directory directly
        self._output_dir = new_path

        # Update the output manager's directory to match, if it exists
        if self._output_manager:
            self.output_manager.output_dir = new_path

    @property
    def output_format(self) -> RapidMarkupOutputManager.OutputFormat:
        return self._output_format

    @output_format.setter
    def output_format(self, new_format: RapidMarkupOutputManager.OutputFormat):
        # Update our own format
        self._output_format = new_format

        # Update the output manager's format to match, if it exists
        if self._output_manager:
            self.output_manager.output_format = new_format

    @property
    def output_manager(self):
        # Pseudo-cached read-only property, allowing for lazy generation
        if not self._output_manager:
            self._output_manager = RapidMarkupOutputManager(
                self.profile,
                self.output_dir,
                self.output_format
            )
        return self._output_manager

    ## Unit Management ##
    def _pop_untracked_markup(self, label: str) -> Optional[str]:
        """
        Tries to find an untracked markup with a label matching the
        label provided. If it succeeds, removes it from our
        'untracked' map and provides the ID for the corresponding
        node for re-use. If it fails, returns None instead
        """
        if label in self.untracked_markups.keys():
            markup_id = self.untracked_markups[label].pop()
            if len(self.untracked_markups[label]) < 1:
                del self.untracked_markups[label]
            return markup_id
        else:
            return None

    def add_markup_label(self, idx: int, new_label: str) -> Optional[str]:
        """
        Add a new markup label to the logic.

        Returns the ID of the matching markup node in the tracked
        data unit if one was found; otherwise, returns None
        """
        markup_id = None
        # Bind to any untracked markup that may exist by the same name if possible
        if new_label in self.untracked_markups.keys():
            markup_id = self._pop_untracked_markup(new_label)

        # Track the resulting tuple
        self.markups.insert(idx, (new_label, markup_id))

        # Update the config to match
        self.config.last_used_markups = self.markup_labels

        # Return the ID of the markup node, if any
        return markup_id

    def remove_markup_label(self, idx: int):
        markup_label, markup_id = self.markups[idx]

        # If the user has configured it, remove the corresponding markup from the scene as well
        if markup_id and self.config.remove_from_scene:
            # Find the markup in question and remove it from the scene
            markup_idx = self.data_unit.markup_node.GetNthControlPointIndexByID(markup_id)
            self.data_unit.markup_node.RemoveNthControlPoint(markup_idx)
        # Otherwise, we just stop tracking it instead
        else:
            # Move the markup from tracked to untracked
            untracked_markup_group = self.untracked_markups.get(markup_label, [])
            untracked_markup_group.append(markup_id)
            self.untracked_markups[markup_label] = untracked_markup_group
        # Remove the markup from being tracked
        del self.markups[idx]

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

        If one does, however, it will move that control point to the
        position of the newest control point and then delete it,
        effectively "replacing" it.
        """
        # Pull some globally relevant data first
        markup_node = self.data_unit.markup_node
        markup_label, markup_id = self.markups[idx]
        new_markup_idx = markup_node.GetNumberOfControlPoints() - 1

        # If this index doesn't have a markup yet, simply use it
        if not markup_id:
            # Make the markups label match our own
            markup_node.SetNthControlPointLabel(new_markup_idx, markup_label)
            # Track it for later re-use
            markup_id = markup_node.GetNthControlPointID(new_markup_idx)
            self.markups[idx] = (markup_label, markup_id)
        # Otherwise, move the markup instead
        else:
            # Move the old markup to the new markup's position
            new_pos = markup_node.GetNthControlPointPositionVector(new_markup_idx)
            old_markup_idx = markup_node.GetNthControlPointIndexByID(markup_id)
            markup_node.SetNthControlPointPosition(old_markup_idx, new_pos)
            # Delete the new markup
            markup_node.RemoveNthControlPoint(new_markup_idx)

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

        # Generate a map of pre-existing values within the data unit (if any)
        self.untracked_markups = dict()
        for i in range(data_unit.markup_node.GetNumberOfControlPoints()):
            markup_id = data_unit.markup_node.GetNthControlPointID(i)
            markup_label = data_unit.markup_node.GetNthControlPointLabel(i)
            prior_vals = self.untracked_markups.get(markup_label, [])
            prior_vals.append(markup_id)
            self.untracked_markups[markup_label] = prior_vals

        # Generate our list of tracked markups, binding to pre-existing where possible
        for i, (l, __) in enumerate(self.markups):
            # Try to find the corresponding markup
            v = self._pop_untracked_markup(l)
            # Build a tuple from the result
            self.markups[i] = (l, v)

        # Save any changes to our config
        self.config.save()

        # If we have a GUI, update it as well
        if self.gui:
            self.gui.update(data_unit)

    def save(self) -> Optional[str]:
        # We can only save if we have something to save!
        if not self.data_unit:
            raise ValueError("Cannot save, nothing to save!")
        # Delegate to the output manager to save the file
        result_msg = self.output_manager.save_markups(self.data_unit)
        # Log the result to console
        print(result_msg)
        # If we have a GUI, prompt the user as well
        if self.gui:
            showSuccessPrompt(result_msg)

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
