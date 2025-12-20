import os


USE_PYQT6 = False
USE_PYSIDE6 = False
QT_PACKAGE = ""

try:
    raise ImportError
    import PySide6.QtCore as QtCore
    import PySide6.QtGui as QtGui
    import PySide6.QtWidgets as QtWidgets
    USE_PYSIDE6 = True
    QT_PACKAGE = "PySide6"
except (ImportError, ModuleNotFoundError):
    try:
        import PyQt6.QtCore as QtCore
        import PyQt6.QtWidgets as QtWidgets
        import PyQt6.QtGui as QtGui
        USE_PYQT6 = True
        QT_PACKAGE = "PyQt6"
    except (ImportError, ModuleNotFoundError) as exc:
        raise ImportError("Requires PyQt6 or PySide6.") from exc

import modules._qt_ver as _qt_ver
_qt_ver.USE_PYQT6 = USE_PYQT6
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
QT_EXPANDING = QtWidgets.QSizePolicy.Policy.Expanding
QT_FIXED = QtWidgets.QSizePolicy.Policy.Fixed
QT_PREFERRED = QtWidgets.QSizePolicy.Policy.Preferred

# for textedit
QT_SCROLLBAR_ALWAYSOFF = QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
QT_TEXTEDIT_NOWRAP = QtWidgets.QTextEdit.LineWrapMode.NoWrap

# for popup
QT_STACKINGMODE_STACKONE = QtWidgets.QStackedLayout.StackingMode.StackOne
QT_STACKINGMODE_STACKALL = QtWidgets.QStackedLayout.StackingMode.StackAll
QT_PE_WIDGET = QtWidgets.QStyle.PrimitiveElement.PE_Widget
QT_WA_TRANSLUCENT_BACKGROUND = QtCore.Qt.WidgetAttribute.WA_TranslucentBackground
QT_WA_TRANSPARENT_FOR_MOUSE_EVENTS = (
    QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents
)

# for map widgets
QT_COMPOSITION_MODE_SOURCEIN = (
    QtGui.QPainter.CompositionMode.CompositionMode_SourceIn
)
QT_COMPOSITION_MODE_DARKEN = (
    QtGui.QPainter.CompositionMode.CompositionMode_Darken
)
QT_MOUSEBUTTON_LEFTBUTTON = QtCore.Qt.MouseButton.LeftButton

