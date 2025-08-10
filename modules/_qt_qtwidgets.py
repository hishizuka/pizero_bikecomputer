import os


USE_QT6 = False
USE_PYQT6 = False
USE_PYQT5 = False
USE_PYSIDE6 = False
QT_PACKAGE = ""

try:
    raise ImportError
    import PySide6.QtCore as QtCore
    import PySide6.QtGui as QtGui
    import PySide6.QtWidgets as QtWidgets
    USE_QT6 = True
    USE_PYSIDE6 = True
    QT_PACKAGE = "PySide6"
except (ImportError, ModuleNotFoundError):
    try:
        import PyQt6.QtCore as QtCore
        import PyQt6.QtWidgets as QtWidgets
        import PyQt6.QtGui as QtGui
        USE_QT6 = True
        USE_PYQT6 = True
        QT_PACKAGE = "PyQt6"
    except (ImportError, ModuleNotFoundError):
        import PyQt5.QtCore as QtCore
        import PyQt5.QtWidgets as QtWidgets
        import PyQt5.QtGui as QtGui
        USE_PYQT5 = True
        QT_PACKAGE = "PyQt5"

import modules._qt_ver as _qt_ver
_qt_ver.USE_QT6 = USE_QT6
_qt_ver.USE_PYQT6 = USE_PYQT6
_qt_ver.USE_PYQT5 = USE_PYQT5
_qt_ver.USE_PYSIDE6 = USE_PYSIDE6
_qt_ver.QT_PACKAGE = QT_PACKAGE
_qt_ver.QtCore = QtCore
_qt_ver.QtGui = QtGui

from modules._qt_constants import *

# pyqtgraph will check/try to import PyQT6 on load and might fail if some packages were imported
# (if pyQt6 is halfway installed): so we force the version here
os.environ.setdefault("PYQTGRAPH_QT_LIB", qasync.QtModuleName)

# make sure pyqtgraph it imported from here so PYQTGRAPH_QT_LIB will always be set
import pyqtgraph as pg  # noqa

# set default configuration
pg.setConfigOptions(antialias=True)
pg.setConfigOption("background", "w")
pg.setConfigOption("foreground", "k")

# QtWidgets
QT_EXPANDING = (
    QtWidgets.QSizePolicy.Policy.Expanding
    if USE_QT6
    else QtWidgets.QSizePolicy.Expanding
)
QT_FIXED = (
    QtWidgets.QSizePolicy.Policy.Fixed if USE_QT6 else QtWidgets.QSizePolicy.Fixed
)

# for textedit
QT_SCROLLBAR_ALWAYSOFF = (
    QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    if USE_QT6
    else QtCore.Qt.ScrollBarAlwaysOff
)
QT_TEXTEDIT_NOWRAP = (
    QtWidgets.QTextEdit.LineWrapMode.NoWrap if USE_QT6 else QtWidgets.QTextEdit.NoWrap
)

# for popup
QT_STACKINGMODE_STACKONE = (
    QtWidgets.QStackedLayout.StackingMode.StackOne
    if USE_QT6
    else QtWidgets.QStackedLayout.StackOne
)
QT_STACKINGMODE_STACKALL = (
    QtWidgets.QStackedLayout.StackingMode.StackAll
    if USE_QT6
    else QtWidgets.QStackedLayout.StackAll
)
QT_PE_WIDGET = (
    QtWidgets.QStyle.PrimitiveElement.PE_Widget
    if USE_QT6
    else QtWidgets.QStyle.PE_Widget
)
QT_WA_TRANSLUCENT_BACKGROUND = (
    QtCore.Qt.WidgetAttribute.WA_TranslucentBackground
    if USE_QT6
    else QtCore.Qt.WA_TranslucentBackground
)
QT_WA_TRANSPARENT_FOR_MOUSE_EVENTS = (
    QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents
    if USE_QT6
    else QtCore.Qt.WA_TransparentForMouseEvents
)

# for map widgets
QT_COMPOSITION_MODE_SOURCEIN = (
    QtGui.QPainter.CompositionMode.CompositionMode_SourceIn
    if USE_QT6
    else QtGui.QPainter.CompositionMode_SourceIn
)
QT_COMPOSITION_MODE_DARKEN = (
    QtGui.QPainter.CompositionMode.CompositionMode_Darken
    if USE_QT6
    else QtGui.QPainter.CompositionMode_Darken
)
QT_MOUSEBUTTON_LEFTBUTTON = (
    QtCore.Qt.MouseButton.LeftButton
    if USE_QT6
    else QtCore.Qt.MouseButton.LeftButton
)