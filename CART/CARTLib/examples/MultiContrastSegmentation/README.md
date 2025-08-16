# Segmentation Review and Correction

This task allows for iterative review (and, if needed, correction and/or creation) of image segmentations for a cohort.

## Cohort File Specification

Aside from the universally required `uid` column, the cohort file for this task can contain the following categories of columns:

* `volume`: Any column with `volume` in its name (`volume_T1w`, `rescan_volume` etc.) is treated as a standard imaging sequence.
  * Each case must have at least one valid `volume` column entry. 
  * If multiple `volume` columns are specified, each volume will be displayed in its own column in the Slicer viewer.
  * Cases lacking an entry for a given `volume` column are ignored.
  * The first _valid_ `volume` column for each case is used as the reference volume.
* `segmentation`: Any column with `segmentation` in its name (`segmentation_deepseg`, `dr_johns_spinal_segmentation` etc.) is treated as a segmentation label, as is loaded as an overlay on top of _all_ volumes.
  * The to-be-reviewed segmentation is determined by a few criterion.
    * If the column has `primary` in its name (i.e. `primary_segmentation`, `deepseg_segmentation_primary`), it is selected as the "to-be-reviewed" segmentation, making it the default target for any corrections made.
    * If multiple `primary` columns exist, the first valid on for a given case is selected.
    * If no valid `primary` columns exist, the first valid segmentation is selected.
    * If a case lacks any valid `segmentation` column entries whatsoever, we assume you want to create the corresponding segmentation instead.
  * You do **_not_** need to specify any `segmentation` columns; doing so will assume you are creating the corresponding segmentations instead.
