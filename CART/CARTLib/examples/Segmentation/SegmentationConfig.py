from enum import Enum
from typing import Optional, TYPE_CHECKING

import ctk
import qt

from slicer.i18n import tr as _

from CARTLib.utils.config import DictBackedConfig, JobProfileConfig
from CARTLib.utils.data import SegmentationResourceConfig

if TYPE_CHECKING:
    # Provide some type references for QT, even if they're not
    #  perfectly useful.
    import PyQt5.Qt as qt


class SegmentationFileStructure(Enum):
    BIDS = "BIDS"
    FolderPerCase = "Folder-per-Case"


class SegmentationFileFormat(Enum):
    NIFTI = "NiFTI"
    NRRD = "NRRD"


class SegmentationConfig(DictBackedConfig):
    """
    Configuration manager for the MultiContrast task
    """

    CONFIG_KEY = "multi_contrast_segmentation"

    def __init__(self, parent_config: JobProfileConfig):
        super().__init__(parent_config=parent_config)

    @classmethod
    def default_config_label(cls) -> str:
        return cls.CONFIG_KEY

    ## CONFIG ENTRIES ##
    SHOULD_INTERPOLATE_KEY = "should_interpolate"

    @property
    def should_interpolate(self) -> bool:
        return self.get_or_default(self.SHOULD_INTERPOLATE_KEY, True)

    @should_interpolate.setter
    def should_interpolate(self, new_val: bool):
        self.backing_dict[self.SHOULD_INTERPOLATE_KEY] = new_val
        self.has_changed = True

    HIDE_EDITABLE_ON_START_KEY = "hide_editable_on_start"

    @property
    def hide_editable_on_start(self) -> bool:
        return self.get_or_default(self.HIDE_EDITABLE_ON_START_KEY, False)

    @hide_editable_on_start.setter
    def hide_editable_on_start(self, new_val: bool):
        self.backing_dict[self.HIDE_EDITABLE_ON_START_KEY] = new_val
        self.has_changed = True

    SAVE_BLANK_SEGMENTATIONS_KEY = "save_blanks"

    @property
    def save_blank_segmentations(self) -> bool:
        return self.get_or_default(self.SAVE_BLANK_SEGMENTATIONS_KEY, True)

    @save_blank_segmentations.setter
    def save_blank_segmentations(self, new_val: bool):
        self.backing_dict[self.SAVE_BLANK_SEGMENTATIONS_KEY] = new_val
        self.has_changed = True

    CUSTOM_SEGMENTATIONS_KEY = "custom_segmentations"
    CUSTOM_SEG_PATH_KEY = "path_string"
    CUSTOM_SEG_COLOR_KEY = "color"

    @property
    def custom_segmentations(self) -> dict[str, dict]:
        return self.get_or_default(self.CUSTOM_SEGMENTATIONS_KEY, dict())

    @custom_segmentations.setter
    def custom_segmentations(self, new_vals: dict[str, dict]):
        self.backing_dict[self.CUSTOM_SEGMENTATIONS_KEY] = new_vals
        self.has_changed = True

    def add_custom_segmentation(self, new_name: str, output_str: str, color_hex: str):
        sub_dict = {
            self.CUSTOM_SEG_PATH_KEY: output_str,
            self.CUSTOM_SEG_COLOR_KEY: color_hex
        }
        self.custom_segmentations[new_name] = sub_dict
        self.has_changed = True

    SEGMENTATIONS_TO_SAVE_KEY = "segmentations_to_save"

    @property
    def segmentations_to_save(self) -> list[str]:
        return self.get_or_default(self.SEGMENTATIONS_TO_SAVE_KEY, list())

    @segmentations_to_save.setter
    def segmentations_to_save(self, new_segs: list[str]):
        self._backing_dict[self.SEGMENTATIONS_TO_SAVE_KEY] = new_segs
        self.has_changed = True

    EDIT_OUTPUT_PATH_KEY = "edit_output_path"

    @property
    def edit_output_path(self) -> str:
        return self.get_or_default(self.EDIT_OUTPUT_PATH_KEY, "")

    @edit_output_path.setter
    def edit_output_path(self, new_val: str):
        self.backing_dict[self.EDIT_OUTPUT_PATH_KEY] = new_val
        self.has_changed = True

    DEFAULT_CUSTOM_OUTPUT_PATH_KEY = "default_custom_output_path"

    @property
    def default_custom_output_path(self) -> str:
        return self.get_or_default(self.DEFAULT_CUSTOM_OUTPUT_PATH_KEY, "")

    @default_custom_output_path.setter
    def default_custom_output_path(self, new_val: str):
        self.backing_dict[self.DEFAULT_CUSTOM_OUTPUT_PATH_KEY] = new_val
        self.has_changed = True

    def generateGUILayout(self) -> tuple[str, Optional[qt.QLayout]]:
        return _("Segmentation Configuration"), SegmentationConfigGUILayout(self)


