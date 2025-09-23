import itertools
from pathlib import Path
from typing import Optional, Any

import slicer

from CARTLib.core.DataUnitBase import DataUnitBase
from CARTLib.utils.layout import Orientation, LayoutHandler


## LOADING ##
def load_volume(path: Path):
    """
    Load a file into Slicer as a Volume.

    Unlike slicer's default utility function, it will hide the volume from view
    by default to better work with CART's iterative DataUnit loading.

    :param path: Path to the file
    """
    # Load the file into a volume node, hidden from view
    return slicer.util.loadVolume(path, {"show": False})


def load_label(path: Path):
    """
    Load a file into Slicer as a LabelVolume.

    Unlike slicer's default utility function, it will hide the label from view
    by default to better work with CART's iterative DataUnit loading.

    :param path: Path to the file
    """
    # Load the file into a label node, hidden from view
    return slicer.util.loadLabelVolume(path, {"show": False})


def load_segmentation(path: Path):
    """
    Load a file into Slicer as a Segmentation.

    Unlike slicer's default utility function, it will hide the segmentation from
    view by default to better work with CART's iterative DataUnit loading.

    :param path: Path to the file
    """
    # We first have to load it as a label volume
    label_node = load_label(path)

    # Then pass its contents to a segmentation node
    scene = slicer.mrmlScene
    segment_node = scene.AddNewNodeByClass("vtkMRMLSegmentationNode")
    slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(
        label_node, segment_node
    )

    # Hide it from view by default
    segment_node.SetDisplayVisibility(False)

    # Remove the (now redundant) label node from the scene
    scene.RemoveNode(label_node)
    del label_node

    # Return the result
    return segment_node


def load_markups(path: Path) -> list[slicer.vtkMRMLMarkupsFiducialNode]:
    """
    Load a file into Slicer as a Markups node.

    Unlike slicer's default utility function, it will hide the markups from view
    by default to better work with CART's iterative DataUnit loading.

    Also there is a workaround to track all loaded markup nodes
    :param path: Path to the file
    """
    # Load the file into a markups node, hidden from view

    all_fiducials = set(slicer.util.getNodesByClass("vtkMRMLMarkupsFiducialNode"))

    markups_nodes = slicer.util.loadMarkups(
        path
    )  # THIS IS SUPPOSED TO RETURN A LIST if
    # there are multiple nodes in the file
    # THIS DOESNT https://slicer.readthedocs.io/en/latest/developer_guide/slicer.html#slicer.util.loadMarkups
    all_new_fiducials = list(
        set(slicer.util.getNodesByClass("vtkMRMLMarkupsFiducialNode")) - all_fiducials
    )

    print(f"Found {len(all_new_fiducials)} new markups nodes after loading {path}")
    print(f"Fiductrials in the scene: {[node.GetName() for node in all_new_fiducials]}")
    if markups_nodes is None:
        raise ValueError(f"Failed to load markups from {path}")
    if not isinstance(markups_nodes, list):
        markups_nodes = [markups_nodes]

    if all_new_fiducials != markups_nodes:
        print(
            "Warning: The loaded markups returned from slicer.util.loadMarkups does not match the expected new fiducials."
        )
        difference = set(markups_nodes) - set(all_new_fiducials)
        if difference:
            print(f"Difference: {[node.GetName() for node in difference]}")
        markups_nodes = all_new_fiducials

    print(f"Markups nodes: {[node.GetName() for node in markups_nodes]}")
    for markups_node in markups_nodes:

        # Hide the display node as well, if it exists
        displayNode = markups_node.GetDisplayNode()
        if displayNode:
            displayNode.SetVisibility(False)

    return markups_nodes


## SAVING ##
def save_volume_to_nifti(volume_node, path: Path):
    """
    Save a volume node to the specified path.
    """
    slicer.util.saveNode(volume_node, str(path))


def save_segmentation_to_nifti(segment_node, volume_node, path: Path):
    """
    Save a segmentation node's contents to a `.nii` file.

    Much like loading, we can't save segmentations directly. Instead, we need to
    convert it back to a label-type node w/ reference to a volume node first,
    then save that.
    """
    # Convert the Segmentation back to a Label (for Nifti export)
    label_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLabelMapVolumeNode")
    slicer.modules.segmentations.logic().ExportVisibleSegmentsToLabelmapNode(
        segment_node, label_node, volume_node
    )

    # Save the active segmentation node to the desired directory
    slicer.util.saveNode(label_node, str(path))

    # Clean up the label node after so it doesn't pollute the scene
    slicer.mrmlScene.RemoveNode(label_node)


def save_markups_to_json(markups_node, path: Path):
    """
    Save a markups node to the specified path as a JSON file.
    """
    # Use Slicer's utility function to save the markups node
    assert path.name.endswith(".mrk.json"), "Path must end with .mrk.json"
    slicer.util.saveNode(markups_node, str(path))


## ORGANIZATION ##
def create_subject(label: str, *child_nodes):
    # Get Slicer's hierarchy node
    shNode = slicer.mrmlScene.GetSubjectHierarchyNode()

    # Create a new subject with the desired label
    subject_id = shNode.CreateSubjectItem(shNode.GetSceneItemID(), label)

    # Have the new subject "adopt" all provided child nodes
    for n in child_nodes:
        n_id = shNode.GetItemByDataNode(n)
        shNode.SetItemParent(n_id, subject_id)

    # Return the ID for the newly created subject
    return subject_id


