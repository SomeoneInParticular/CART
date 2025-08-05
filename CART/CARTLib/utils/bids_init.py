from pathlib import Path

import slicer

### Importing and checking ###
def check_pybids_installation():
    try :
        import pybids
        return True
    except ImportError:
        return False

def import_pybids():
    """
    Install the PyBIDS package into Slicer's Python environment if not installed.

    This is a convenience function to ensure that PyBIDS is available for use
    in Slicer's Python environment.
    """
    try:
        import pybids
    except ImportError:
        slicer.util.pip_install("pybids")
        import pybids
    finally:
        print("PyBIDS is now working adequately!")

### Searching ###