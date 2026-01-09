import csv
from pathlib import Path
from typing import Optional, TYPE_CHECKING

import ctk
import numpy as np
import qt
import slicer
from slicer.i18n import tr as _

# The code below does actually work, but the Slicer widgets are only added
#  to the namespace after slicer boots, hence the error suppression
# noinspection PyUnresolvedReferences
import qSlicerSegmentationsModuleWidgetsPythonQt

if TYPE_CHECKING:
    import numpy.typing as npt
    # Try to use a reference PyQT5 install if it's available
    import PyQt5.Qt as qt


## Standardized Prompts ##
def showSuccessPrompt(msg: str, parent_widget: Optional[qt.QWidget] = None):
    """
    Show a standardized QT prompt for something being successful.

    Blocks interactions until closed (modal); you should provide a
    parent widget to "block" to avoid cross-modal blocking if possible
    """
    # Build the prompt itself
    msgPrompt = qt.QMessageBox(parent_widget)
    msgPrompt.setWindowTitle(_("SUCCESS!"))

    # Display the requested text within it, and show it to the user
    msgPrompt.setText(msg)
    msgPrompt.exec()


def showErrorPrompt(msg: str, parent_widget: Optional[qt.QWidget]):
    # Build the prompt itself
    errBox = qt.QErrorMessage(parent_widget)
    errBox.setWindowTitle(_("ERROR!"))

    # Display the requested text within it, and show it to the user
    errBox.showMessage(msg)
    errBox.exec()


## CSV-Backed Table Widget ##
class CSVBackedTableModel(qt.QAbstractTableModel):
    def __init__(self, csv_path: Optional[Path], editable: bool = True, parent: qt.QObject = None):
        super().__init__(parent)

        # The CSV path that should be referenced
        self._csv_path = csv_path

        # The backing contents of the CSV data
        self._csv_data: "Optional[npt.NDArray[str]]" = None

        # Cells should, by default, be enabled and select-able
        self._flags = qt.Qt.ItemIsEnabled | qt.Qt.ItemIsSelectable
        # Add the "editable" flag if requested as well
        if editable:
            self._flags = self._flags | qt.Qt.ItemIsEditable

        # Try to load the CSV data into memory immediately
        if csv_path is None:
            pass
        elif csv_path.exists():
            self.load()
        # If the file doesn't exist (we're creating it), set the data to be blank
        else:
            self._csv_data = np.empty((0, 0), str)

    @property
    def csv_path(self):
        return self._csv_path

    @csv_path.setter
    def csv_path(self, new_path: Path):
        self._csv_path = new_path
        # Re-load the data
        self.load()

    @property
    def header(self) -> "npt.NDArray[str]":
        return self._csv_data[0]

    @property
    def csv_data(self) -> "Optional[npt.NDArray]":
        """
        Read-only; data should be hard-synced to the backing CSV.
        """
        if self._csv_data is None:
            return None
        return self._csv_data[1:]

    # Querying
    def __getitem__(self, item):
        if self.csv_data is None:
            return None
        return self.csv_data[item]

    def __setitem__(self, key, value):
        if self.csv_data is None:
            raise IndexError("Cannot set value, as no CSV data has been initialized!")
        self.csv_data[key] = value

    ## Overrides
    def data(self, index: qt.QModelIndex, role=qt.Qt.DisplayRole):
        # If we failed to load CSV data, return None
        if self.csv_data is None:
            return None
        # If this is a displayed element, or a to-be-edited element, return the data's content
        if role in (qt.Qt.DisplayRole, qt.Qt.EditRole):
            return str(self[index.row()][index.column()])
        # Otherwise, return None by default.
        return None

    def setData(self, index: qt.QModelIndex, value, role: int = ...):
        if role == qt.Qt.EditRole:
            self[index.row()][index.column()] = str(value)
        self.dataChanged(index, index)
        return True

    def headerData(self, section: int, orientation: qt.Qt.Orientation, role: int = ...):
        # Note; "section" -> column for Horizontal, row for Vertical
        if role == qt.Qt.DisplayRole and orientation == qt.Qt.Horizontal:
            return self.header[section]
        return None

    def rowCount(self, parent: qt.QObject = None):
        if self.csv_data is None:
            return 0
        return self.csv_data.shape[0]

    def columnCount(self, parent: qt.QObject = None):
        if self.csv_data is None:
            return 0
        return self.csv_data.shape[1]

    def insertRows(self, row: int, count: int, parent = ...):
        self.beginInsertRows(parent, row, row+count)
        np.insert(self._csv_data, row, np.full((self.columnCount(parent), count), ""))
        self.endInsertRows()

    def insertColumns(self, column: int, count: int, parent = ...):
        self.beginInsertColumns(parent, column, column+count)
        np.insert(self._csv_data, column, np.full((self.columnCount(parent), count), ""), axis=1)
        self.endInsertColumns()

    def addRow(self, row_idx: int, contents: "npt.NDArray[str]"):
        # Create the new row
        self.insertRow(row_idx)
        # Inser the new values into it
        for i in range(np.min(contents.shape[0], self.columnCount())):
            self.setData(self.index(row_idx, i), contents[i])

    def addColumn(self, col_idx: int, contents: "npt.NDArray[str]"):
        # Create the new column
        self.insertColumn(col_idx)
        # Inser the new values into it
        for i in range(np.min(contents.shape[0], self.columnCount())):
            self.setData(self.index(i, col_idx), contents[i])

    def flags(self, __: qt.QModelIndex) -> "qt.Qt.ItemFlags":
        # Mark all elements as enabled, selectable, and editable
        return self._flags

    ## I/O ##
    def load(self):
        # Denote that a full reset is beginning
        self.beginResetModel()
        # Reset the backing data to contain the contents of the CSV file
        try:
            with open(self.csv_path, 'r') as fp:
                new_data = np.array([r for r in csv.reader(fp)])
                self._csv_data = new_data
        except Exception as e:
            # Blank the CSV data outright if an error occurred
            self._csv_data = None
            raise e
        finally:
            # No matter what, denote that the reset has ended
            self.endResetModel()

    def save(self):
        if self.csv_data is None:
            raise ValueError("Nothing to save!")
        with open(self.csv_path, 'w') as fp:
            csv.writer(fp).writerows(self._csv_data)

