from pathlib import Path

import slicer


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
    slicer.mrmlScene.RemoveNode(markups_node)


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