class ExtendedSegmentationResourceConfig(SegmentationResourceConfig):
    """
    Configuration manager for a specific segmentation resource, tuned for this task.
    """

    SHOULD_SAVE_KEY = "should_save"

    @property
    def should_save(self) -> bool:
        # Whether this segmentation should save itself when the case it's part of does
        return self.get_or_default(self.SHOULD_SAVE_KEY, True)

    @should_save.setter
    def should_save(self, new_val: bool):
        self.backing_dict[self.SHOULD_SAVE_KEY] = new_val

    SEGMENTS_KEY = "segments"

    @property
    def segments(self) -> list[dict]:
        # Map of the segments this resource is handling;
        # Maps value (with the segmentation) to segment name and color (in hex format)
        return self.get_or_default(
            self.SEGMENTS_KEY, list()
        )

    NAME_KEY = "Name"
    VALUE_KEY = "Value"
    COLOR_KEY = "Color"

    def add_segment(self, label: str, value: int, color: str):
        """
        Add a new segment with the given values
        """
        self.segments.append({
            self.NAME_KEY: label,
            self.VALUE_KEY: value,
            self.COLOR_KEY: color
        })

    def drop_segment(self, idx: int) -> dict:
        """
        Drop configuration options associated with the provided segment
        """
        return self.segments.pop(idx)

    HEADER_MAP = {
        NAME_KEY: 0,
        VALUE_KEY: 1,
        COLOR_KEY: 2
    }

    def buildSegmentTableGUI(self, layout: qt.QFormLayout):
        # Table widget to place the results within
        # TODO: Make QT model/view wrappers for this to ensure sync is maintained
        table = qt.QTableWidget(0, 3, None)
        table.setHorizontalHeaderLabels(list(self.HEADER_MAP.keys()))

        # Make the table behave in a sensible manner
        table.setSizeAdjustPolicy(qt.QAbstractScrollArea.AdjustToContents)
        table.horizontalHeader().setSectionResizeMode(qt.QHeaderView.ResizeToContents)
        table.verticalHeader().setSectionResizeMode(qt.QHeaderView.ResizeToContents)
        table.setHorizontalScrollMode(qt.QAbstractItemView.ScrollPerPixel)
        table.setSizePolicy(
            qt.QSizePolicy.Expanding, qt.QSizePolicy.Expanding
        )

        # Make the columns stretch to fill available space
        table.horizontalHeader().setSectionResizeMode(0, qt.QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, qt.QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, qt.QHeaderView.Stretch)

        # Give ourselves 3 columns, as QT is too dumb to figure it out otherwise
        table.setColumnCount(3)

        # Simple helper function to avoid duplicate code
        def _setTableDataFor(idx, name, value, color):
            # If this index is larger than the current number of rows, give ourselves a new row
            if idx >= table.rowCount:
                table.setRowCount(table.rowCount + 1)

            nameItem = qt.QTableWidgetItem(name)
            valueItem = qt.QTableWidgetItem(str(value))
            colorItem = qt.QTableWidgetItem(color)

            # Disable the color from being edited; its handled another way
            colorItem.setFlags(
                colorItem.flags() & ~qt.Qt.ItemIsEditable
            )

            # Set the color backround + text color
            qColor = qt.QColor(color)
            colorItem.setBackground(qColor)
            # Make the text black or white depending on how bright the new color is
            if qColor.lightness() > 100:
                colorItem.setForeground(qt.QBrush(qt.QColor("#000000")))
            else:
                colorItem.setForeground(qt.QBrush(qt.QColor("#FFFFFF")))

            table.setItem(idx, self.HEADER_MAP[self.NAME_KEY], nameItem)
            table.setItem(idx, self.HEADER_MAP[self.VALUE_KEY], valueItem)
            table.setItem(idx, self.HEADER_MAP[self.COLOR_KEY], colorItem)

        # Instantiate w/ our starting values
        for i, val_dict in enumerate(self.segments):
            _setTableDataFor(
                i,
                val_dict.get(self.NAME_KEY),
                val_dict.get(self.VALUE_KEY),
                val_dict.get(self.COLOR_KEY),
            )

        # Add the table to the layout
        layout.addRow(table)

        # Add buttons add, edit, and remove entries in the table
        addButton = qt.QPushButton(_("New"))
        deleteButton = qt.QPushButton(_("Delete"))
        buttonPanel = qt.QWidget(None)
        buttonLayout = qt.QHBoxLayout(buttonPanel)
        buttonLayout.addWidget(addButton)
        buttonLayout.addWidget(deleteButton)
        layout.addRow(buttonPanel)

        # When the selections change, enable/disable the edit and delete buttons
        @qt.Slot()
        def selectionChanged():
            selected_indices = table.selectedIndexes()
            selected_rows = len({idx.row() for idx in selected_indices})
            deleteButton.setEnabled(selected_rows > 0)

        table.itemSelectionChanged.connect(selectionChanged)
        selectionChanged()

        # When the contents of the table change, update our backing dict to match
        @qt.Slot(int, int)
        def onCellChanged(row: int, col: int):
            # Get the new value inserted into this location
            item: qt.QTableWidgetItem = table.item(row, col)
            new_val = item.text()
            key = list(self.HEADER_MAP.keys())[col]

            # If the item is our "value" column, make sure it's an integer before proceeding
            if key == self.VALUE_KEY:
                try:
                    new_val = int(new_val)
                    if new_val == 0:
                        raise ValueError()
                except ValueError:
                    # If we couldn't, restore the original value and tell the user what happened
                    old_val = self.segments[row].get(self.VALUE_KEY)
                    item.setText(str(old_val))
                    qt.QMessageBox.critical(
                        table,
                        _("Invalid Value") + f" '{new_val}'",
                        _(f"Value must be a non-zero integer! Previous value {old_val} was restored."),
                        qt.QMessageBox.Ok,
                    )
                    return

            # Update ourselves to match
            segment_dict = self.segments[row]
            segment_dict[key] = new_val

            # Mark ourselves as being changed
            self.has_changed = True

        table.cellChanged.connect(onCellChanged)

        # Add button simply creates a new row w/ default values the user can edit later
        @qt.Slot()
        def addClicked():
            # Find the smallest positive value not already taken
            value = 1
            taken_vals = {x[self.VALUE_KEY] for x in self.segments}
            while value in taken_vals:
                value += 1

            # The other defaults
            name = ""
            color = "#fadd00"  # Gold-ish

            # Create an (empty) dictionary and place it into our segments;
            # it will be populated when the table updates
            self.segments.append(dict())

            # Update the table
            try:
                _setTableDataFor(table.rowCount, name, value, color)
            except Exception as e:
                # If that failed somehow, clean up the (likely malformed) new segment
                self.segments.pop(table.rowCount)
                raise e

        addButton.clicked.connect(addClicked)

        # Delete button deletes all selected rows
        @qt.Slot()
        def deleteClicked():
            selected_rows = {idx.row() for idx in table.selectedIndexes()}
            for r in selected_rows:
                # Drop the row in the table itself
                table.removeRow(r)

                # If that worked correctly, remove it from our backing config too
                self.segments.pop(r)

        deleteButton.clicked.connect(deleteClicked)

        # Double-clicking on a color cell brings up the color picker instead
        @qt.Slot(int, int)
        def onCellDoubleClicked(row: int, col: int):
            # If this row does not correspond to the color column, do nothing
            if self.HEADER_MAP[self.COLOR_KEY] != col:
                return

            # Get the item at this location
            item: qt.QTableWidgetItem = table.item(row, col)

            # Close the (now open) persistent editor
            table.closePersistentEditor(item)

            # Request the user provide a new color w/ CTK's color dialog
            init_color = qt.QColor(item.text())
            color_dialog = ctk.ctkColorDialog()
            # If the user backed out, return without proceeding further
            qColor: qt.QColor = color_dialog.getColor(init_color, None)

            # Update our item to have this new value
            item.setText(qColor.name())
            item.setBackground(qColor)

            # Make the text black or white depending on how bright the new color is
            if qColor.lightness() > 100:
                item.setForeground(qt.QBrush(qt.QColor("#000000")))
            else:
                item.setForeground(qt.QBrush(qt.QColor("#FFFFFF")))

        table.cellDoubleClicked.connect(onCellDoubleClicked)