class CSVBackedTableWidget(qt.QStackedWidget):
    """
    Simple implementation for viewing the contents of a CSV file in Qt.

    Shows an error message when the backing CSV cannot be read.
    """
    def __init__(self, model: CSVBackedTableModel, parent: qt.QWidget = None):
        super().__init__(parent)

        # The table widget itself; shown when the CSV is valid
        self._model = model
        self.tableView = qt.QTableView()
        self.tableView.setModel(model)
        self.tableView.show()
        self.tableView.horizontalHeader().setSectionResizeMode(qt.QHeaderView.ResizeToContents)
        self.tableView.verticalHeader().setSectionResizeMode(qt.QHeaderView.ResizeToContents)
        self.tableView.setHorizontalScrollMode(qt.QAbstractItemView.ScrollPerPixel)
        self.addWidget(self.tableView)

        # Placeholder message; shown when no CSV is selected
        default_msg = _(
            "No CSV file has been provided yet; once selected, its contents "
            "should appear here."
        )
        self.defaultLabel = qt.QLabel(default_msg)
        self.defaultLabel.setAlignment(qt.Qt.AlignTop | qt.Qt.AlignLeft)
        self.addWidget(self.defaultLabel)

        # An error message; shown when the CSV is invalid
        error_msg = _(
            "ERROR: Could not load the selected CSV file. "
            "Please confirm it exists, is accessible, and formatted correctly."
        )
        self.errorLabel = qt.QLabel(f"<b style='color:red;'>{error_msg}</b>")
        self.errorLabel.setAlignment(qt.Qt.AlignTop | qt.Qt.AlignLeft)
        self.addWidget(self.errorLabel)

        # Set the size policy
        self.setSizePolicy(
            qt.QSizePolicy(qt.QSizePolicy.Preferred, qt.QSizePolicy.Preferred)
        )

        # Refresh immediately
        self.refresh()

    @classmethod
    def from_path(cls, csv_path, editable: bool = True):
        model = CSVBackedTableModel(csv_path, editable=editable)
        return cls(model)

    @property
    def model(self) -> CSVBackedTableModel:
        return self._model

    @model.setter
    def model(self, new_model: CSVBackedTableModel):
        # To ensure sync, we need to update the table widget's model as well
        self._model = new_model
        self.tableView.setModel(new_model)

    @property
    def backing_csv(self) -> Path:
        # Defer to our backing model
        return self.model.csv_path

    @backing_csv.setter
    def backing_csv(self, new_path: Path):
        # Defer to our backing model
        self.model.csv_path = new_path
        self.refresh()

    def save(self):
        # Defer to our backing model
        self.model.save()

    def refresh(self):
        # If we have data, show it no matter what
        if self.model.csv_data is not None:
            self.setCurrentWidget(self.tableView)
        # Otherwise, check if we just haven't selected a path yet
        elif self.model.csv_path is None:
            self.setCurrentWidget(self.defaultLabel)
        # If neither of the above, something's gone wrong
        else:
            self.setCurrentWidget(self.errorLabel)


