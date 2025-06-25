from abc import abstractmethod
import logging
import os
import re

import vtk, qt, ctk, slicer


class SegmentationBackendBase(object):

  def __init__(self):
    self.logger = logging.getLogger('SlicerCaseIterator.SegmentationBackend')

  @abstractmethod
  def enter_module(self, master_image_node, master_mask_node):
    """
    This function is called when the segmentation module should be entered, either by switching to, or calling the
    correct "enter" function.

    :param master_image_node: Volume node reflecting the master volume loaded
    :param master_mask_node: Node reflecting the master mask loaded (can be None)
    """

  @abstractmethod
  def exit_module(self):
    """
    This function is called when the segmentation module should be exited, by calling the
    correct "exit" function.
    """

  def observe_mask_node(self, node):
    pass

  def remove_mask_node_observers(self):
    pass

  @abstractmethod
  def loadMask(self, mask_path, ref_image=None):
    """

    :param mask_path: string pointing to the mask file that should be loaded
    :param ref_image: master volume node that should serve as reference for the loaded mask
    :return: node representing the loaded mask, None if loading failed.
    """

  @abstractmethod
  def newMask(self, ref_image, node_name=None):
    """

    :param ref_image: master volume node that should serve as geometric reference for the new mask
    :param node_name: string specifying the name of the new node. If None, name is derived from ref_image node name
    :return: new mask node
    """

  @abstractmethod
  def getMaskExtension(self):
    """

    :return: string specifying the extension that should be appended to saved masks
    """

  @abstractmethod
  def getMaskNodes(self):
    """

    :return: iterable of Slicer nodes that need to be saved by the iterator
    """


class EditorBackend(SegmentationBackendBase):
  def enter_module(self, master_image_node, master_mask_node):
    """
    This function is called when the segmentation module should be entered, either by switching to, or calling the
    correct "enter" function.

    :param master_image_node: Volume node reflecting the master volume loaded
    :param master_mask_node: Node reflecting the master mask loaded (can be None)
    """
    if slicer.util.selectedModule() != 'Editor':
      slicer.util.selectModule('Editor')
    else:
      slicer.modules.EditorWidget.enter()

    # Explictly set the segmentation and master volume nodes
    EditorWidget = slicer.modules.editor.widgetRepresentation().self()
    if master_mask_node is not None:
      EditorWidget.setMergeNode(master_mask_node)
    EditorWidget.setMasterNode(master_image_node)

  def exit_module(self):
    """
    This function is called when the segmentation module should be exited, by calling the
    correct "exit" function.
    """
    if slicer.util.selectedModule() == 'Editor':
      slicer.modules.EditorWidget.exit()

  def loadMask(self, mask_path, ref_image=None):
    """

    :param mask_path: string pointing to the mask file that should be loaded
    :param ref_image: master volume node that should serve as reference for the loaded mask
    :return: node representing the loaded mask, None if loading failed.
    """
    if mask_path is None:
      return None

    # Check if the file actually exists
    if not os.path.isfile(mask_path):
      self.logger.warning('Segmentation file %s does not exist, skipping...', mask_path)
      return None

    # Determine if file is segmentation based on extension
    file_base, ext = os.path.splitext(mask_path)

    isSegmentation = file_base.endswith('.seg')

    # Try to load the mask
    if isSegmentation:
      self.logger.debug('Loading segmentation and converting to labelmap')
      # split off .seg
      file_base = os.path.splitext(file_base)[0]

      ma_node = slicer.util.loadSegmentation(mask_path)

      label_node = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLLabelMapVolumeNode')
      slicer.modules.segmentations.logic().ExportAllSegmentsToLabelmapNode(ma_node, label_node)

      slicer.mrmlScene.RemoveNode(ma_node)
      ma_node = label_node

      # Add a storage node for this segmentation node
      store_node = label_node.CreateDefaultStorageNode()
      slicer.mrmlScene.AddNode(store_node)
      label_node.SetAndObserveStorageNodeID(store_node.GetID())

      store_node.SetFileName('%s.nrrd' % file_base)

      # UnRegister the storage node to prevent a memory leak
      store_node.UnRegister(None)
    else:
      self.logger.debug('Loading labelmap')
      # If not segmentation, then load as labelmap then convert to segmentation
      ma_node = slicer.util.loadLabelVolume(mask_path)

    # Use the file basename as the name for the newly loaded segmentation node
    ma_node.SetName(file_base)

    return ma_node

  def newMask(self, ref_image, node_name=None):
    """

    :param ref_image: master volume node that should serve as geometric reference for the new mask
    :param node_name: string specifying the name of the new node. If None, name is derived from ref_image node name
    :return: new mask node
    """

  def getMaskExtension(self):
    """

    :return: string specifying the extension that should be appended to saved masks
    """
    return '.nrrd'

  def getMaskNodes(self):
    """

    :return: iterable of Slicer nodes that need to be saved by the iterator
    """
    return slicer.util.getNodesByClass('vtkMRMLLabelMapVolumeNode')


