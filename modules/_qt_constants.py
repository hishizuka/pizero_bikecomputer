from modules._qt_ver import (
    USE_PYQT6,
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

# import qasync once the Qt bindings are imported so the correct version is used
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


# key
QT_KEY_BACKTAB = QtCore.Qt.Key.Key_Backtab
QT_KEY_TAB = QtCore.Qt.Key.Key_Tab
QT_KEY_SPACE = QtCore.Qt.Key.Key_Space
QT_KEY_PRESS = QtCore.QEvent.Type.KeyPress
QT_KEY_RELEASE = QtCore.QEvent.Type.KeyRelease
QT_NO_MODIFIER = QtCore.Qt.KeyboardModifier.NoModifier

# align
QT_ALIGN_LEFT = QtCore.Qt.AlignmentFlag.AlignLeft
QT_ALIGN_RIGHT = QtCore.Qt.AlignmentFlag.AlignRight
QT_ALIGN_CENTER = QtCore.Qt.AlignmentFlag.AlignCenter
QT_ALIGN_H_CENTER = QtCore.Qt.AlignmentFlag.AlignHCenter
QT_ALIGN_V_CENTER = QtCore.Qt.AlignmentFlag.AlignVCenter
QT_ALIGN_BOTTOM = QtCore.Qt.AlignmentFlag.AlignBottom
QT_ALIGN_TOP = QtCore.Qt.AlignmentFlag.AlignTop

# focus
QT_NO_FOCUS = QtCore.Qt.FocusPolicy.NoFocus
QT_STRONG_FOCUS = QtCore.Qt.FocusPolicy.StrongFocus
QT_TAB_FOCUS_REASON = QtCore.Qt.FocusReason.TabFocusReason
QT_BACKTAB_FOCUS_REASON = QtCore.Qt.FocusReason.BacktabFocusReason

# for draw_display
QT_FORMAT_RGB888 = QtGui.QImage.Format.Format_RGB888
QT_FORMAT_MONO = QtGui.QImage.Format.Format_Mono