## Cohort Editor/Preview Widget ##
class CohortTableModel(CSVBackedTableModel):
    """
    More specialized version of the CSV-backed model w/ additional checks
    and features specific to cohort editing
    """
    def __init__(self, csv_path: Optional[Path], editable: bool = True, parent: qt.QObject = None):
        super().__init__(csv_path, editable, parent)

        # Try to move the UID column to the front of the array
        if self._csv_path is not None:
            if not self._move_uid_to_index():
                raise ValueError("No UID column found, cannot set up Cohort model!")

    def _move_uid_to_index(self) -> bool:
        # If the UID is already in the index position, do nothing
        if self._csv_data[0, 0].lower() == "uid":
            return True
        # Otherwise, find and move the UID column to the front
        for i, c in enumerate(self.header):
            if c.lower() == "uid":
                # Model "reset", as this changes more than just one column's pos
                self.beginResetModel()
                uid_arr = self._csv_data[:, i]
                np.delete(self._csv_data, i, axis=1)
                np.insert(self._csv_data, 0, uid_arr, axis=1)
                self.endResetModel()
                return True
        # If that fails (there's no UID column), return False for handling
        return False

    @property
    def csv_data(self) -> "Optional[npt.NDArray]":
        if self._csv_data is None:
            return None
        # Suppressed because PyCharm went mad for some reason here
        # noinspection PyTypeChecker
        return self._csv_data[1:, 1:]

    @property
    def header(self) -> "npt.NDArray[str]":
        return self._csv_data[0, 1:]

    @property
    def indices(self) -> "npt.NDArray[str]":
        data = self._csv_data[1:, 0]
        return data

    def headerData(self, section: int, orientation: qt.Qt.Orientation, role: int = ...):
        # Note; "section" -> column for Horizontal, row for Vertical
        if role == qt.Qt.DisplayRole:
            if orientation == qt.Qt.Horizontal:
                return self.header[section]
            elif orientation == qt.Qt.Vertical:
                return self.indices[section]
        return None


class CohortTableWidget(CSVBackedTableWidget):
    """
    Simple implementation for viewing the contents of a CSV file in Qt.

    Shows an error message when the backing CSV cannot be read.
    """
    def __init__(self, model: CohortTableModel, parent: qt.QWidget = None):
        super().__init__(model, parent)

    @classmethod
    def from_path(cls, csv_path, editable: bool = True):
        model = CohortTableModel(csv_path, editable=editable)
        return cls(model)

    def refresh(self):
        # If we have data, show it no matter what
        if self.model.csv_data is not None:
            self.setCurrentWidget(self.tableView)
        # Otherwise, check if we just haven't selected a path yet
        elif self.model.csv_path is None:
            self.setCurrentWidget(self.defaultLabel)
        # If neither of the above, something's gone wrong
        else:
            self.setCurrentWidget(self.errorLabel)


