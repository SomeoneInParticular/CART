import slicer
import qt
from slicer.i18n import tr as _

from pathlib import Path
from typing import Dict, List, Optional

### Accepted filetypes for conventions
bids_extensions = [
    # Core imaging
    ".nii", ".nii.gz",

    # Metadata / tabular / text
    ".json", ".tsv", ".txt", ".md",

    # Diffusion MRI
    ".bvec", ".bval",

    # Surfaces / Morphometry
    ".gii", ".surf.gii", ".label.gii", ".shape.gii",

    # Tractography / Streamlines (BEPs)
    ".trk", ".tck", ".vtk",

    # Microscopy
    ".ome.tif", ".ome.tiff",

    # EEG
    ".edf", ".bdf", ".set", ".fdt",
    ".vhdr", ".vmrk", ".eeg",
    ".mef3", ".nwb",

    # iEEG (same as EEG + clinical formats)
    # (not adding duplicates here, but same as above)

    # MEG
    ".fif",   # Elekta/Neuromag
    ".ds",    # CTF (directory)
    ".con",   # KIT/Yokogawa
    ".m4d", ".pdf", ".xyz",  # BTi/4D

    # Eye Tracking
    ".edf",  # (already included, but for eye tracking too)

    # Genetics (referenced, not always stored inside BIDS)
    ".vcf",
]

### Convention checking ###
# Add any custom convention checker here

def check_pseudo_bids(data_path: Path) -> bool:
    """
    Check if the dataset follows a pseudo-BIDS structure
    """
    # First check if the derivatives folder exists
    derivatives_folder = data_path / "derivatives"

    if not derivatives_folder.is_dir():
        return False

    # Second check if structure under raw exists under derivatives
    raw_folders = [p.name for p in data_path.iterdir() if p.is_dir() and p.name.startswith("sub")]

    for name in raw_folders:
        matches = [p for p in derivatives_folder.rglob(name) if p.is_dir()]
        if matches:
            return True

    return False

def check_conventions(data_path: Path) -> Optional[str]:
    """
    Chain all the conventions until one matches, or all fail.
    """

    # By default, CART offers BIDS. Conventions can be added.
    checks = [check_pseudo_bids]

    # Set the first validated data convention as the current data convention
    for c in checks:
        if c(data_path):
            return c.__name__

    return None

### Paths fetching  ###
def fetch_resources(current_data_convention, root_path, excluded_extensions=None):
    if current_data_convention == "check_pseudo_bids":
        return fetch_bids_resources_paths(
            root_path,
            excluded_extensions=excluded_extensions
        )
    else:
        return {}


def fetch_bids_resources_paths(
    root_path: Path,
    excluded_extensions: Optional[List[str]] = None
) -> Dict[str, List[str]]:
    """
    Scan a BIDS dataset folder structure and return a dict mapping subject IDs
    (e.g., 'sub-01') to all their relevant file paths (raw + all derivatives subfolders).

    Parameters:
    - root_path: Path to the root BIDS dataset folder.
    - excluded_extensions: list of file extensions to exclude (e.g., ['.json']).

    Returns:
    - Dictionary: { subject_id: [list of relative file paths as POSIX strings] }
    """
    excluded_ext = [e.lower().strip() for e in excluded_extensions or []]
    temp_cases = {}

    def collect_files_for_subject(subject_path: Path) -> List[str]:
        files = []
        for file_path in subject_path.rglob('*'):
            if file_path.is_file() and file_path.suffix.lower() not in excluded_ext:
                rel_path = file_path.relative_to(root_path)
                files.append(rel_path.as_posix())
        return files

    # 1. Raw BIDS subjects at root
    for subj_dir in root_path.glob('sub-*'):
        if subj_dir.is_dir():
            subj_id = subj_dir.name
            temp_cases[subj_id] = collect_files_for_subject(subj_dir)

    # 2. Derivatives subjects under any subfolder of derivatives/
    derivatives_path = root_path / 'derivatives'
    if derivatives_path.is_dir():
        for subfolder in derivatives_path.iterdir():
            if subfolder.is_dir():
                for deriv_subj_dir in subfolder.glob('sub-*'):
                    if deriv_subj_dir.is_dir():
                        subj_id = deriv_subj_dir.name
                        files = collect_files_for_subject(deriv_subj_dir)
                        if subj_id in temp_cases:
                            temp_cases[subj_id].extend(files)
                        else:
                            temp_cases[subj_id] = files

    # Return sorted dictionary by subject ID
    return {case_id: files for case_id, files in sorted(temp_cases.items())}