class SegmentationConfigGUILayout(qt.QFormLayout):
    def __init__(self, config: SegmentationConfig, parent = None, ):
        super().__init__(parent)

        # Output folder structure selection
        fileStructureComboBox = qt.QComboBox(None)
        fileStructureComboBox.addItems([x.value for x in SegmentationFileStructure])
        fileStructureLabel = qt.QLabel(_("Output File Structure:"))
        self.addRow(fileStructureLabel, fileStructureComboBox)

        # Output file structure selection
        fileFormatComboBox = qt.QComboBox(None)
        fileFormatComboBox.addItems([x.value for x in SegmentationFileFormat])
        fileFormatLabel = qt.QLabel(_("Output File Format:"))
        self.addRow(fileFormatLabel, fileFormatComboBox)

        # Toggle-able options
        toggleLayout = qt.QFormLayout(None)
        self.addRow(toggleLayout)

        ## Segmentation Overlap
        segmentOverlapCheckBox = qt.QCheckBox()
        segmentOverlapLabel = qt.QLabel(_("Disallow Overlapping Segments"))
        toggleLayout.addRow(segmentOverlapCheckBox, segmentOverlapLabel)

        ## Hide To-Edit Segments on Load
        hideEditSegmentsInitiallyCheckBox = qt.QCheckBox()
        hideEditSegmentsInitiallyCheckBox.setChecked(config.hide_editable_on_start)
        hideEditSegmentsInitiallyLabel = qt.QLabel(_("Initially Hide To-Edit Segmentations"))
        toggleLayout.addRow(hideEditSegmentsInitiallyCheckBox, hideEditSegmentsInitiallyLabel)

        ## Whether to save blank segmentations
        saveEmptySegmentsCheckBox = qt.QCheckBox()
        saveEmptySegmentsLabel = qt.QLabel(_("Save Empty Segmentations (will result in 'blank' files)"))
        toggleLayout.addRow(saveEmptySegmentsCheckBox, saveEmptySegmentsLabel)

        # Connections
        @qt.Slot(None)
        def onHideEditsToggled():
            config.hide_to_edit = hideEditSegmentsInitiallyCheckBox.isChecked()
        hideEditSegmentsInitiallyCheckBox.toggled.connect(onHideEditsToggled)
