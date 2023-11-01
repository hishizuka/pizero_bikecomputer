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

# set default configuration
pg.setConfigOptions(antialias=True)
pg.setConfigOption("background", "w")
pg.setConfigOption("foreground", "k")


QT_KEY_BACKTAB = QtCore.Qt.Key.Key_Backtab if USE_PYQT6 else QtCore.Qt.Key_Backtab
QT_KEY_TAB = QtCore.Qt.Key.Key_Tab if USE_PYQT6 else QtCore.Qt.Key_Tab
QT_KEY_SPACE = QtCore.Qt.Key.Key_Space if USE_PYQT6 else QtCore.Qt.Key_Space
QT_KEY_PRESS = QtCore.QEvent.Type.KeyPress if USE_PYQT6 else QtCore.QEvent.KeyPress
QT_KEY_RELEASE = (
    QtCore.QEvent.Type.KeyRelease if USE_PYQT6 else QtCore.QEvent.KeyRelease
)
QT_NO_MODIFIER = (
    QtCore.Qt.KeyboardModifier.NoModifier if USE_PYQT6 else QtCore.Qt.NoModifier
)

QT_ALIGN_LEFT = QtCore.Qt.AlignmentFlag.AlignLeft if USE_PYQT6 else QtCore.Qt.AlignLeft
QT_ALIGN_CENTER = (
    QtCore.Qt.AlignmentFlag.AlignCenter if USE_PYQT6 else QtCore.Qt.AlignCenter
)
QT_ALIGN_H_CENTER = (
    QtCore.Qt.AlignmentFlag.AlignHCenter if USE_PYQT6 else QtCore.Qt.AlignHCenter
)
QT_ALIGN_V_CENTER = (
    QtCore.Qt.AlignmentFlag.AlignVCenter if USE_PYQT6 else QtCore.Qt.AlignVCenter
)
QT_ALIGN_RIGHT = (
    QtCore.Qt.AlignmentFlag.AlignRight if USE_PYQT6 else QtCore.Qt.AlignRight
)
QT_ALIGN_BOTTOM = (
    QtCore.Qt.AlignmentFlag.AlignBottom if USE_PYQT6 else QtCore.Qt.AlignBottom
)
QT_ALIGN_TOP = QtCore.Qt.AlignmentFlag.AlignTop if USE_PYQT6 else QtCore.Qt.AlignTop
QT_EXPANDING = (
    QtWidgets.QSizePolicy.Policy.Expanding
    if USE_PYQT6
    else QtWidgets.QSizePolicy.Expanding
)
QT_FIXED = (
    QtWidgets.QSizePolicy.Policy.Fixed if USE_PYQT6 else QtWidgets.QSizePolicy.Fixed
)

QT_NO_FOCUS = QtCore.Qt.FocusPolicy.NoFocus if USE_PYQT6 else QtCore.Qt.NoFocus
QT_STRONG_FOCUS = (
    QtCore.Qt.FocusPolicy.StrongFocus if USE_PYQT6 else QtCore.Qt.StrongFocus
)
QT_TAB_FOCUS_REASON = (
    QtCore.Qt.FocusReason.TabFocusReason if USE_PYQT6 else QtCore.Qt.TabFocusReason
)
QT_BACKTAB_FOCUS_REASON = (
    QtCore.Qt.FocusReason.BacktabFocusReason
    if USE_PYQT6
    else QtCore.Qt.BacktabFocusReason
)

QT_SCROLLBAR_ALWAYSOFF = (
    QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    if USE_PYQT6
    else QtCore.Qt.ScrollBarAlwaysOff
)
QT_TEXTEDIT_NOWRAP = (
    QtWidgets.QTextEdit.LineWrapMode.NoWrap if USE_PYQT6 else QtWidgets.QTextEdit.NoWrap
)

# TODO => QT_STACKONE
QT_STACKINGMODE_STACKONE = (
    QtWidgets.QStackedLayout.StackingMode.StackOne
    if USE_PYQT6
    else QtWidgets.QStackedLayout.StackOne
)
# TODO => QT_STACKALL
QT_STACKINGMODE_STACKALL = (
    QtWidgets.QStackedLayout.StackingMode.StackAll
    if USE_PYQT6
    else QtWidgets.QStackedLayout.StackAll
)

QT_PE_WIDGET = (
    QtWidgets.QStyle.PrimitiveElement.PE_Widget
    if USE_PYQT6
    else QtWidgets.QStyle.PE_Widget
)
QT_WA_TRANSLUCENT_BACKGROUND = (
    QtCore.Qt.WidgetAttribute.WA_TranslucentBackground
    if USE_PYQT6
    else QtCore.Qt.WA_TranslucentBackground
)
QT_WA_TRANSPARENT_FOR_MOUSE_EVENTS = (
    QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents
    if USE_PYQT6
    else QtCore.Qt.WA_TransparentForMouseEvents
)

# for draw_display
QT_FORMAT_RGB888 = (
    QtGui.QImage.Format.Format_RGB888 if USE_PYQT6 else QtGui.QImage.Format_RGB888
)

QT_FORMAT_MONO = (
    QtGui.QImage.Format.Format_Mono if USE_PYQT6 else QtGui.QImage.Format_Mono
)

QT_COMPOSITION_MODE_SOURCEIN = (
    QtGui.QPainter.CompositionMode.CompositionMode_SourceIn
    if USE_PYQT6
    else QtGui.QPainter.CompositionMode_SourceIn
)

QT_COMPOSITION_MODE_DARKEN = (
    QtGui.QPainter.CompositionMode.CompositionMode_Darken
    if USE_PYQT6
    else QtGui.QPainter.CompositionMode_Darken
)
