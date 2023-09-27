import os

__all__ = ["USE_PYQT6", "QtCore", "QtWidgets", "QtGui", "pg", "qasync"]

USE_PYQT6 = False
try:
    import PyQt6.QtCore as QtCore
    import PyQt6.QtWidgets as QtWidgets
    import PyQt6.QtGui as QtGui

    USE_PYQT6 = True
except (ImportError, ModuleNotFoundError):
    import PyQt5.QtCore as QtCore
    import PyQt5.QtWidgets as QtWidgets
    import PyQt5.QtGui as QtGui

# import qasync once pyQt is imported so the correct version is used (it starts with PyQt5 then tries PyQt6)
import qasync  # noqa

# make sure the version is correct in case the underlying code for qasync changed
if USE_PYQT6 and qasync.QtModuleName != "PyQt6":
    raise AssertionError(
        f"Wrong version of PyQt6 used for qasync: {qasync.QtModuleName}"
    )
elif not USE_PYQT6 and qasync.QtModuleName != "PyQt5":
    raise AssertionError(
        f"Wrong version of PyQt5 used for qasync: {qasync.QtModuleName}"
    )

# pyqtgraph will check/try to import PyQT6 on load and might fail if some packages were imported
# (if pyQt6 is halfway installed): so we force the version here
os.environ.setdefault("PYQTGRAPH_QT_LIB", qasync.QtModuleName)

# make sure pyqtgraph it imported from here so PYQTGRAPH_QT_LIB will always be set
import pyqtgraph as pg  # noqa
