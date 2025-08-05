import slicer
import qt

from pathlib import Path

### Import & installation ###
def import_pybids():
    """
    Install the PyBIDS package into Slicer's Python environment if not installed.
    """
    try:
        import pybids
        print("PyBIDS is now working adequately!")
        return True
    except Exception as e:
        slicer.util.pip_install("pybids")

        msg = qt.QMessageBox()
        msg.setWindowTitle("Restart Required")
        msg.setText("Please restart 3D Slicer for PyBIDS to take effect.")
        msg.setIcon(qt.QMessageBox.Warning)
        msg.addButton("Restart", qt.QMessageBox.AcceptRole)
        msg.addButton("Later", qt.QMessageBox.RejectRole)

        if msg.exec_() == 0:
            slicer.util.restart()
        return False

def check_pybids_installation():
    try:
        import pybids
        return True
    except ImportError or ModuleNotFoundError:
        return import_pybids()

### Querying ###
def get_bids_folders(data_path, scope):
    """
    Gets either the derivatives or raw BIDS folders from the datapath
    """
    try:
        layout_raw = BIDSLayout(data_path)
        layout_derivatives = BIDSLayout(data_path, derivatives=True)

        if scope == "raw":
            subject_dirs = [Path(layout_raw.root) / f'sub-{subject}' for subject in layout_raw.get_subjects()]
        else:
            subject_dirs = [Path(layout_raw.root) / "derivatives" / f'sub-{subject}' for subject in layout_raw.get_subjects()]

        return subject_dirs

    except Exception as e:
        msgBox = qt.QMessageBox()
        msgBox.setIcon(qt.QMessageBox.Critical)
        msgBox.setText(f"<b>Error</b>")
        msgBox.setWindowTitle(f"Validation Error: {e}")
        msgBox.setStandardButtons(qt.QMessageBox.Ok)
        # Allows for selectable text in the error message
        msgBox.setTextInteractionFlags(qt.Qt.TextSelectableByMouse)
        msgBox.exec()

        return None