class SegmentEditorBackend(SegmentationBackendBase):
  def __init__(self):
    super(SegmentEditorBackend, self).__init__()
    self.mask_node_observers = []
    self.prefixes = {}

  def enter_module(self, master_image_node, master_mask_node):
    """
    This function is called when the segmentation module should be entered, either by switching to, or calling the
    correct "enter" function.

    :param master_image_node: Volume node reflecting the master volume loaded
    :param master_mask_node: Node reflecting the master mask loaded (can be None)
    """
    if slicer.util.selectedModule() != 'SegmentEditor':
      slicer.util.selectModule('SegmentEditor')
    else:
      slicer.modules.SegmentEditorWidget.enter()

    # Explictly set the segmentation and master volume nodes
    segmentEditorWidget = slicer.modules.segmenteditor.widgetRepresentation().self().editor
    if master_mask_node is not None:
      segmentEditorWidget.setSegmentationNode(master_mask_node)
    segmentEditorWidget.setSourceVolumeNode(master_image_node)

  def exit_module(self):
    """
    This function is called when the segmentation module should be exited, by calling the
    correct "exit" function.
    """
    if slicer.util.selectedModule() == 'SegmentEditor':
      slicer.modules.SegmentEditorWidget.exit()

  def observe_mask_node(self, node):
    if node is None:
      self.logger.debug("No node to observe passed. Skipping adding observer")
      return

    # Observe the SegmentAdded event to enable changing the auto-naming behaviour
    segmentation = node.GetSegmentation()
    self.mask_node_observers.append((node, segmentation.AddObserver(segmentation.SegmentAdded, self.onSegmentAdded)))

    # Store the prefix we want to use, as the event only passes the segmentation,
    # not the segmentationNode
    self.prefixes[segmentation.GetAddressAsString(None)] = node.GetName()

  def remove_mask_node_observers(self):
    if len(self.mask_node_observers) == 0:
      self.logger.debug("Not observing any node!")

    for node, obs in self.mask_node_observers:
      segmentation = node.GetSegmentation()
      segmentation.RemoveObserver(obs)
      seg_addr = segmentation.GetAddressAsString(None)
      if seg_addr in self.prefixes:
        del self.prefixes[seg_addr]
    self.mask_node_observers = []

  def onSegmentAdded(self, caller, event):
    # caller is vtkSegment, not vtkMRMLSegmentationNode!
    try:
      # Get the last added segment, and check if it is a new empty segment with standard name
      new_segment = caller.GetNthSegment(caller.GetNumberOfSegments() - 1)
      name_match = re.match(r'Segment_(?P<seg_no>\d+)', new_segment.GetName())
      seg_addr = caller.GetAddressAsString(None)  # Needed to look up prefix

      if seg_addr not in self.prefixes:
        self.logger.debug('Segment added, but segmentation does not have a prefix set. Skipping setting name')
      elif name_match is None:
        self.logger.debug('Segment added, but non-standard name. Possibly imported segment. Skipping setting name')
      else:
        new_name = self.prefixes[seg_addr] + '_%s' % name_match.groupdict()['seg_no']
        self.logger.debug('Segment added, Auto-setting name to %s', new_name)
        new_segment.SetName(new_name)
    except Exception:
      self.logger.warning('Error setting new name for segment!', exc_info=True)

  def loadMask(self, mask_path, ref_image=None):
    """

    :param mask_path: string pointing to the mask file that should be loaded
    :param ref_image: master volume node that should serve as reference for the loaded mask
    :return: node representing the loaded mask, None if loading failed.
    """
    if mask_path is None:
      return None

    # Check if the file actually exists
    if not os.path.isfile(mask_path):
      self.logger.warning('Segmentation file %s does not exist, skipping...', mask_path)
      return None

    file_base = os.path.splitext(os.path.basename(mask_path))[0]

    # Determine if file is segmentation based on extension
    isSegmentation = os.path.splitext(mask_path)[0].endswith('.seg')
    # Try to load the mask
    if isSegmentation:
      self.logger.debug('Loading segmentation')
      # split off .seg
      file_base = os.path.splitext(file_base)[0]

      ma_node = slicer.util.loadSegmentation(mask_path)
    else:
      self.logger.debug('Loading labelmap and converting to segmentation')
      # If not segmentation, then load as labelmap then convert to segmentation
      ma_node = slicer.util.loadLabelVolume(mask_path)

      seg_node = slicer.vtkMRMLSegmentationNode()
      slicer.mrmlScene.AddNode(seg_node)
      if ref_image is not None:
        seg_node.SetReferenceImageGeometryParameterFromVolumeNode(ref_image)

      slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(ma_node, seg_node)
      slicer.mrmlScene.RemoveNode(ma_node)
      ma_node = seg_node

      # Add a storage node for this segmentation node
      file_base, ext = os.path.splitext(mask_path)
      store_node = seg_node.CreateDefaultStorageNode()
      slicer.mrmlScene.AddNode(store_node)
      seg_node.SetAndObserveStorageNodeID(store_node.GetID())

      store_node.SetFileName('%s.seg.nrrd' % file_base)

      # UnRegister the storage node to prevent a memory leak
      store_node.UnRegister(None)

    # Use the file basename as the name for the newly loaded segmentation node
    ma_node.SetName(file_base)
    return ma_node

  def newMask(self, ref_image, node_name=None):
    """

    :param ref_image: master volume node that should serve as geometric reference for the new mask
    :param node_name: string specifying the name of the new node. If None, name is derived from ref_image node name
    :return: new mask node
    """
    seg_node = slicer.vtkMRMLSegmentationNode()
    slicer.mrmlScene.AddNode(seg_node)
    seg_node.GetSegmentation().AddEmptySegment()
    seg_node.SetReferenceImageGeometryParameterFromVolumeNode(ref_image)
    if node_name is None:
      seg_node.SetName('%s_segmentation' % ref_image.GetName())
    else:
      seg_node.SetName(node_name)
    return seg_node

  def getMaskExtension(self):
    """

    :return: string specifying the extension that should be appended to saved masks
    """
    return '.seg.nrrd'

  def getMaskNodes(self):
    """

    :return: iterable of Slicer nodes that need to be saved by the iterator
    """
    return slicer.util.getNodesByClass('vtkMRMLSegmentationNode')
