import slicer
import qt
from slicer.i18n import tr as _
import time

from pathlib import Path

### Import & installation ###
def import_pybids():
    """
    Install the PyBIDS package into Slicer's Python environment if not installed.
    """
    try:
        import bids
        from bids import BIDSLayout
        print("PyBIDS is now working adequately!")
        return True
    except ImportError as e:
        print(f"PyBIDS not found, attempting to install: {e}")
        progressDialog = slicer.util.createProgressDialog(
            windowTitle="Installing...",
            labelText="Installing Pandas Python package...",
            maximum=0,
        )
        slicer.app.processEvents()

        try:
            slicer.util.pip_install("pybids")
            progressDialog.close()

            # Try importing again after installation
            import bids
            from bids import BIDSLayout
            print("PyBIDS installed and imported successfully!")
            return True

        except Exception as install_error:
            progressDialog.close()

            msg = qt.QMessageBox()
            msg.setWindowTitle("Installation Failed")
            msg.setText(f"Failed to install PyBIDS. Please restart 3D Slicer and try again.\n\nError details:\n{str(install_error)}")
            msg.setIcon(qt.QMessageBox.Critical)
            msg.addButton("Restart", qt.QMessageBox.AcceptRole)
            msg.addButton("Later", qt.QMessageBox.RejectRole)

            if msg.exec_() == 0:
                slicer.util.restart()
            return False
    except Exception as e:
        print(f"Unexpected error with PyBIDS: {e}")
        return False

def check_pybids_installation():
    """
    Check if PyBIDS is available and install if needed.
    """
    try:
        import bids
        from bids import BIDSLayout
        return True
    except ImportError:
        return import_pybids()

def get_bids_layout(data_path, derivatives=False):
    """
    Helper function to get a BIDSLayout object.
    """
    try:
        return fetch_layout(data_path, derivatives=derivatives)
    except ImportError:
        if not import_pybids():
            return None
        # Try again after installation
        try:
            return fetch_layout(data_path, derivatives=derivatives)
        except Exception as e:
            print(f"Failed to create BIDSLayout even after installation: {e}")
            return None
    except Exception as e:
        print(f"Error creating BIDSLayout: {e}")
        return None

def fetch_layout(data_path, derivatives=False):
    """
    Fetches a BIDSLayout object while displaying a progress dialog.
    The dialog is shown during the potentially long initialization of BIDSLayout.
    """
    import bids
    from bids import BIDSLayout

    progressDialog = slicer.util.createProgressDialog(
            windowTitle=_("Initializing BIDS"),
            labelText=_("Analyzing BIDS structure..."),
            maximum=0,
            parent=slicer.util.mainWindow()
    )

    progressDialog.setCancelButton(None)

    progressDialog.labelText = f"Analyzing BIDS structure at {data_path}..."
    slicer.app.processEvents()

    cancelled = progressDialog.wasCanceled

    if cancelled:
        return None

    slicer.app.processEvents()

    try:
        layout = BIDSLayout(data_path, derivatives=derivatives)

        slicer.app.processEvents()
        if cancelled:
            return None

        progressDialog.close()
        return layout

    except:
        progressDialog.close()
        return None

### Querying ###
def get_bids_folders(data_path, scope):
    """
    Gets either the derivatives or raw BIDS folders from the datapath
    """
    try:
        # Check if PyBIDS is available first
        if not check_pybids_installation():
            return None

        layout = get_bids_layout(data_path, derivatives=(scope != "raw"))

        if layout is None:
            return None

        subjects = layout.get_subjects()

        if scope == "raw":
            subject_dirs = [Path(layout.root) / f'sub-{subject}' for subject in subjects]
        else:
            subject_dirs = [Path(layout.root) / "derivatives" / f'sub-{subject}' for subject in subjects]

        return subject_dirs

    except Exception as e:
        print(f"Error in get_bids_folders: {e}")
        msgBox = qt.QMessageBox()
        msgBox.setIcon(qt.QMessageBox.Critical)
        msgBox.setText(f"<b>BIDS Error</b>")
        msgBox.setInformativeText(f"Failed to process BIDS data: {str(e)}")
        msgBox.setWindowTitle("BIDS Validation Error")
        msgBox.setStandardButtons(qt.QMessageBox.Ok)
        msgBox.setTextInteractionFlags(qt.Qt.TextSelectableByMouse)
        msgBox.exec()
        return None