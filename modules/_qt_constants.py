from modules._qt_ver import (
    USE_QT6,
    USE_PYQT6,
    USE_PYQT5,
    USE_PYSIDE6,
    QtCore,
    QtGui,
)


if USE_PYSIDE6:
    Signal = QtCore.Signal
    QtCore.QT_VERSION_STR = QtCore.__version__
    Slot = QtCore.Slot
else:
    Signal = QtCore.pyqtSignal
    Slot = QtCore.pyqtSlot

# import qasync once pyQt is imported so the correct version is used (it starts with PyQt5 then tries PyQt6)
import qasync  # noqa

# make sure the version is correct in case the underlying code for qasync changed
if USE_PYSIDE6 and qasync.QtModuleName != "PySide6":
    raise AssertionError(
        f"Wrong version of PySide6 used for qasync: {qasync.QtModuleName}"
    )
elif USE_PYQT6 and qasync.QtModuleName != "PyQt6":
    raise AssertionError(
        f"Wrong version of PyQt6 used for qasync: {qasync.QtModuleName}"
    )
elif USE_PYQT5 and qasync.QtModuleName != "PyQt5":
    raise AssertionError(
        f"Wrong version of PyQt5 used for qasync: {qasync.QtModuleName}"
    )


# key
QT_KEY_BACKTAB = QtCore.Qt.Key.Key_Backtab if USE_QT6 else QtCore.Qt.Key_Backtab
QT_KEY_TAB = QtCore.Qt.Key.Key_Tab if USE_QT6 else QtCore.Qt.Key_Tab
QT_KEY_SPACE = QtCore.Qt.Key.Key_Space if USE_QT6 else QtCore.Qt.Key_Space
QT_KEY_PRESS = QtCore.QEvent.Type.KeyPress if USE_QT6 else QtCore.QEvent.KeyPress
QT_KEY_RELEASE = (
    QtCore.QEvent.Type.KeyRelease if USE_QT6 else QtCore.QEvent.KeyRelease
)
QT_NO_MODIFIER = (
    QtCore.Qt.KeyboardModifier.NoModifier if USE_QT6 else QtCore.Qt.NoModifier
)

#align
QT_ALIGN_LEFT = QtCore.Qt.AlignmentFlag.AlignLeft if USE_QT6 else QtCore.Qt.AlignLeft
QT_ALIGN_RIGHT = QtCore.Qt.AlignmentFlag.AlignRight if USE_QT6 else QtCore.Qt.AlignRight
QT_ALIGN_CENTER = (
    QtCore.Qt.AlignmentFlag.AlignCenter if USE_QT6 else QtCore.Qt.AlignCenter
)
QT_ALIGN_H_CENTER = (
    QtCore.Qt.AlignmentFlag.AlignHCenter if USE_QT6 else QtCore.Qt.AlignHCenter
)
QT_ALIGN_V_CENTER = (
    QtCore.Qt.AlignmentFlag.AlignVCenter if USE_QT6 else QtCore.Qt.AlignVCenter
)
QT_ALIGN_RIGHT = (
    QtCore.Qt.AlignmentFlag.AlignRight if USE_QT6 else QtCore.Qt.AlignRight
)
QT_ALIGN_BOTTOM = (
    QtCore.Qt.AlignmentFlag.AlignBottom if USE_QT6 else QtCore.Qt.AlignBottom
)
QT_ALIGN_TOP = QtCore.Qt.AlignmentFlag.AlignTop if USE_QT6 else QtCore.Qt.AlignTop

#focus
QT_NO_FOCUS = QtCore.Qt.FocusPolicy.NoFocus if USE_QT6 else QtCore.Qt.NoFocus
QT_STRONG_FOCUS = (
    QtCore.Qt.FocusPolicy.StrongFocus if USE_QT6 else QtCore.Qt.StrongFocus
)
QT_TAB_FOCUS_REASON = (
    QtCore.Qt.FocusReason.TabFocusReason if USE_QT6 else QtCore.Qt.TabFocusReason
)
QT_BACKTAB_FOCUS_REASON = (
    QtCore.Qt.FocusReason.BacktabFocusReason
    if USE_QT6
    else QtCore.Qt.BacktabFocusReason
)

# for draw_display
QT_FORMAT_RGB888 = (
    QtGui.QImage.Format.Format_RGB888 if USE_QT6 else QtGui.QImage.Format_RGB888
)
QT_FORMAT_MONO = (
    QtGui.QImage.Format.Format_Mono if USE_QT6 else QtGui.QImage.Format_Mono
)

