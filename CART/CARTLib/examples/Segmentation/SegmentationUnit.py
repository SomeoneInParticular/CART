from pathlib import Path

import slicer

from CARTLib.utils.data import CARTStandardUnit, create_empty_segmentation_node

class SegmentationUnit(CARTStandardUnit):
    """
    DataUnit for the segmentation task. Extends the CART
    Standard Unit to support custom segmentations.
    """

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

    def add_custom_segmentation(self, name: str):
        """
        Create a new "custom" segmentation for this data unit;
        these segmentations allow users to "add" new elements
        to the dataset
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
            new_node.GetSegmentation().AddEmptySegment(name, "1")

            # Track it for later reference
            self.custom_segmentations[formatted_name] = new_node
            self.segmentation_nodes[formatted_name] = new_node
        except Exception as e:
            # If this fails at any point, clean up the unit from the scene
            if new_node:
                slicer.mrmlScene.RemoveNode(new_node)
            raise e