## CART-Tuned Segmentation Editor ##
class _NodeComboBoxProxy(qt.QComboBox):
    """
    A combobox widget which delegates to a proxy `qMRMLNodeComboBox` to run operations
    in the code.

    This is required because there is no way to refresh a `qMRMLNodeComboBox` to check
    whether the node's its tracking have become hidden since it initialized. This is
    the only way to allow access to (and modification of) the nodes which can be
    selected by the user in several widgets.
    """

    def __init__(self, bound_widget: slicer.qMRMLNodeComboBox, *args):
        super().__init__(*args)

        # Reference to its "bound" widget which we will be instructing instead.
        self._bound_widget = bound_widget

        # Isolate the bound widget's ComboBox, as we will update it by-proxy
        self._combo_box = self._findComboBox()

        # Map from our indices to those used by the bound widget's
        self.idx_map: dict[int, int] = dict()

        # Slots are an affront to god
        self.currentIndexChanged.connect(self.onIndexChanged)

        # Initialize via a refresh
        self.refresh()

    def _findComboBox(self):
        # Search the children of our bound widget to a ComboBox of some kind
        for c in self._bound_widget.children():
            # KO: despite ctkComboBox explicitly being a subclass of QComboBox, the
            #  developers failed to translate that relationship to Python. hence us
            #  checking for both
            if isinstance(c, qt.QComboBox) or isinstance(c, ctk.ctkComboBox):
                return c

    def refresh(self):
        # Reset our entries before re-building
        self.clear()

        # Start by filtering through our viewed nodes
        # KO: We really should use "nodes" here, but despite it being documented as a
        #  valid method in the Slicer docs, it doesn't actually work! Ref:
        #  https://apidocs.slicer.org/main/classqMRMLNodeComboBox.html#a2313ce3b060a2a2068a117f3ea232a56
        self.idx_map = {}
        for i in range(self._bound_widget.nodeCount()):
            node = self._bound_widget.nodeFromIndex(i)
            if self._bound_widget.showHidden or not node.GetHideFromEditors():
                self.idx_map[self.count] = i
                self.addItem(node.GetName())

        # TODO: Consider whether we can re-enable actions (add/remove nodes) again...

    def map_index(self, idx: int):
        # Special case; -1 is universal for "nothing is selected"
        if idx == -1:
            return -1
        # Otherwise, try to get our mapped index
        mapped_idx = self.idx_map.get(idx, None)
        if mapped_idx is None:
            raise ValueError(f"Could not find requested index {idx}!")
        return mapped_idx

    def onIndexChanged(self, idx: int):
        mapped_idx = self.map_index(idx)
        self._combo_box.setCurrentIndex(mapped_idx)

    ## Proxy Parameters ##
    @property
    def addEnabled(self) -> bool:
        return self._bound_widget.addEnabled

    @addEnabled.setter
    def addEnabled(self, val: bool):
        self._bound_widget.addEnabled = val

    @property
    def removeEnabled(self) -> bool:
        return self._bound_widget.removeEnabled

    @removeEnabled.setter
    def removeEnabled(self, val: bool):
        self._bound_widget.removeEnabled = val

    @property
    def showHidden(self) -> bool:
        return self._bound_widget.showHidden

    @showHidden.setter
    def showHidden(self, val: bool):
        self._bound_widget.showHidden = val


class _VolumeNodeComboBoxProxy(_NodeComboBoxProxy):
    """
    Due to the first row in the "Source Volume" combobox always being
    "Select Source Volume for Editting", _NodeComboBoxProxy will have
    an off-by-one error if used raw.

    This subclass corrects for this discrepancy within the index map for our
    ComboBoxProxy class.
    """
    def refresh(self):
        # Refresh as usual
        super().refresh()

        # Offset the indices within the map by 1
        for k, v in self.idx_map.items():
            self.idx_map[k] = v+1


