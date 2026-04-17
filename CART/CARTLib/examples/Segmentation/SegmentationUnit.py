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
    from SegmentationConfig import SegmentationConfig

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

    @classmethod
    def get_short_name(cls, resource_id: str):
        id_str = f"_{cls.id}"
        if not resource_id.endswith(id_str):
            return resource_id
        return resource_id.replace(id_str, "")


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

    def apply_segmentation_configs(self, task_config: "SegmentationConfig"):
        """
        Apply the user-specified configuration options to the segmentations managed by
        this unit. This includes;

        * Renaming and recoloring existing segments
        * Creating missing segmentations (and segments)
        * Tracking the segmentations which should be saved
        """
        resource_config_manager = ResourceSpecificConfig(task_config)
        for k in resource_config_manager.backing_dict.keys():
            # Skip over non-segmentation resources
            if not SegmentationResource.is_type(k):
                continue
            # If there's no config options for this resource, proceed w/o doing anything
            if resource_config_manager.backing_dict.get(k) is None:
                continue
            # Updated/add the segmentation corresponding to this resource's configuration settings
            segmentation_config = ExtendedSegmentationResourceConfig(resource_config_manager, k)
            segmentation_node = self.segmentation_nodes.get(k)

            # If there isn't already a segmentation node for a to-be-edited segmentation, create one
            should_edit = EditableSegmentationResource.is_type(k)
            if should_edit and segmentation_node is None:
                self._create_new_segmentation(k)

            # Iterate through our segment config and apply them whenever we have a match
            segmentation = segmentation_node.GetSegmentation()
            missing_segments = list()
            for segment_config in segmentation_config.segments:
                seg_val = segment_config.get(
                    ExtendedSegmentationResourceConfig.VALUE_KEY
                )
                seg_color = segment_config.get(
                    ExtendedSegmentationResourceConfig.COLOR_KEY
                )
                seg_name = segment_config.get(
                    ExtendedSegmentationResourceConfig.NAME_KEY
                )

                # Try and find the segment w/ the matching value
                was_found = False
                for segment in map(
                    lambda i: segmentation.GetNthSegment(i),
                    range(segmentation.GetNumberOfSegments()),
                ):
                    # If we did, update the segment's settings to match and finish the loop
                    if segment.GetLabelValue() == seg_val:
                        # Set its name to match
                        segment.SetName(seg_name)

                        # Set its color to match
                        rgb_string = seg_color.lstrip("#")
                        rgb = (int(rgb_string[i : i + 2], 16) / 255 for i in (0, 2, 4))
                        segment.SetColor(*rgb)

                        # End the loop early, marking this segment config as having been found
                        was_found = True
                        continue

                # If we never found a matching segment, track it for later
                if not was_found:
                    missing_segments.append(segment_config)

            # Create any missing segments
            for segment_config in missing_segments:
                seg_val = segment_config.get(
                    ExtendedSegmentationResourceConfig.VALUE_KEY
                )
                seg_color = segment_config.get(
                    ExtendedSegmentationResourceConfig.COLOR_KEY
                )
                seg_name = segment_config.get(
                    ExtendedSegmentationResourceConfig.NAME_KEY
                )

                # Generate a new empty segment to hold everything in
                segment_id = segmentation.AddEmptySegment("", seg_name)
                segment = segmentation.GetSegment(segment_id)

                # Set its color to match
                rgb_string = seg_color.lstrip("#")
                rgb = (int(rgb_string[i : i + 2], 16) / 255 for i in (0, 2, 4))
                segment.SetColor(*rgb)

                # Set its label value
                segment.SetLabelValue(seg_val)

    def _create_new_segmentation(self, name: str):
        # Create the new node
        new_node = create_empty_segmentation_node(
            name,
            reference_volume=self.primary_volume_node,
            scene=self.scene,
        )

        # Track it for later reference
        self.segmentation_keys.append(name)
        self.segmentation_nodes[name] = new_node

        # TODO Add it to this unit's subject as well

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
        # Use our custom resource types
        return cls.RESOURCE_TYPES
