from pathlib import Path
from typing import Optional

import slicer
from CARTLib.core.DataUnitBase import DataUnitBase
from CARTLib.utils.data import load_segmentation, load_volume, create_subject
from CARTLib.utils.layout import LayoutHandler, Orientation


class MultiContrastSegmentationEvaluationDataUnit(DataUnitBase):
    """
    DataUnit for segmentation evaluation supporting any number of volumes.
    Dynamically discovers all case_data keys containing "volume", loads them,
    and uses one as the primary for geometry alignment.
    """

    SEGMENTATION_KEY = "segmentation"
    COMPLETED_KEY = "completed"
    COMPLETED_BY_KEY = "completed_by"

    DEFAULT_ORIENTATION = Orientation.AXIAL

    def __init__(
        self,
        case_data: dict[str, str],
        data_path: Path,
        scene: Optional[slicer.vtkMRMLScene] = slicer.mrmlScene,
    ) -> None:
        super().__init__(case_data, data_path, scene)

        # --- Discover volume and segmentation keys ---
        self.volume_keys = [k for k in case_data if "volume" in k.lower()]
        if not self.volume_keys:
            raise ValueError(f"No volume keys found in case_data for case {self.uid}")

        self.segmentation_keys = [k for k in case_data if "seg" in k.lower()]
        # Fallback to a single default key if none found
        if not self.segmentation_keys:
            self.segmentation_keys = [self.SEGMENTATION_KEY]
            self._created_empty_by_default = True
        else:
            self._created_empty_by_default = False

        # --- Determine primaries ---
        self.primary_volume_key = next(
            (k for k in self.volume_keys if "primary" in k.lower()),
            self.volume_keys[0],
        )
        self.NO_PRIMARY_SEGMENTATION_KEY: bool = False
        # DONT LOVE THIS LOGIC,
        # Want to handle ANY NUMBER of segmentations
        # If no segmentation keys are found, we will use the default SEGMENTATION_KEY and create an empty segmentation node.
        # If any segmentation keys are found, we will use them.
        # -- If no primary segmentation key is found, we will use the first segmentation key as the primary.
        if not self.segmentation_keys:
            # If no segmentation keys, use the primary volume key as a fallback
            self.segmentation_keys = [self.self.SEGMENTATION_KEY]
            self.NO_PRIMARY_SEGMENTATION_KEY = True
        self.primary_segmentation_key = next(
            (k for k in self.segmentation_keys if "primary" in k.lower()),
            self.segmentation_keys[0],
        )

        # --- Build file paths ---
        self.volume_paths: dict[str, Path] = {
            k: data_path / case_data[k] for k in self.volume_keys
        }
        self.segmentation_paths: dict[str, Path] = {
            k: data_path / case_data.get(k, "") for k in self.segmentation_keys
        }

        # --- Node storage ---
        self.volume_nodes: dict[str, slicer.vtkMRMLScalarVolumeNode] = {}
        self.segmentation_nodes: dict[str, slicer.vtkMRMLSegmentationNode] = {}
        self.primary_volume_node: Optional[slicer.vtkMRMLScalarVolumeNode] = None
        self.primary_segmentation_node: Optional[slicer.vtkMRMLSegmentationNode] = None

        # subject hierarchy
        self.hierarchy_node = scene.GetSubjectHierarchyNode()
        self.subject_id: Optional[int] = None

        self.is_complete = case_data.get(self.COMPLETED_KEY, False)

        # --- Load everything ---
        self._initialize_resources()

        # Layout manager for this data uni; as it has MRML nodes, it needs to be cleaned
        #  up on a per-unit basis.
        self.layout_handler: LayoutHandler = LayoutHandler(
            list(self.volume_nodes.values()),
            self.DEFAULT_ORIENTATION,
        )

    def set_orientation(self, ori: Orientation):
        # Update our layout to match
        self.layout_handler.set_orientation(ori)

    def to_dict(self) -> dict[str, str]:
        """Serialize back to case_data format."""
        output = {key: self.case_data[key] for key in self.volume_keys}
        output.update({key: self.case_data[key] for key in self.segmentation_keys})
        output[self.COMPLETED_KEY] = self.is_complete
        return output

    def focus_gained(self) -> None:
        """Show all volumes and segmentation when this unit gains focus."""
        # Reveal all the data nodes again
        for node in self.volume_nodes.values():
            node.SetDisplayVisibility(True)
        for node in self.segmentation_nodes.values():
            node.SetDisplayVisibility(True)
            if not node == self.primary_segmentation_node:
                # TODO This should be configurable and a button to toggle visibility of non primary segmentations
                node.SetSegementOpacity(0.3)  # Dim non-primary segmentations
        self._set_subject_shown(True)

    def focus_lost(self) -> None:
        """Hide all volumes and segmentation when focus is lost."""
        for node in self.volume_nodes.values():
            node.SetDisplayVisibility(False)
        for node in self.segmentation_nodes.values():
            node.SetDisplayVisibility(False)
        self._set_subject_shown(False)

    def clean(self) -> None:
        """Clean up the hierarchy node and its children."""
        super().clean()

        # If we are bound to a subject, remove it from the scene
        if self.subject_id is not None:
            self.hierarchy_node.RemoveItem(self.subject_id)

        # Ensure the layout handler is cleaned up as well
        self.layout_handler.clean()

    def _validate(self) -> None:
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
        Confirm that case_data[key] exists, is a path under data_path,
        and refers to a file.
        """
        rel_path = self.case_data.get(key)
        if not rel_path:
            raise ValueError(f"Case {self.uid} missing required entry '{key}'.")
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
        primary_vol = self._init_volume_nodes()
        primary_seg = self._init_segmentation_nodes()

        # Align segmentation to volume
        primary_seg.SetReferenceImageGeometryParameterFromVolumeNode(primary_vol)

        # Group under one hierarchy item
        self.subject_id = create_subject(
            self.uid, primary_seg, *self.volume_nodes.values()
        )

    def _init_volume_nodes(self) -> slicer.vtkMRMLScalarVolumeNode:
        """
        Load each volume path into a volume node, name it,
        store in resources, and identify the primary.
        """
        for key in self.volume_keys:
            path = self.volume_paths[key]
            node = load_volume(path)
            node.SetName(f"{self.uid}_{key}")
            self.volume_nodes[key] = node
            self.resources[key] = node
            if key == self.primary_volume_key:
                self.primary_volume_node = node
        return self.primary_volume_node  # primary

    def _init_segmentation_nodes(self) -> slicer.vtkMRMLSegmentationNode:
        """
        For each segmentation key, load if file exists; otherwise create empty node.
        Then pick the primary segmentation.
        """
        for key in self.segmentation_keys:
            seg_path = self.segmentation_paths.get(key)
            if seg_path and seg_path.exists():
                node = load_segmentation(seg_path)
            else:
                # create an empty segmentation node
                node = slicer.vtkMRMLSegmentationNode()
                node.SetName(f"{self.uid}_{key}")
                self.scene.AddNode(node)
            self.segmentation_nodes[key] = node
            self.resources[key] = node

        self.primary_segmentation_node = self.segmentation_nodes[
            self.primary_segmentation_key
        ]
        return self.primary_segmentation_node  # type: ignore

    def _set_subject_shown(self, new_state: bool) -> None:
        """
        Expand or collapse the subject hierarchy group.
        """
        if self.subject_id is not None:
            self.hierarchy_node.SetItemExpanded(self.subject_id, new_state)
            self.hierarchy_node.SetItemDisplayVisibility(self.subject_id, new_state)