* `markup`: Any column with `markup` in its name is loaded as [Slicer Markup file](https://slicer.readthedocs.io/en/latest/user_guide/modules/markups.html).
  * **Currently Experimental:** markups are loaded in for reference only. We cannot guarantee any consistency with how they will behave it edited, deleted, or created post-load; this task only loads markups relevant to the currently selected case, and hides those which are not.
  * Act identically to `segmentation` columns, except that they cannot be edited at all, and no "primary" markup is selected.

## Example Cohort Files

Below are some examples of valid cohort files for common use cases. 
The file names used are placeholders representing a BIDS-like dataset; while this structure is encouraged, it is not required.

### Segmentation Creation

Only requires one (or more) volume columns to segment. You may optionally provide some markups as well.

* Single volume:
    
    | uid     | volume_T2w                      |
    |---------|---------------------------------|
    | sub_001 | sub_001/anat/sub_001_T2w.nii.gz |
    | sub_002 | sub_002/anat/sub_002_T2w.nii.gz |

* Multi-volume (T2w as orientation reference):
    
    | uid     | volume_T2w                      | volume_T1w                      |
    |---------|---------------------------------|---------------------------------|
    | sub_001 | sub_001/anat/sub_001_T2w.nii.gz | sub_001/anat/sub_001_T1w.nii.gz |
    | sub_002 | sub_002/anat/sub_002_T2w.nii.gz | sub_001/anat/sub_002_T1w.nii.gz |

* Multi-volume (T1w as orientation reference; note the change in column order):
    
    | uid     | volume_T1w                      | volume_T2w                      |
    |---------|---------------------------------|---------------------------------|
    | sub_001 | sub_001/anat/sub_001_T1w.nii.gz | sub_001/anat/sub_001_T2w.nii.gz |
    | sub_002 | sub_002/anat/sub_002_T1w.nii.gz | sub_001/anat/sub_002_T2w.nii.gz |
  
* Single volume w/ reference markup:

    | uid     | volume_T2w                      | markup_discs                                |
    |---------|---------------------------------|---------------------------------------------|
    | sub_001 | sub_001/anat/sub_001_T2w.nii.gz | derivatives/sub_001/anat/sub_001_discs.json |
    | sub_002 | sub_002/anat/sub_002_T2w.nii.gz | derivatives/sub_002/anat/sub_002_discs.json |

### Segmentation Review and/or Correction

* Single volume, reviewing a liver segmentation:
    
    | uid     | volume_T2w                      | segmentation_liver                            |
    |---------|---------------------------------|-----------------------------------------------|
    | sub_001 | sub_001/anat/sub_001_T2w.nii.gz | derivatives/sub_001/anat/sub_001_liver.nii.gz |
    | sub_002 | sub_002/anat/sub_002_T2w.nii.gz | derivatives/sub_002/anat/sub_002_liver.nii.gz |

* Single volume, reviewing a liver segmentation w/ kidney segmentation as reference:

    | uid     | volume_T2w                      | primary_segmentation_liver                    | segmentation_kidney                            |
    |---------|---------------------------------|-----------------------------------------------|------------------------------------------------|
    | sub_001 | sub_001/anat/sub_001_T2w.nii.gz | derivatives/sub_001/anat/sub_001_liver.nii.gz | derivatives/sub_001/anat/sub_001_kidney.nii.gz |
    | sub_002 | sub_002/anat/sub_002_T2w.nii.gz | derivatives/sub_002/anat/sub_002_liver.nii.gz | derivatives/sub_002/anat/sub_002_kidney.nii.gz |

* Multiple volume (w/ T2w as orientation reference), reviewing a liver segmentation w/ kidney segmentation as reference:
    
    | uid     | volume_T2w                      | volume_T1w                      | primary_segmentation_liver                    | segmentation_kidney                            |
    |---------|---------------------------------|---------------------------------|-----------------------------------------------|------------------------------------------------|
    | sub_001 | sub_001/anat/sub_001_T2w.nii.gz | sub_001/anat/sub_001_T1w.nii.gz | derivatives/sub_001/anat/sub_001_liver.nii.gz | derivatives/sub_001/anat/sub_001_kidney.nii.gz |
    | sub_002 | sub_002/anat/sub_002_T2w.nii.gz | sub_002/anat/sub_002_T1w.nii.g  | derivatives/sub_002/anat/sub_002_liver.nii.gz | derivatives/sub_002/anat/sub_002_kidney.nii.gz |

* Multiple volume (w/ T2w as orientation reference), reviewing a kidney segmentation w/ liver segmentation as reference (note the change in column names):
    
    | uid     | volume_T2w                      | volume_T1w                      | segmentation_liver                            | primary_segmentation_kidney                    |
    |---------|---------------------------------|---------------------------------|-----------------------------------------------|------------------------------------------------|
    | sub_001 | sub_001/anat/sub_001_T2w.nii.gz | sub_001/anat/sub_001_T1w.nii.gz | derivatives/sub_001/anat/sub_001_liver.nii.gz | derivatives/sub_001/anat/sub_001_kidney.nii.gz |
    | sub_002 | sub_002/anat/sub_002_T2w.nii.gz | sub_002/anat/sub_002_T1w.nii.g  | derivatives/sub_002/anat/sub_002_liver.nii.gz | derivatives/sub_002/anat/sub_002_kidney.nii.gz |

* Multiple volume (w/ T2w as orientation reference), reviewing a liver segmentation w/ kidney segmentation and vein lines for reference:

    | uid     | volume_T2w                      | volume_T1w                      | segmentation_liver                            | primary_segmentation_kidney                    | markup_veins                                |
    |---------|---------------------------------|---------------------------------|-----------------------------------------------|------------------------------------------------|---------------------------------------------|
    | sub_001 | sub_001/anat/sub_001_T2w.nii.gz | sub_001/anat/sub_001_T1w.nii.gz | derivatives/sub_001/anat/sub_001_liver.nii.gz | derivatives/sub_001/anat/sub_001_kidney.nii.gz | derivatives/sub_001/anat/sub_001_veins.json |
    | sub_002 | sub_002/anat/sub_002_T2w.nii.gz | sub_002/anat/sub_002_T1w.nii.g  | derivatives/sub_002/anat/sub_002_liver.nii.gz | derivatives/sub_002/anat/sub_002_kidney.nii.gz | derivatives/sub_001/anat/sub_002_veins.json |