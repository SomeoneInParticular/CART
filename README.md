# Case Annotation and Review Tool (CART)

## What is CART?

CART is a module for the 3D slicer program designed to help you manage  iterative analyses, allowing you to focus on implementing and running task you set out to do. Currently, it provides the following capabilities:

* Managing sequential cases (be they patients, sub-studies, or other collections of data).
* Caching and memory management.
* User profiles (to distinguish between different local users of CART analyses)

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
   <img width="948" height="144" alt="image" src="https://github.com/user-attachments/assets/9e98c9b5-7039-4e1a-bea8-a97c63ee73bd" />

   3. Select "Download ZIP"
   <img width="432" height="349" alt="image" src="https://github.com/user-attachments/assets/0a1360dd-89fe-4cbb-8e46-c5be4282e5aa" />

   4. Choose where you want the resulting file to be placed in the resulting popup
   5. Wait for the download to complete
   6. Once complete, navigate to the `CART-main.zip` file and unzip it (on most OS systems, double-clicking on the file should tell you how to do this)

2. Cloning the repository via `git`:
   1. Open a terminal in a directory of your choice
   2. Run the following command to clone the current `CART` repository:
    ~~~
    git clone git@github.com:SomeoneInParticular/CART.git CART-main
    ~~~

### Registering CART in Slicer

0. Open the cloned CART directory you created prior in a file browser
1. Start up Slicer
2. Select `Edit` (top left) > `Application Settings`
<img width="1066" height="154" alt="image" src="https://github.com/user-attachments/assets/1f2c4d4f-ce10-46fd-8165-09c0df87a7e6" />

3. In the "settings" popup, select `Modules` from the left sidebar
<img width="865" height="650" alt="image" src="https://github.com/user-attachments/assets/ea9d4013-b77b-47ef-84b5-f4d38fd7f044" />

4. Click and drag `CART.py` from the file browser into the "Additional module paths" panel.
5. Click "OK"; Slicer should prompt you that it needs to restart.
<img width="395" height="169" alt="image" src="https://github.com/user-attachments/assets/76c1d8c4-bd3a-40d9-b674-01d7787a2a44" />

6. Restart Slicer

### [Optional] Setting CART as your Default Module

1. Start Slicer
2. Select `Edit` (top left) > `Application Settings`
3. In the "settings" popup, select `Modules` from the left sidebar
4. Select `CART` from the dropdown button labelled "Default startup module"
<img width="506" height="760" alt="image" src="https://github.com/user-attachments/assets/66a360ff-8ad6-406e-a498-7e1ff1ae6f20" />


## Using CART

To run CART, you must specify 4 things prior to beginning:

### User

The User is simply a profile which tracks who is currently running CART. It marks completed tasks as being done by you, so that others can repeat what you did simultaneously without overriding your work. In future releases, it will also track configuration settings specific to you, allowing you to modify CART's behaviour to your liking without disrupting others who're sharing the computer.

To add a new user:

0. Select the `CART` module, if you have not done so already.
1. Next to the "User:" row, select the `+` button.
2. Fill in the details prompted to you by the resulting popup, and click "OK"

If you have already registered yourself, you can select your user-name from dropdown instead. 

### Cohort

A "Cohort" is a set of "cases" you want to iterate through. What a "case" entails is largely up to you; it can represent a single patient, a subset of the data, or any other collection of resources you want to want to group together to iteratively do something with/too.

In CART, a cohort (and the cases within it) are managed through a CSV file; one each row (barring the first) represents a single case, and each column a resource that case may need/have.

The only strict requirement of a cohort CSV file is that it must have a `uid` column, which contains a unique string. CART uses this string to track each case internally, so please ensure that the each case has a unique value here! Aside from this constraint, it is otherwise up to you what resources each case should include; as long as they're formatted in a way that the [Task](#task) you intend to run can interpret it, it is free game! For example, the cohort file for a segmentation review task could look something like this:

```
uid,volume_t2w,segmentation_deepseg
sub-amu05_T2w,sub-amu05/anat/sub-amu05_T2w.nii.gz,derivatives/labels/sub-amu05/anat/sub-amu05_T2w_seg.nii.gz
sub-amu04_T2w,sub-amu04/anat/sub-amu04_T2w.nii.gz,derivatives/labels/sub-amu04/anat/sub-amu04_T2w_seg.nii.gz
...
```

To select a cohort CSV, click the `...` button next to the file browser labelled "Cohort File" in the Cart module


> [!NOTE]  
> File resources in a cohort can be absolute OR relative; the root path for relative files can be selected via the [Data Path](#data-path)..


### Data Path

This is a path to the root directory for resources your cohort require. Any files within the cohort file will treat the path designated here as their "root".

To select a Data path, click the `...` button next to the file browser labelled "Data Path" in the Cart module.

### Task

A Task designates what you want to do for each case in the cohort. By default, CART provides a number of pre-provided tasks for you to use:

* **[Multi-Contrast Segmentation](./CART/CARTLib/examples/MultiContrastSegmentation/README.md)**: General purpose segmentation review and correction tool. Simply specify a "primary" segmentation you want to review, and CART will load it into view for you to review, correct, or replace entirely.
* **[Registration Review](CART/CARTLib/examples/RegistrationReview/README.md)**: Based on a set of volumes and corresponding segmentations, mark each case as properly registered or not.

In the future, you will also be able to register arbitrary tasks, either coded by you or downloaded from other developers.

To select a Task, choose it from the "Task" dropdown.

### Starting CART

Once you have selected all the parameters prior, click "Confirm" to begin!


## For Developers:

### IDE Set Up

#### Source Directories

As both Slicer and CART load libraries into Python's path post-init, most IDEs will not be able to recognize some of the import statements used by our codebase by default.

To fix this, please mark the following directories as "source" folders in the Project's structure:

* `{Slicer Installation Directory}/bin/Python`: exposes that installations versions of VTK, CTK, and QT, along with slicer's own utilities.
* `{This Directory}/CART`; exposes CARTLib and its contents.

---
# Example Data
The example data consists of a subset (fold0) from the PI-CAI dataset, featuring prostate MRI images and their corresponding segmentations. The original data can be obtained from the [official website](https://zenodo.org/records/6624726) by downloading the `picai_public_images_fold0.zip` file. 
For this project, the first four subjects were selected and the images were converted from MHA to NRRD format.

1. Example `sample_data` is adapted from this original data and will be located under `sample_data.zip`.
2. Unzip the file to a folder of your choice.
