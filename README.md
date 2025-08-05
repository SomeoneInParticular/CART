# Case Annotation and Review Tool (CART)

## What is CART?

CART is a module for the 3D slicer program designed to help you manage  iterative analyses, allowing you to focus on implementing and running task you set out to do. Currently, it provides the following capabilities:

* Managing sequential cases (be they patients, sub-studies, or other collections of data).
* Cacheing and memory management.
* User tracking.

A number of features are currently in progress as well, and will be available upon CART's full release:

* Custom task creation and registration.
* Case pre-fetching/deferred loading.
* Per-user + per-task configurations.

## Setting up CART

### Prerequisites

- Slicer v5.8 (other versions might work, without guarantee)

### Installation

Clone this repository somewhere can easily access it. You can do this one of two ways:

1. Downloading the repository from GitHub:
   1. Open the [CART](https://github.com/SomeoneInParticular/CART) repository in your browser.
   2. Click the green "<> Code" drop-down button on the top-right of of the page
   3. Select "Download ZIP"
   4. Choose where you want the resulting file to be placed in the resulting popup
   5. Wait for the download to complete
   6. Once complete, navigate to the `CART-main.zip` file and unzip it (on most OS systems, double-clicking on the file should tell you how to do this)

2. Cloning the repository via `git`:
   1. Open a terminal in a directory of your choice
   2. Run the following command to clone the current `CART` repository:
    ~~~
    git clone git@github.com:SomeoneInParticular/CART.git
    ~~~

### Registering CART in Slicer

0. Open the cloned CART directory you created prior in a file browser
1. Start up Slicer
2. Select `Edit` (top left) > `Application Settings`
3. In the "settings" popup, select `Modules` from the left sidebar
4. Click and drag `CART.py` from the file browser into the "Additional module paths" panel.
5. Click "OK"; Slicer should prompt you that it needs to restart.
6. Restart Slicer

### [Optional] Setting CART as your Default Module

1. Start Slicer
2. Select `Edit` (top left) > `Application Settings`
3. In the "settings" popup, select `Modules` from the left sidebar
4. Select `CART` from the dropdown button labelled "Default startup module"

## Using CART

### Create a user

Under the "User" section, click on the "+" and add your name.

### Cohort File

A cohort file is a CSV file that lists the data to be annotated.

Example of such a file:

```
uid,volume,segmentation
sub-amu05_T2w,sub-amu05/anat/sub-amu05_T2w.nii.gz,derivatives/labels/sub-amu05/anat/sub-amu05_T2w_seg.nii.gz
sub-amu04_T2w,sub-amu04/anat/sub-amu04_T2w.nii.gz,derivatives/labels/sub-amu04/anat/sub-amu04_T2w_seg.nii.gz
...
```

> [!NOTE]  
> The paths are relative for clarity. The root path is indicated under [Data Path](#data-path).


### Data Path

Root path where the dataset is located.

### Task

A task can be segmentation review (ie: already existing segmentation), new segmentation, categorization, etc.. 

A task is associated with a 'cohort file', which configures CART environment for annotation. You can find examples of 
tasks at: [./CART/CARTLib/examples](./CART/CARTLib/examples).

## IDE Set Up

### Source Directories

As both Slicer and CART load libraries into Python's path post-init, most IDEs will not be able to recognize some of the import statements used by our codebase by default.

To fix this, please mark the following directories as "source" folders in the Project's structure:

* `{Slicer Installation Directory}/bin/Python`: exposes that installations versions of VTK, CTK, and QT, along with slicer's own utilities.
* `{This Directory}/CART`; exposes CARTLib and its contents.

## Basic Structure

- **CARTLib**: The main library containing the base classes for defining the standard iterator and Task Workflow.
- **CARTLib/Task**: Contains the base classes for defining a Task.
  - A task is defined as an actionable set of steps that can be taken by a specific user.
  - Tasks Do not load data they are only used to define the GUI and support the user in performing a specific action.
  - Tasks are at the "DataUnit" level, meaning that they are specific to a single DataIO object 
    (e.g. a single row in the cohort csv).
- **CARTLib/DataIO**: Contains the base classes for defining a DataIO.
  - DataIO is used to interface with the cohort csv(Which is an organizational scheme we required to be defined by the user beforehand).
  - DataIO baseclass is used to map a single row of the cohort csv to loaded Slicer Nodes and vice versa.
  - DataIO is used to load the data and save the data.
  - DataIO is used to define the data that is loaded and saved for a specific task.
  - DataIO is at the "DataUnit" level, meaning that it is specific to a single DataIO object 
    (e.g. a single row in the cohort csv).
- **CARTLib/DataManager**: Contains the base classes for defining a DataManager.
  - DataManager is used to interface/ convert the Cohort csv to a list of DataIO objects.
  - DataManager is used to manage the loading and saving of data for a specific 'project' or set of tasks.
  - DataManager is at the "Project" level, meaning that it is specific to a set of tasks and DataIO objects.
  - It is used to create the DataUnits
- **CARTLib/TaskConfig**: Contains the base classes for defining a TaskConfig.
  - TaskConfig is used to define all of the hyperparameters and configurations for a specific 'project' or set of tasks 

Logical Extensions: 
- **CART/SegmentationTask**: A specific task for segmentation. 
- **CART/ClassificationTask**: A specific task for classification.
- **CART/ReviewTask**: A specific task for reviewing existing segmentations or classifications."
- **CARTLib/TaskWorkflow**: Contains the base classes for defining a TaskWorkflow.
- **CARTLib/TaskConfigMaker**: Contains the base classes for defining a TaskWorkflowManager.
- **CARTLib/CSVCohortMaker**: Contains the base classes for defining a CSVCohortMaker.


---
# Example Data
The example data consists of a subset (fold0) from the PI-CAI dataset, featuring prostate MRI images and their corresponding segmentations. The original data can be obtained from the [official website](https://zenodo.org/records/6624726) by downloading the `picai_public_images_fold0.zip` file. 
For this project, the first four subjects were selected and the images were converted from MHA to NRRD format.

1. Example `sample_data` is adapted from this original data and will be located under `sample_data.zip`.
2. Unzip the file to a folder of your choice.


----

# BUGS
-[ ] Mix multiScene support and rm the explicit "clearScene" that is currently triggered on the "Next"/"Previous" button.
-[ ] The input of new raters updates the CODE's configuration.json. This is not the desired behavior, as the configuration should be copied from the original CODE and not modified.
- 
