import itertools
from pathlib import Path
from typing import Optional

import slicer

from CARTLib.core.DataUnitBase import DataUnitBase
from CARTLib.utils.data import (
    parse_volumes,
    parse_markups,
    parse_segmentations,
    create_subject,
    load_segmentation,
    load_markups,
    load_volume
)
from CARTLib.utils.layout import LayoutHandler, Orientation


class CARTStandardUnit(DataUnitBase):
    """
    A DataUnit instance which imports volumes, segmentations, and markup files
    in a standardized way. Also provides some convenience functionality, such as
    managing the currently viewed orientation(s) of the data unit's contents
    within Slicer's graphical viewer.
    """

    COMPLETED_KEY = "completed"

    DEFAULT_ORIENTATION = Orientation.AXIAL

    def __init__(
        self,
        case_data: dict[str, str],
        data_path: Path,
        scene: slicer.vtkMRMLScene = slicer.mrmlScene,

    ) -> None:
        super().__init__(case_data, data_path, scene)

        # The primary volume acts as the "reference" co-ordinate system + orientation
        # for all other volumes, segmentation, and markups
        self.primary_volume_key: str = ""

        self.volume_keys: list[str]
        self.volume_paths: dict[str, Path]
        self.primary_volume_key: str
        self.volume_keys, self.volume_paths, self.primary_volume_key = parse_volumes(
            case_data, data_path
        )
        self.volume_nodes: dict[str, slicer.vtkMRMLScalarVolumeNode] = dict()

        # Segmentation-related parameters
        self.segmentation_keys: list[str]
        self.segmentation_paths: dict[str, Path]
        self.segmentation_keys, self.segmentation_paths, _ = (
            parse_segmentations(case_data, data_path))
        self.segmentation_nodes: dict[str, slicer.vtkMRMLSegmentationNode] = dict()

        # Markup-related parameters
        self.markup_keys: list[str]
        self.markup_paths: dict[str, Path]
        self.markup_keys, self.markup_paths = parse_markups(case_data, data_path)
        self.markup_nodes: dict[str, slicer.vtkMRMLMarkupsFiducialNode] = dict()

        # Load everything into memory
        self._initialize_resources()

        # Create a subject associated with this data unit
        self.hierarchy_node = scene.GetSubjectHierarchyNode()
        self.subject_id = create_subject(
            self.uid,
            *self.segmentation_nodes.values(),
            *self.volume_nodes.values(),
            *self.markup_nodes.values(),
        )

        self.is_complete = case_data.get(self.COMPLETED_KEY, False)

        # Layout manager for this data unit; as it has MRML nodes, it needs to be
        # cleaned up on a per-unit basis.
        self.layout_handler: LayoutHandler = LayoutHandler(
            list(self.volume_nodes.values()),
            primary_volume_node=self.primary_volume_node,
            orientation=self.DEFAULT_ORIENTATION,
        )

    def set_orientation(self, ori: Orientation):
        # Update our layout to match
        self.layout_handler.set_orientation(ori)

    def to_dict(self) -> dict[str, str]:
        """Serialize back to case_data format."""
        output = {key: self.case_data[key] for key in self.volume_keys}
        output.update({key: self.case_data[key] for key in self.segmentation_keys})
        output.update({key: self.case_data[key] for key in self.markup_keys})
        output[self.COMPLETED_KEY] = self.is_complete
        return output

    def focus_gained(self) -> None:
        """Show all volumes and segmentation when this unit gains focus."""
        # Reveal all the data nodes again
        for node in itertools.chain(
            self.volume_nodes.values(),
            self.segmentation_nodes.values(),
            self.markup_nodes.values(),
        ):
            node.SetDisplayVisibility(True)
            node.SetSelectable(True)
            node.SetHideFromEditors(False)

        self._set_subject_shown(True)

    def focus_lost(self) -> None:
        """Hide all volumes and segmentation when focus is lost."""
        for node in itertools.chain(
            self.volume_nodes.values(),
            self.segmentation_nodes.values(),
            self.markup_nodes.values(),
        ):
            node.SetDisplayVisibility(False)
            node.SetSelectable(False)
            node.SetHideFromEditors(True)

        self._set_subject_shown(False)

    def clean(self) -> None:
        """Clean up the hierarchy node and its children."""
        super().clean()

        # If we are bound to a subject, remove it from the scene
        if self.subject_id is not None:
            self.hierarchy_node.RemoveItem(self.subject_id)

        # Ensure the layout handler is cleaned up as well
        self.layout_handler.clean()

    def validate(self) -> None:
        """
        Ensure that all discovered volume keys and the segmentation key
        refer to existing files.
        """
        for key in self.volume_keys:
            self.validate_key_is_file(key)
        for key in self.segmentation_keys:
            if key is not None:
                self.validate_key_is_file(key)

    def validate_key_is_file(self, key: str) -> None:
        """
        Confirm that `case_data[key]` exists, is a path under data_path,
        and refers to a file.
        """
        rel_path = self.case_data.get(key)
        # If the path wasn't specified, we assume the user wants it skipped/created
        if not rel_path:
            return
        # If there was a path, ensure it exists and is a file
        full_path = self.data_path / rel_path
        if not full_path.exists():
            raise ValueError(f"Path for '{key}' does not exist: {full_path}")
        if not full_path.is_file():
            raise ValueError(f"Path for '{key}' is not a file: {full_path}")

    def _initialize_resources(self) -> None:
        """
        Load volume nodes and segmentation nodes, align geometry,
        and register under a single subject in the hierarchy.
        """
        self._init_volume_nodes()
        self._init_segmentation_nodes()
        self._init_markups_nodes()

    def _init_volume_nodes(self) -> None:
        """
        Load each volume path into a volume node, name it,
        store in resources, and identify the primary.
        """
        for key, path in self.volume_paths.items():
            # If the volume is blank, skip it
            if path is None:
                continue
            # Attempt to load the volume and track it
            node = load_volume(path)
            node.SetName(f"{self.uid}_{key}")
            self.volume_nodes[key] = node
            self.resources[key] = node

            # If this is our primary volume, track it outright for ease of reference
            if key == self.primary_volume_key:
                self.primary_volume_node = node

    def _init_segmentation_nodes(self) -> None:
        """
        For each segmentation key, load if file exists.
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
            if seg_path and seg_path.exists():
                # Try to load the segmentation first
                node = load_segmentation(seg_path)
            else:
                # If that fails, skip over it
                continue

            # Set the name of the node, and align it to our primary volume
            node.SetName(f"{self.uid}_{key}")
            node.SetReferenceImageGeometryParameterFromVolumeNode(
                self.primary_volume_node
            )

            # Apply a unique color to all segments within the segmentation
            for segment_id in node.GetSegmentation().GetSegmentIDs():
                print(f"Setting color for segment '{segment_id}' in '{key}'.")
                segment = node.GetSegmentation().GetSegment(segment_id)

                # TODO MAKE THIS COLOR SETTING A UTIL FUNCTION AND MORE CONFIGURABLE
                # Get the corresponding color, w/ Alpha stripped from it
                segmentation_color = color_table.GetTableValue(c_idx)[:-1]
                segment.SetColor(*segmentation_color)

                # Increment the color index
                c_idx += 1
            self.segmentation_nodes[key] = node
            self.resources[key] = node

    def _init_markups_nodes(self) -> None:
        """
        Load each markup path into a markups node, name it,
        store in resources, and identify the primary.
        """
        for key, path in self.markup_paths.items():
            # If the markup was blank, skip it
            if path is None:
                continue
            # Try to load all markups from the file
            nodes = load_markups(path)
            for i, node in enumerate(nodes):
                if not isinstance(node, slicer.vtkMRMLMarkupsFiducialNode):
                    raise TypeError(
                        f"Expected a MarkupsFiducialNode, got {type(node)} for key {key}"
                    )
                c_name = node.GetName()
                node.SetName(f"{self.uid}_{c_name}_{key}_{i}")
                self.markup_nodes[f"{key}_{i}"] = node
                self.resources[f"{key}_{i}"] = node

    def _set_subject_shown(self, new_state: bool) -> None:
        """
        Expand or collapse the subject hierarchy group.
        """
        if self.subject_id is not None:
            self.hierarchy_node.SetItemExpanded(self.subject_id, new_state)
            self.hierarchy_node.SetItemDisplayVisibility(self.subject_id, new_state)

