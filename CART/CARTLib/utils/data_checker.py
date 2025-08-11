import slicer
import qt
from slicer.i18n import tr as _

from pathlib import Path
from typing import Optional

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

    # Returns the first validated data convention
    for c in checks:
        if c(data_path):
            return c.__name__

    return None

### Paths fetching  ###



