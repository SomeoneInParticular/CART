import slicer
import qt

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