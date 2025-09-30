# CART Core Components

The files within this directory contain the components that nearly (if not all) tasks within CART will use. This includes cohort management, data unit creation and iteration, Slicer layout handing, and the Abstract Base Classes (ABCs) that all tasks and their data units should inherit from.


## Table of Contents

## Table of Contents

* [Slicer Layout Handling](#slicer-layout-handling)
  * [The Orientation Flag](#the-orientation-flag)
  * [`LayoutHandler`](#the-layouthandler)

## Slicer Layout Handling

The contents of `LayoutManagement.py` are for handling how the nodes in a given case should be displayed to the user in the Slicer viewer. For the most part, CART handles this for you (via a unified orientation selection widget and `LayoutHandler` instance), but you can interact with and/or subclass each of these to enable customized layouts for your task.

### The Orientation Flag

This enum is used by CART to track what orientation(s) you want to be displayed to the user. It can be one of three "base" values:

* `AXIAL`: Represents the Axial plane
* `SAGITTAL`: Represents the Sagittal plane
* `CORONAL`: Represents the Coronal plane

The `Orientation` enum is a [flag-type enum](https://docs.python.org/3/library/enum.html#enum.Flag); this allows us to "combine" orientations using the `|` operator. The resulting orientations are then treated as all the "base" orientations used to create it:

```python
>>> axial_and_coronal = Orientation.AXIAL | Orientation.CORONAL
>>> print(Orientation.AXIAL in axial_and_coronal) 
True
>>> print(Orientation.SAGITTAL in axial_and_coronal)
False
```

These "combined" orientations are used by the LayoutHandler (detailed below) to denote when the user wants multiple orientations displayed simultaneously; it is not bound to that use, however, and can be re-used in your own tasks as you see fit.

### The `LayoutHandler`

The `LayoutHandler` class is responsible for determining the best layout to display the set of volume nodes (and, by extension, their associated segmentation and markups). By default, CART creates one itself and relies on it to generate new layouts for each data unit (or change the existing layout to match the users preference). This default handler relies on three things to accomplish this:

* A set of volume nodes that it should make displays for.
* A "primary" volume node; this is used as the reference for the purposes of determining where overlays (segmentations and markups) will be displayed. 
  * If none is provided, the first segmentation node is used.
* An `Orientation` flag, containing the view orientation(s) that should be displayed.

It can then "apply" its layout to the Slicer scene; for the default handler, this results in 1 panel per combination of volume node and orientation (Axial, Sagittal, and/or Coronal). 

You can change the orientation post-init with the `set_orientation` function; this invalidates the current layout XML, and will require it be re-applied manually for the changes to take effect in Slicer.
