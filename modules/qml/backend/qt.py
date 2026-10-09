"""Qt bindings used by the QML GUI backend."""

USE_PYQT6 = False
USE_PYSIDE6 = False
QT_PACKAGE = ""

try:
    import PySide6.QtCore as QtCore
    import PySide6.QtGui as QtGui
    import PySide6.QtQml as QtQml
    import PySide6.QtQuick as QtQuick

    USE_PYSIDE6 = True
    QT_PACKAGE = "PySide6"
except (ImportError, ModuleNotFoundError):
    try:
        import PyQt6.QtCore as QtCore
        import PyQt6.QtGui as QtGui
        import PyQt6.QtQml as QtQml
        import PyQt6.QtQuick as QtQuick

        USE_PYQT6 = True
        QT_PACKAGE = "PyQt6"
    except (ImportError, ModuleNotFoundError):
        pass

import modules.qt._qt_ver as _qt_ver

_qt_ver.USE_PYQT6 = USE_PYQT6
_qt_ver.USE_PYSIDE6 = USE_PYSIDE6
_qt_ver.QT_PACKAGE = QT_PACKAGE
_qt_ver.QtCore = QtCore
_qt_ver.QtGui = QtGui

from modules.qt._qt_constants import *
