from pathlib import Path
from typing import TYPE_CHECKING, Optional

import qt
import slicer
from slicer.i18n import tr as _

from CARTLib.utils.config import ResourceSpecificConfig
from CARTLib.utils.data import (
    CARTStandardUnit,
    MarkupResource,
    SegmentationResource,
    VolumeResource,
    create_empty_segmentation_node,
    load_segmentation,
)

from SegmentationConfig import ExtendedSegmentationResourceConfig

## Type Utils ##
if TYPE_CHECKING:
    # Avoid potential cyclic imports
    from CARTLib.core.DataUnitBase import ResourceType

    # NOTE: this isn't perfect (this only exposes Widgets, and Slicer's QT impl
    # isn't the same as PyQT5 itself), but it's a LOT better than constant
    # cross-referencing
    import PyQt5.Qt as qt


## Resource-Specific Elements ##
class EditableSegmentationResource(SegmentationResource):

    id = "segmentation_editable"
    pretty_name = "To-Edit Segmentation"
    user_warning = _("⚠ The resource name will be used as a suffix in the saved file! ⚠")
    description = _(
        "A discrete (integer) segmentation of anatomy you want to load and edit for a given case. "
        "If a case is missing this resource, a blank segmentation will be created instead "
        "(which you can then edit). Can support multiple segmentations within a single file, "
        "as long as each has a unique 'final' integer value. "
        "\n\n"
        "Any changes made to this resource will be saved when the case is saved. "
        "You can customize the values the label(s) will have using the GUI below. "
        "Please define it to the best of your ability."
    )

    @classmethod
    def buildConfigGUI(
        cls, task_config: "DictBackedConfig", resource_id: Optional[str] = None
    ) -> "Optional[qt.QLayout]":
        # Initialize the layout as before
        layout = super().buildConfigGUI(task_config, resource_id)

        # Add an QTableWidget to display the segments associated w/ this resource
        resource_config = ExtendedSegmentationResourceConfig(ResourceSpecificConfig(task_config), resource_id)
        resource_config.buildSegmentTableGUI(layout)

        return layout


class ReferenceSegmentationResource(SegmentationResource):

    id = "segmentation_view_only"
    pretty_name = "To-View Segmentation"
    description = _(
        "A discrete (integer) segmentation of anatomy you want to load for reference. "
        "Nothing is done if a case is missing this resource; it is simply skipped over. "
        "\n\n"
        "While you can edit this segmentation in Slicer if you so choose, "
        "any changes made will **NOT** be saved when the case is saved."
    )

    @classmethod
    def buildConfigGUI(
        cls, task_config: "DictBackedConfig", resource_id: Optional[str] = None
    ) -> "Optional[qt.QLayout]":
        # Initialize the layout as before
        layout = super().buildConfigGUI(task_config, resource_id)

        # Add an QTableWidget to display the segments associated w/ this resource
        resource_config = ExtendedSegmentationResourceConfig(
            ResourceSpecificConfig(task_config), resource_id
        )
        resource_config.buildSegmentTableGUI(layout)

        return layout


class SegmentationUnit(CARTStandardUnit):
    """
    DataUnit for the segmentation task. Extends the CART
    Standard Unit to support custom segmentations.
    """

    # Replace the default segmentation resource w/ our custom subtypes
    RESOURCE_TYPES = {
        VolumeResource.id: VolumeResource,
        EditableSegmentationResource.id: EditableSegmentationResource,
        ReferenceSegmentationResource.id: ReferenceSegmentationResource,
        MarkupResource.id: MarkupResource
    }

    def __init__(
        self,
        case_data: dict[str, str],
        data_path: Path,
        scene: slicer.vtkMRMLScene = slicer.mrmlScene,
    ) -> None:
        super().__init__(case_data, data_path, scene)

        # Subset of segmentation nodes marked "custom"
        self._custom_segmentations = dict()

    @property
    def custom_segmentations(self):
        # Get only to avoid unintentional de-sync
        return self._custom_segmentations

    def add_custom_segmentation(self, name: str, color_hex: str):
        """
        Create a new "custom" segmentation for this data unit;
        these segmentations allow users to "add" new elements
        to the dataset.

        :return: The newly created segmentation node.
        """
        formatted_name = f"{name} ({self.uid})"
        if formatted_name in self._custom_segmentations.keys():
            raise ValueError(
                f"Cannot create custom segmentation '{name}'; "
                "a segmentation with that name already exists!"
            )

        # Create and track the new segmentation node
        new_node = None
        try:
            # Create the new node
            new_node = create_empty_segmentation_node(
                formatted_name,
                reference_volume=self.primary_volume_node,
                scene=self.scene,
            )

            # Add a new (blank) segment within the node for the user to edit
            segmentation_node = new_node.GetSegmentation()
            segment_id = segmentation_node.AddEmptySegment(name, "1")
            segment = segmentation_node.GetSegment(segment_id)

            # Set its color to match the one provided
            rgb_string = color_hex.lstrip("#")
            rgb = (int(rgb_string[i:i + 2], 16)/255 for i in (0, 2, 4))
            segment.SetColor(*rgb)

            # Track it for later reference
            self.custom_segmentations[formatted_name] = new_node
            self.segmentation_nodes[formatted_name] = new_node
            return new_node
        except Exception as e:
            # If this fails at any point, clean up the unit from the scene
            if new_node:
                slicer.mrmlScene.RemoveNode(new_node)
            raise e

    def _init_segmentation_nodes(self) -> None:
        """
        Modified version of the super-class, which "fills in" missing
        segmentations with blanks ones instead
        """
        # If we don't have a primary volume yet, this method was called too early
        if not self.primary_volume_node:
            raise ValueError(
                "Cannot initialize segmentation nodes prior to volume nodes!"
            )

        # Prepare to set the color of each segment
        color_table = slicer.util.getNode("GenericColors").GetLookupTable()
        c_idx = 2  # Start at 2, so newly created segments can have a unique color
        for key in self.segmentation_keys:
            seg_path = self.segmentation_paths.get(key, None)
            # Try to read from file
            if seg_path is not None:
                if seg_path.exists():
                    # Try to load the segmentation first
                    node = load_segmentation(seg_path)
                else:
                    continue
            # If no file exists, create a segmentation from scratch
            else:
                node = create_empty_segmentation_node(
                    "",
                    reference_volume=self.primary_volume_node,
                    scene=self.scene,
                )

                # Add a new (blank) segment within the node for the user to edit
                segmentation_node = node.GetSegmentation()
                segmentation_node.AddEmptySegment("", "1")

            # Set the name of the node, and align it to our primary volume
            node.SetName(f"{key} ({self.uid})")
            node.SetReferenceImageGeometryParameterFromVolumeNode(
                self.primary_volume_node
            )

            # Apply a unique color to all segments within the segmentation
            for segment_id in node.GetSegmentation().GetSegmentIDs():
                print(f"Setting color for segment '{segment_id}' in '{key}'.")
                segment = node.GetSegmentation().GetSegment(segment_id)

                # Get the corresponding color, w/ Alpha stripped from it
                segmentation_color = color_table.GetTableValue(c_idx)[:-1]
                segment.SetColor(*segmentation_color)

                # Increment the color index
                c_idx += 1
            self.segmentation_nodes[key] = node
            self.resources[key] = node

    @classmethod
    def resource_types(cls) -> "dict[str, ResourceType]":
        # Replace the "default" se
        return cls.RESOURCE_TYPES
