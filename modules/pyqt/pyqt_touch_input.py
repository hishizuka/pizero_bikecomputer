from modules._qt_qtwidgets import QtCore, QtGui, QtWidgets


class TouchInputFilter(QtCore.QObject):
    _TOUCH_EVENTS = {
        QtCore.QEvent.Type.TouchBegin,
        QtCore.QEvent.Type.TouchUpdate,
        QtCore.QEvent.Type.TouchEnd,
        QtCore.QEvent.Type.TouchCancel,
    }
    _MOUSE_EVENTS = {
        QtCore.QEvent.Type.MouseButtonPress,
        QtCore.QEvent.Type.MouseButtonRelease,
        QtCore.QEvent.Type.MouseButtonDblClick,
        QtCore.QEvent.Type.MouseMove,
        QtCore.QEvent.Type.Wheel,
    }

    def __init__(self, gui):
        super().__init__(gui.app)
        self.gui = gui
        self._swipe_start = None
        self._swipe_page = None
        self._swipe_touch = False

    def reset_swipe(self):
        self._swipe_start = None
        self._swipe_page = None
        self._swipe_touch = False

    def eventFilter(self, obj, event):
        event_type = event.type()
        if event_type in self._TOUCH_EVENTS:
            if not self.gui.touch_enabled:
                return True
            points = event.points()
            consumed = self._swipe_touch
            if event_type == QtCore.QEvent.Type.TouchBegin:
                self.reset_swipe()
                consumed = False
                if len(points) == 1:
                    position = points[0].globalPosition()
                    if self._can_swipe(obj, position):
                        self._swipe_start = position
                        self._swipe_page = self.gui.main_page.currentWidget()
                        self._swipe_touch = True
                        consumed = True
            elif event_type == QtCore.QEvent.Type.TouchEnd and self._swipe_touch:
                if len(points) == 1:
                    self._finish_swipe(points[0].globalPosition())
                else:
                    self.reset_swipe()
            elif event_type == QtCore.QEvent.Type.TouchCancel:
                self.reset_swipe()
            return consumed
        if event_type not in self._MOUSE_EVENTS:
            return False
        if (
            not self.gui.touch_enabled
            and event.deviceType() == QtGui.QInputDevice.DeviceType.TouchScreen
        ):
            return True
        if self._swipe_touch and event_type == QtCore.QEvent.Type.MouseButtonPress:
            self.reset_swipe()
        elif self._swipe_touch:
            return False

        if event_type == QtCore.QEvent.Type.MouseButtonPress:
            self.reset_swipe()
            if event.button() == QtCore.Qt.MouseButton.LeftButton and self._can_swipe(
                obj, event.globalPosition()
            ):
                self._swipe_start = event.globalPosition()
                self._swipe_page = self.gui.main_page.currentWidget()
        elif event_type == QtCore.QEvent.Type.MouseButtonRelease:
            if event.button() == QtCore.Qt.MouseButton.LeftButton:
                self._finish_swipe(event.globalPosition())
        return False

    def _can_swipe(self, obj, position):
        if self.gui.stack_widget.currentIndex() != 1:
            return False
        page = self.gui.main_page.currentWidget()
        if page in (self.gui.map_widget, self.gui.course_profile_graph_widget):
            if not page.lock_status:
                return False

        widget = obj
        if not isinstance(widget, QtWidgets.QWidget):
            widget = QtWidgets.QApplication.widgetAt(position.toPoint())
        while widget is not None:
            if isinstance(widget, QtWidgets.QAbstractButton):
                return False
            if widget is page:
                return True
            widget = widget.parentWidget()
        return False

    def _finish_swipe(self, position):
        start = self._swipe_start
        page = self._swipe_page
        self.reset_swipe()
        if start is None:
            return
        if self.gui.stack_widget.currentIndex() != 1:
            return
        if page is not self.gui.main_page.currentWidget():
            return
        if page in (self.gui.map_widget, self.gui.course_profile_graph_widget):
            if not page.lock_status:
                return

        delta = position - start
        if abs(delta.x()) < max(40, page.width() * 0.12):
            return
        if abs(delta.x()) < abs(delta.y()) * 1.4:
            return
        direction = 1 if delta.x() < 0 else -1
        QtCore.QTimer.singleShot(0, lambda: self.gui.scroll(direction))
