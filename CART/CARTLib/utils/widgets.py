import slicer

def buildSegmentationEditorWidget():
    """
    Builds a copy of the Segmentation Editor's editor widget for use within a
    task
    """
    # TODO: Fix this "stealing" from the original Segment Editor widget
    return slicer.modules.segmenteditor.widgetRepresentation().self().editor


