import sys
import os

# Ensure the project root is on the path when launched directly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# PyQt6 needs its bundled Qt6 DLLs in the DLL search path.
# In Anaconda environments the standard Library\bin dir is not in PATH,
# and the PyQt6 package dir may also need to be registered explicitly.
import importlib.util as _ilu
_pyqt6_spec = _ilu.find_spec("PyQt6")
if _pyqt6_spec:
    _qt6_bin = os.path.join(os.path.dirname(_pyqt6_spec.origin), "Qt6", "bin")
    if os.path.isdir(_qt6_bin):
        os.add_dll_directory(_qt6_bin)
_conda_lib = os.path.join(os.path.dirname(sys.executable), "Library", "bin")
if os.path.isdir(_conda_lib):
    os.add_dll_directory(_conda_lib)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt

from AppRoot import AppRoot
from comm.serial_com_ctrl import SerialCtrl
from comm.data_com_ctrl   import DataMaster


def main():
    serial = SerialCtrl()
    data   = DataMaster()

    # Respect OS display scaling on every monitor size / DPI
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # QWebEngineView (used for the Leaflet map) requires this attribute to
    # be set BEFORE QApplication is constructed. Without it, Qt prints
    # "Attribute Qt::AA_ShareOpenGLContexts must be set before
    # QCoreApplication is created." on every launch.
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Scale base font with screen DPI so text is readable on every display
    screen_dpi = app.primaryScreen().physicalDotsPerInch()
    base_pt    = max(9, min(12, int(10 * screen_dpi / 96)))
    app.setFont(QFont("Segoe UI", base_pt))

    # First-run setup: if no API keys have ever been configured for this user,
    # prompt for them BEFORE creating the main window. Skipping is allowed —
    # the app will still launch but with limited functionality. Settings can
    # be revisited later from the gear buttons.
    from setup.keys import has_any_key
    if not has_any_key():
        from setup.dialog import FirstRunSetupDialog
        dlg = FirstRunSetupDialog()
        dlg.exec()   # blocking — user must Save or Skip

    window = AppRoot(serial, data)
    window.showMaximized()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

