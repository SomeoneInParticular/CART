# Standardized CART Utilities

This package contains a number of utilities or structures which have a common enough use case (or have an unintuitive/difficult implementation) to be standardized across most CART applications. This readme provides an overview of the notable utilities provided, with a brief description of each.

## Table of Contents

* [BIDS Management](#bids-management)
* [Configuration Management](#configuration-management)
* [Data Handling](#data-handling)
  * [The CART Standard Format](#the-cart-standard-format) 
  * [Manual I/O Handling](#manual-io-handling)

## BIDS Management

Placed within `bids.py`, provides utilities for handling data organized in the BIDS format. Notable functions include:

### `check_pseudo_bids` 

Validates that the passed directory is organized in a BIDS-like manner. Checks for the presence of at least one `sub-` directory, and a `derivatives` directory.
### `generate_blank_cohort`

Generate a cohort file template, with one case row per `sub-` directory within the provided path.

### `fetch_bids_subject_map`

Generates a map of case (subject) IDs to the files within the BIDS directory that should be associated with them.

## Configuration Management

Placed within `config.py`, this provides a number of standard structures for managing, saving, and loading configuration options in CART. Notable elements include:

### `DictBackedConfig`

As the name suggests, this is a configuration handled back by a Python dictionary. For it to work in the context of CART's profiles, it has two attributes of note:

* `parent`: Another `DictBackedConfig` that this config should be stored within. 
  * In most cases, this will be the currently active profile's configuration passed during task initialization, making this a "child" of that profile.
  * If you do not provide one, you need to override `save_without_parent` to define how this configuration should be saved!
* `config_label`: A label that the parent config will use to track this config within itself. Can be overridden by passing a different label during construction (see `ProfileConfig` in [`config.py`](config.py) for an example of when that may be warranted.)

By using this class as a configuration manager for your task, you get the following for free:

* Allows you to mark when its contents has changed, which hooks into the GUI component (see [`ConfigDialog`](#configdialog) below)
* Handles access to the backing dictionary and its contents, including lazily evaluated defaults with `get_or_default`.
  * For ease of access, we use Python `properties` to add/access configuration entries within the `_backing_dict` dictionary.
* Ensures configuration values are saved and loaded correctly throughout CART's runtime.

### `ConfigDialog`

An abstract QT Dialog class which provides common utilities for interacting with a bound `DictBackedConfig` instance. You should subclass this to build the GUI yourself, but doing so provides you the following for free:

* Standardized set of "reset", "confirm", and "cancel" buttons.
* "Are you sure?" confirmation prompt if the user tries to cancel out of the dialog with saved changes.
* Implicit synchronization with the state of CART and its current configuration settings.

## Data Handling

Provides wrappers for common data I/O operations in Slicer, adjusted to work effectively in the context of CART's iterative framework. Most utilities also follow the "CART Standard Format" if they are parsing a cohort file; this format is detailed below:

### The CART Standard Format

All example tasks provided by CART follow the "CART Standard" for cohort formatting. This standard can be summarized as follows:

* Columns which contain `volume` are assumed to be a path to a volume file. 
  * The first such volume is made the "reference" volume for the case, with its co-ordinate system and orientation being used to place and orient all other volumes, segmentations, and markups.
* Columns which contain `segmentation` are assumed to be a path to a segmentation file.
* Columns which contain `markup` are assumed to be a path to a Slicer markup JSON file.

If you want your data unit to follow this standard (and load each column according to its detected type automatically), you can subclass the `CARTStandardUnit` to do so. If you want to follow the standard, but handling the loading of each file yourself, you can instead use the `parse_volumes`, `parse_segmentations`, and `parse_markups` functions to identify Volume, Segmentation, and Markup columns, respectively.

### Manual I/O Handling

If your Task needs your cohort to not follow the CART Standard Format, you should still consider using the following I/O utilities for reading/writing common file types. Most are wrappers for common Slicer I/O operations, modified (or with additional checks) to ensure they will run nicely within CART's iterative framework.

#### Volume I/O

Volumes can be loaded in any format currently supported by Slicer (except DICOM, due to its folder-based structure) via the `load_volume` function. Currently only supports saving volumes to _NiFTI_ format with `save_volume_to_nifti`.

#### Segmentation I/O

Like volumes, can load any format supported by Slicer. Can be loaded as a "label" (via `load_label`) or a "segmentation" (via `load_segmentation`). Label files are saving identically to volumes (with `save_volume_to_nifti`), with segmentations being saved using `save_segmentation_to_nifti` instead.

You can also create a "blank" segmentation using the `create_empty_segmentation_node` function; this can be useful for tasks where you want the user to create a segmentation themselves, rather than edit an existing one.

#### Markups I/O

Supports markups stored in the Slicer `.json` format; load with `load_markups`, save with `save_markups_to_json`. What is loaded/saved depends on the type of markup contained within the file; see [the official documentation](https://slicer.readthedocs.io/en/latest/user_guide/modules/markups.html) for more details.

#### Node Grouping

To make managing each data unit's nodes easier, it's often easier to group them into a single "subject" that is hidden/revealed/deleted when needed (rather than doing so for each MRML node manually). If you have a list/set of nodes you want to group, you can use the `create_subject` to streamline this process.