class CARTSegmentationEditorWidget(
    qSlicerSegmentationsModuleWidgetsPythonQt.qMRMLSegmentEditorWidget
):
    """
    A "wrapper" for Segment Editor Modules's editor widget, to make it more
    user-friendly and easier to manage in the context of a CART task.

    Specifically, this automatically does some stuff that each task would have
    to do themselves manually. This includes:
        * Hooking itself into an MRML scene
        * Creating a `vtkMRMLSegmentEditorNode` editor node into said scene
        * Managing shortcuts for its various functions
        * Disables adding/removing nodes (as they should be managed by the task)
        * Ensuring that only visible nodes can be selected by the user (hiding "cached" nodes)

    Code heavily based on SegmentEditorWidget in
    https://github.com/Slicer/Slicer/blob/main/Modules/Scripted/SegmentEditor/SegmentEditor.py
    """

    SEGMENT_EDITOR_NODE_KEY = "vtkMRMLSegmentEditorNode"
    TOGGLE_VISIBILITY_SHORTCUT_KEY = qt.QKeySequence("g")

    def __init__(self, tag: str = "CARTSegmentEditor", scene=slicer.mrmlScene):
        """
        Create a new segmentation editor widget; basically a carbon copy of
        `qMRMLSegmentEditorWidget` with a few additions to make it play nicer with
        CART constantly replacing nodes in MRML scene.

        :param tag: The tag for the segmentation editor node in the MRML scene.
            If you want to have your editor have different active settings than
            the one in the Segment Editor module, you should specify something
            here.
        :param scene: The MRML scene this widget will hook into. By default, it
            uses Slicer's MRML scene; passing a different scene will hook into
            it instead (useful for organization purposes in some cases).
        """
        # Run initial setup first
        super().__init__()

        # Parameters tracking for ease-of-reference
        self.tag: str = tag
        self.scene = scene

        # By default, match the Segment Editor Module's 10-deep undo state buffer
        self.setMaximumNumberOfUndoStates(10)

        # Associate ourselves with our scene
        self.setMRMLScene(self.scene)

        # Initialize (and track) the segmentation editor node in the MRML scene
        self.editor_node = self._set_up_editor_node()

        # Hide the "Add/Remove Segment" buttons, as it *will* cause problems
        self.setAddRemoveSegmentButtonsVisible(False)

        # Hide the 3D segmentation button; CART's GUI manages this for us
        # TODO: Actually move the "show 3d" button to the CART GUI
        self.setShow3DButtonVisible(False)

        # Hide the module swap button, to further discourage adding/remove segmentations
        self.setSwitchToSegmentationsButtonVisible(False)

        # Track our segmentation node combo box for direct reference
        # TODO: Figure out why this makes these combo-boxes become "stubby"
        self.proxyVolumeNodeComboBox, self.proxySegNodeComboBox = self._replaceSelectionNodes()

        # Track the current shortcut override
        self.hideActiveSegmentationShortcut = None

    ## Setup Helpers ##
    def _set_up_editor_node(self):
        # Get a pre-existing node from the MRML scene if it exists
        editor_node = self.scene.GetSingletonNode(
            self.tag, self.SEGMENT_EDITOR_NODE_KEY
        )

        # If we don't have one, create it ourselves
        if not editor_node:
            editor_node = self.scene.CreateNodeByClass(self.SEGMENT_EDITOR_NODE_KEY)
            editor_node.UnRegister(None)
            editor_node.SetSingletonTag(self.tag)
            self.scene.AddNode(editor_node)

        # Update ourselves to use this editor node
        self.setMRMLSegmentEditorNode(editor_node)

        # Track the editor node for future reference
        return editor_node

    def _replaceSelectionNodes(self) -> tuple[Optional[_NodeComboBoxProxy], Optional[_NodeComboBoxProxy]]:
        volumeSelectNode = None
        segmentSelectNode = None
        # Unfortunately we have to exploit QT here to search for it; Slicer hides it
        #  from public access through its interface
        for c in self.children():
            # Find the relevant combo-boxes in the widget and replace them
            c_name = c.name
            if c_name == "SourceVolumeNodeComboBox":
                # Build a proxy widget for it
                proxy = self._buildProxyVolumeComboBox(c)
                # Track it for later
                volumeSelectNode = proxy
            elif c_name == "SegmentationNodeComboBox":
                # Build a proxy widget for it
                proxy = self._buildProxySegmentationComboBox(c)
                # Return it, ending the search here
                segmentSelectNode = proxy

            # If we have both, end here
            if volumeSelectNode and segmentSelectNode:
                break

        # Return what we found
        return volumeSelectNode, segmentSelectNode

    def _buildProxySegmentationComboBox(self, comboBox):
        # Generate the widget we want to put in its place
        proxy = _NodeComboBoxProxy(comboBox)
        # Use it to replace the original widget in the UI
        self.layout().replaceWidget(comboBox, proxy)
        # Share the size policy of the combobox with its proxy
        proxy.setSizePolicy(comboBox.sizePolicy)
        # Hide the original combo box from view
        comboBox.setVisible(False)
        # Return the proxy for further use
        return proxy

    def _buildProxyVolumeComboBox(self, comboBox):
        # Generate the widget we want to put in its place
        proxy = _VolumeNodeComboBoxProxy(comboBox)
        # Use it to replace the original widget in the UI
        self.layout().replaceWidget(comboBox, proxy)
        # Share the size policy of the combobox with its proxy
        proxy.setSizePolicy(comboBox.sizePolicy)
        # Hide the original combo box from view
        comboBox.setVisible(False)
        # Return the proxy for further use
        return proxy

    ## Shortcuts ##
    def toggleSegmentVisibility(self):
        # Get the display node for the currently selected segmentation
        display_node = self.segmentationNode().GetDisplayNode()

        # Toggle the visibility of ALL of its segments.
        is_visible = len(display_node.GetVisibleSegmentIDs()) > 0
        display_node.SetAllSegmentsVisibility(not is_visible)

    def installShortcutOverrides(self):
        # Overwritten `g` shortcut, allowing better control of segmentation visibility
        self.hideActiveSegmentationShortcut = qt.QShortcut(slicer.util.mainWindow())
        self.hideActiveSegmentationShortcut.setKey(self.TOGGLE_VISIBILITY_SHORTCUT_KEY)
        self.hideActiveSegmentationShortcut.activated.connect(
            self.toggleSegmentVisibility
        )

    def uninstallShortcutOverrides(self):
        self.hideActiveSegmentationShortcut.activated.disconnect()
        self.hideActiveSegmentationShortcut.setParent(None)
        self.hideActiveSegmentationShortcut = None

    ## UI Management ##
    def enter(self):
        # Synchronize ourselves with the MRML state
        self.updateWidgetFromMRML()
        # Install our built-in shortcuts into Slicer's hotkeys
        self.installKeyboardShortcuts()
        # Install our custom shortcuts over top
        self.installShortcutOverrides()

    def exit(self):
        # Disable the active effect, as it *will* desync otherwise
        self.setActiveEffect(None)
        # Uninstall keyboard shortcuts
        self.uninstallKeyboardShortcuts()
        # Install our custom shortcuts over top
        self.uninstallShortcutOverrides()

    def refresh(self):
        self.proxyVolumeNodeComboBox.refresh()
        self.proxySegNodeComboBox.refresh()

    def setSegmentationNode(self, segment_node):
        # KO: We need to delegate to our proxy widget here,
        # otherwise it and the "real" Slicer state will no longer
        # by in sync
        self.proxySegNodeComboBox.setCurrentText(
            segment_node.GetName()
        )
