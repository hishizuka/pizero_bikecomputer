"""Circular monochrome icon button with stylesheet-driven interaction states."""

from modules.qt._qt_qtwidgets import QtCore, QtGui, QtWidgets


class ButtonWidget(QtWidgets.QPushButton):
    """Keep a 44px hit area around a 32px circle and a recolorable vector icon."""

    # sRGB 156 maps to level 1/3 in both phases of the DRM 64/343 palette.
    STYLES = """
      ButtonWidget {
        margin: 6px;
        padding: 0;
        border: 2px solid white;
        border-radius: 16px;
        background-color: black;
        color: white;
        outline: 0;
      }
      ButtonWidget[selected="true"] {
        background-color: white;
        color: black;
      }
      ButtonWidget[pressed="true"] {
        margin: 8px;
        border-width: 3px;
        border-radius: 14px;
        background-color: white;
        color: black;
      }
      ButtonWidget:disabled {
        background-color: black;
        border-color: #9C9C9C;
        color: #9C9C9C;
      }
    """

    def __init__(self, icon_path, accessible_name, parent=None):
        super().__init__(parent)
        self._icon_path = QtGui.QPainterPath(icon_path)
        self.setAccessibleName(accessible_name)
        self.setFixedSize(44, 44)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.setProperty("selected", False)
        self.setProperty("pressed", False)
        self.setStyleSheet(self.STYLES)
        self.pressed.connect(self._sync_state)
        self.released.connect(self._sync_state)
        self.toggled.connect(self._sync_state)

    def _sync_state(self):
        selected = self.hasFocus() or self.isChecked()
        pressed = self.isDown()
        if (
            self.property("selected") == selected
            and self.property("pressed") == pressed
        ):
            return
        self.setProperty("selected", selected)
        self.setProperty("pressed", pressed)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._sync_state()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self._sync_state()

    def setDown(self, down):
        super().setDown(down)
        self._sync_state()

    def hitButton(self, position):
        return self.rect().contains(position)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        option = QtWidgets.QStyleOptionButton()
        self.initStyleOption(option)
        self.style().drawControl(
            QtWidgets.QStyle.ControlElement.CE_PushButtonBevel,
            option,
            painter,
            self,
        )
        painter.translate(self.width() / 2, self.height() / 2)
        role = QtGui.QPalette.ColorRole.ButtonText
        pen = QtGui.QPen(self.palette().color(role), 2.2)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawPath(self._icon_path)
        painter.end()


class CloseButton(ButtonWidget):
    def __init__(self, parent=None):
        path = QtGui.QPainterPath()
        path.moveTo(-5, -5)
        path.lineTo(5, 5)
        path.moveTo(5, -5)
        path.lineTo(-5, 5)
        super().__init__(path, "閉じる", parent)
