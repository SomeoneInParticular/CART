from typing import Optional

import qt
import slicer

from RapidAnnotationUnit import RapidAnnotationUnit


# Type hint guard; only risk the cyclic import if type hints are running
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    # noinspection PyUnusedImports
    from RapidAnnotationTask import RapidAnnotationTask


class RapidAnnotationGUI:

    COMPLETED_BRUSH = qt.QBrush(
        qt.QColor(0, 255, 0, 100)
    )
    HIGHLIGHTED_BRUSH = qt.QBrush(
        qt.QColor(0, 0, 255, 100)
    )
    SKIPPED_BRUSH = qt.QBrush(
        qt.QColor(255, 0, 0, 100)
    )
    BLANK_BRUSH = qt.QBrush(
        qt.QColor(0, 0, 0, 255)
    )

    def __init__(self, bound_task: "RapidAnnotationTask"):
        self.bound_task = bound_task
        self.data_unit: Optional[RapidAnnotationUnit] = None

        # Widget displaying the data unit
        self.annotationList = None

        # Observer IDs; need to be tracked here to avoid cyclic referencing
        self.anot_observer_id: Optional[str] = None
        self.backout_observer_id: Optional[str] = None

    def setup(self) -> qt.QFormLayout:
        # Initialize a layout we'll insert everything into
        formLayout = qt.QFormLayout()

        self._initAnnotationList(formLayout)

        return formLayout

    def _initAnnotationList(self, formLayout: qt.QFormLayout):
        # Create a list widget w/ drag and drop capabilities
        annotationList = qt.QListWidget()
        annotationListLabel = qt.QLabel("Registered Annotations")

        # Insert all attributes tracked by the logic into the annotation list
        annotationList.addItems(self.bound_task.tracked_annotations)

        # Add it to the layout and track it for later
        formLayout.addRow(annotationListLabel)
        formLayout.addRow(annotationList)
        self.annotationList = annotationList

    def update(self, data_unit: RapidAnnotationUnit):
        # Track the new data unit
        self.data_unit = data_unit

        # Update the layout to use its contents
        self.data_unit.layout_handler.apply_layout()

        # Synchronize with our logic's state
        self._syncAnnotationList()

        # Start node placement
        # TODO: make this automated start configurable
        self.initAnnotationPlacement()

    def _syncAnnotationList(self):
        for i in range(self.annotationList.count):
            listItem = self.annotationList.item(i)
            label = listItem.text()
            if self.bound_task.annotation_complete_map.get(label, False):
                listItem.setBackground(self.COMPLETED_BRUSH)
            else:
                listItem.setBackground(self.BLANK_BRUSH)

    def initAnnotationPlacement(self):
        # Ensure the data unit's annotation node the selected one
        selectionNode = slicer.app.applicationLogic().GetSelectionNode()
        selectionNode.SetActivePlaceNodeID(self.data_unit.annotation_node.GetID())

        # Start by getting the user to place the first node
        self._userPlacePoint()

    # TODO: Rewrite this, this is cursed beyond belief
    def _userPlacePoint(self, prior_idx: int = -1):
        # Remove the previous observer callbacks
        anot_node = self.bound_task.data_unit.annotation_node
        if self.anot_observer_id:
            anot_node.RemoveObserver(self.anot_observer_id)

        interactionNode = slicer.app.applicationLogic().GetInteractionNode()
        if self.backout_observer_id:
            interactionNode.RemoveObserver(self.backout_observer_id)

        # Move the starting point up 1
        start_index = prior_idx + 1

        # Find the next valid index in the remaining range
        for i in range(start_index, self.annotationList.count):
            anot_item = self.annotationList.item(i)
            anot_label = anot_item.text()
            # If this annotation isn't completed, get the user to try and place it
            if not self.bound_task.annotation_complete_map.get(anot_label, False):
                # Enter placement mode for the user
                interactionNode.SetCurrentInteractionMode(interactionNode.Place)
                interactionNode.SetPlaceModePersistence(True)

                # Highlight the corresponding entry in our list
                anot_item.setBackground(self.HIGHLIGHTED_BRUSH)

                # Register a callback for when a new point is placed!
                def _onAnotAdded(caller, _):
                    # Change the name of the newly added node to its proper name
                    newest_point_idx = caller.GetNumberOfControlPoints() - 1
                    caller.SetNthControlPointLabel(newest_point_idx, anot_label)

                    # Mark this annotation as complete
                    anot_item.setBackground(self.COMPLETED_BRUSH)
                    self.bound_task.annotation_complete_map[anot_label] = True

                    # Try to prompt the user for the next node
                    self._userPlacePoint(i)

                self.anot_observer_id = anot_node.AddObserver(
                    anot_node.PointPositionDefinedEvent, _onAnotAdded
                )

                # Register a callback for when the user exits placement mode (indicating they backed out)
                def _onBackOut(_, __):
                    # Highlight the entry in "skipped" colors
                    anot_item.setBackground(self.SKIPPED_BRUSH)

                    # Proceed to the next point
                    self._userPlacePoint(i)

                self.backout_observer_id = interactionNode.AddObserver(
                    interactionNode.InteractionModeChangedEvent, _onBackOut
                )

                # Terminate
                break
        else:
            # If the loop ran to completion, exit persistent mode
            interactionNode.SetPlaceModePersistence(False)

    ## GUI SYNCHRONIZATION ##
    def enter(self) -> None:
        pass

    def exit(self) -> None:
        pass