def extract_case_keys_by_prefix(
    case_data: dict[str, str], prefix: str, force_present: bool = False
) -> list[str]:
    """
    Extract keys from a case_data dictionary where the given prefix
    appears as a full word (split by "_"), case-insensitively.

    Parameters
    ----------
    case_data : dict[str, str]
        Dictionary containing keys like 'T2w_Volume', 'Lesion_Segmentation', etc.
    prefix : str
        The prefix to match exactly (e.g., "Volume", "Segmentation", "Markup").
    force_present: bool
        Whether to raise an error if no keys match the prefix.

    Returns
    -------
    list[str]
        Keys in case_data that contain the prefix as a full word.

    """
    prefix_lower = prefix.lower()
    keys = [
        k for k in case_data if prefix_lower in (part.lower() for part in k.split("_"))
    ]
    if not keys and force_present:
        raise ValueError(
            f"No keys found with prefix '{prefix}' in case_data: {case_data}"
        )
    return keys


def create_empty_segmentation_node(
    name: str,
    reference_volume: slicer.vtkMRMLScalarVolumeNode,
    scene: Optional[slicer.vtkMRMLScene] = None,
) -> slicer.vtkMRMLSegmentationNode:
    """
    Create an empty segmentation node with proper display node setup.

    # TODO CREATE SUPPORT FOR KWARGS TO PASS TO THE DISPLAY NODE

    Args:
        name: Name for the segmentation node
        reference_volume: Volume node to use for geometry reference
        scene: MRML scene to add the node to (defaults to slicer.mrmlScene)

    Returns:
        Empty segmentation node with display node configured
    """
    if scene is None:
        scene = slicer.mrmlScene

    # Create segmentation node
    seg_node = slicer.vtkMRMLSegmentationNode()
    scene.AddNode(seg_node)
    seg_node.SetName(name)

    # Create and set up display node
    display_node = slicer.vtkMRMLSegmentationDisplayNode()
    scene.AddNode(display_node)
    seg_node.SetAndObserveDisplayNodeID(display_node.GetID())

    # Set reference geometry
    seg_node.SetReferenceImageGeometryParameterFromVolumeNode(reference_volume)

    return seg_node


## COHORT STRATIFICATION ##
def parse_volumes(
    case_data: dict[str, Any], data_path: Path
) -> tuple[list[str], dict[str, Path], str]:
    # Get the keys from the case data
    volume_keys = extract_case_keys_by_prefix(case_data, "Volume", force_present=True)

    # We need at least one volume key; otherwise theirs nothing to reference against
    if len(volume_keys) < 1:
        raise ValueError("At least one feature in the cohort must be a volume!")

    # Parse the volume paths

    volume_paths: dict[str, Optional[Path]] = {
        (k): (data_path / v if (v := case_data.get(k, "")) != "" else None)
        for k in volume_keys
    }

    # We need at least one non-blank path to reference against
    valid_paths: dict[str, Path] = {
        k: v for k, v in volume_paths.items() if v is not None
    }
    if len(valid_paths) < 1:
        raise ValueError(
            f"No valid volumes were found for case '{case_data.get('uid', 'UNKNOWN')}'!"
        )

    # Set the primary volume to reference segmentations against
    # KO: Note that this will select a non-primary volume if all primary volumes are
    #  blank; not the most intuitive, but much better than just crashing
    primary_volume_key = next(
        # Prefer a key explicitly designated as "primary" if possible
        (k for k in valid_paths.keys() if "primary" in k.lower()),
        # Failing that, select the first valid volume instead
        next(iter(valid_paths.keys())),
    )

    # Move the primary key to the front of our list
    volume_keys.remove(primary_volume_key)
    volume_keys = [primary_volume_key, *volume_keys]
    return volume_keys, volume_paths, primary_volume_key


# TODO: Remove the "default fallback"
def parse_segmentations(
    case_data, data_path
) -> tuple[list[str], dict[str, Path]]:
    # Parse our segmentation keys
    segmentation_keys = extract_case_keys_by_prefix(
        case_data, "Segmentation", force_present=False
    )

    # If there were none, end here
    if not segmentation_keys:
        return [], {}

    # Initialize our segmentation paths
    segmentation_paths: dict[str, Path] = {
        (k): (data_path / v if (v := case_data.get(k, "")) != "" else None)
        for k in segmentation_keys
    }
    valid_segmentation_paths = {
        k: v for k, v in segmentation_paths.items() if v is not None
    }
    return segmentation_keys, valid_segmentation_paths


def parse_markups(case_data, data_path) -> tuple[list[str], dict[str, Path]]:
    # TODO Handle Case for allowing a "Primary" Markup even if we dont currently have a need.
    # This would allow us to dry out this code combining all 3 parse_* functions

    # Get our list of
    markup_keys = extract_case_keys_by_prefix(case_data, "Markup", force_present=False)

    # Initialize our markup paths
    markup_paths: dict[str, Path] = {
        (k): (data_path / v if (v := case_data.get(k, "")) != "" else None)
        for k in markup_keys
    }
    valid_markup_paths = {k: v for k, v in markup_paths.items() if v is not None}
    return markup_keys, valid_markup_paths


## "Standard" Data Unit ##
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
        self.segmentation_keys, self.segmentation_paths = parse_segmentations(case_data, data_path)
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
