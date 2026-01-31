"""
Cached dialog system for popup messages.
Classes are defined at module level for reuse, avoiding repeated class
definitions and widget creation on each dialog display.
"""
import asyncio

from modules._qt_qtwidgets import (
    QT_ALIGN_CENTER,
    QT_ALIGN_LEFT,
    QtCore,
    QtGui,
    QtWidgets,
)


class DialogButton(QtWidgets.QPushButton):
    """Button with circular focus navigation."""

    next_button = None
    prev_button = None

    def focusNextPrevChild(self, is_next):
        if is_next:
            self.next_button.setFocus()
        else:
            self.prev_button.setFocus()
        return True


class DialogContainer(QtWidgets.QWidget):
    """Container widget with custom paint for dialog content."""

    pe_widget = None

    def showEvent(self, event):
        if not event.spontaneous():
            self.setFocus()
            QtCore.QTimer.singleShot(0, self.focusNextChild)

    def paintEvent(self, event):
        qp = QtWidgets.QStylePainter(self)
        opt = QtWidgets.QStyleOption()
        opt.initFrom(self)
        qp.drawPrimitive(self.pe_widget, opt)


class DialogBackground(QtWidgets.QWidget):
    """Semi-transparent background overlay for dialogs."""

    STYLES = """
      DialogContainer {
        border: 3px solid black;
        border-radius: 5px;
        padding: 10px;
      }
      DialogContainer DialogButton {
        border: 2px solid #AAAAAA;
        border-radius: 3px;
        text-align: center;
        padding: 3px;
      }
      DialogContainer DialogButton:pressed { background-color: black; }
      DialogContainer DialogButton:focus { background-color: black; color: white; }
    """

    def __init__(self, *args, dual_mode=False):
        super().__init__(*args, objectName="background")
        self.setStyleSheet(self.STYLES)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.back = None  # Callback for back action
        self._parent_widget = self.parent()
        self._dual_mode = dual_mode
        if self._parent_widget is not None:
            self._update_geometry()
            self._parent_widget.installEventFilter(self)

    def _update_geometry(self):
        """Update geometry based on dual mode setting."""
        if self._parent_widget is None:
            return
        pw = self._parent_widget.width()
        ph = self._parent_widget.height()
        if self._dual_mode:
            # Right half only in dual display mode
            left_w = pw // 2
            self.setGeometry(left_w, 0, pw - left_w, ph)
        else:
            self.setGeometry(0, 0, pw, ph)

    def eventFilter(self, obj, event):
        if obj == self._parent_widget and event.type() == QtCore.QEvent.Type.Resize:
            self._update_geometry()
        return False


class CachedDialog:
    """
    Manages a reusable dialog instance with three layout modes:
    - icon: title with left icon
    - message: title + message (two lines)
    - simple: title only

    Buttons (up to 2) are pre-created and shown/hidden as needed.
    """

    MAX_BUTTONS = 2

    def __init__(self, stack_widget, main_window, pe_widget, dual_mode=False):
        self._stack_widget = stack_widget
        self._main_window = main_window
        self._pe_widget = pe_widget
        self._dual_mode = dual_mode

        self._background = None
        self._container = None
        self._back_layout = None
        self._content_layout = None

        # Three layout modes
        self._icon_widget = None
        self._icon_label = None
        self._icon_title_label = None

        self._message_widget = None
        self._message_title_label = None
        self._message_label = None

        self._simple_title_label = None

        # Buttons
        self._button_widget = None
        self._buttons = []

        # State
        self._timeout_timer = None
        self._current_fn = None
        self._stored_index = None
        self._ok_fn = None
        self._back_fn = None

        self._build()

    def _build(self):
        """Build all widgets once during initialization."""
        # Background
        self._background = DialogBackground(self._stack_widget, dual_mode=self._dual_mode)
        self._back_layout = QtWidgets.QVBoxLayout(self._background)

        # Container
        self._container = DialogContainer(self._background)
        self._container.pe_widget = self._pe_widget
        self._container.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self._container.setAutoFillBackground(True)
        self._back_layout.addWidget(self._container)
        self._content_layout = QtWidgets.QVBoxLayout(self._container)
        self._content_layout.setSpacing(0)

        # Create fonts with different sizes
        base_font = self._main_window.font()
        base_size = base_font.pointSize()

        large_font = QtGui.QFont(base_font)
        large_font.setPointSize(int(base_size * 2))

        medium_font = QtGui.QFont(base_font)
        medium_font.setPointSize(int(base_size * 1.5))

        # === Icon layout ===
        self._icon_widget = QtWidgets.QWidget(self._container)
        icon_layout = QtWidgets.QHBoxLayout(self._icon_widget)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon_layout.setSpacing(0)

        self._icon_label = QtWidgets.QLabel()
        self._icon_title_label = QtWidgets.QLabel(objectName="title_label")
        self._icon_title_label.setWordWrap(True)
        self._icon_title_label.setFont(large_font)
        self._icon_title_label.setContentsMargins(5, 5, 5, 5)
        self._icon_title_label.setAlignment(QT_ALIGN_LEFT)

        icon_layout.addWidget(self._icon_label)
        icon_layout.addWidget(self._icon_title_label, stretch=2)
        self._content_layout.addWidget(self._icon_widget)

        # === Message layout ===
        self._message_widget = QtWidgets.QWidget(self._container)
        message_layout = QtWidgets.QVBoxLayout(self._message_widget)
        message_layout.setContentsMargins(0, 0, 0, 0)
        message_layout.setSpacing(0)

        self._message_title_label = QtWidgets.QLabel(objectName="title_label")
        self._message_title_label.setWordWrap(True)
        self._message_title_label.setFont(medium_font)
        self._message_title_label.setStyleSheet("font-weight: bold;")
        self._message_title_label.setContentsMargins(5, 5, 5, 5)

        self._message_label = QtWidgets.QLabel()
        self._message_label.setWordWrap(True)
        self._message_label.setFont(medium_font)
        self._message_label.setContentsMargins(5, 5, 5, 5)

        message_layout.addWidget(self._message_title_label)
        message_layout.addWidget(self._message_label)
        self._content_layout.addWidget(self._message_widget)

        # === Simple layout ===
        self._simple_title_label = QtWidgets.QLabel(objectName="title_label")
        self._simple_title_label.setWordWrap(True)
        self._simple_title_label.setFont(large_font)
        self._simple_title_label.setContentsMargins(5, 5, 5, 5)
        self._content_layout.addWidget(self._simple_title_label)

        # === Buttons ===
        self._button_widget = QtWidgets.QWidget(self._container)
        button_layout = QtWidgets.QHBoxLayout(self._button_widget)
        button_layout.setContentsMargins(5, 10, 5, 10)
        button_layout.setSpacing(10)

        for _ in range(self.MAX_BUTTONS):
            btn = DialogButton(parent=self._button_widget)
            btn.setFixedWidth(70)
            button_layout.addWidget(btn)
            self._buttons.append(btn)

        # Circular focus navigation
        for i, btn in enumerate(self._buttons):
            btn.next_button = self._buttons[(i + 1) % self.MAX_BUTTONS]
            btn.prev_button = self._buttons[i - 1]

        self._content_layout.addWidget(self._button_widget)

        # Initially hide all
        self._hide_all()

    def _hide_all(self):
        """Hide all layout variants."""
        self._icon_widget.hide()
        self._message_widget.hide()
        self._simple_title_label.hide()
        self._button_widget.hide()

    def _disconnect_buttons(self):
        """Disconnect all button signals."""
        for btn in self._buttons:
            try:
                btn.clicked.disconnect()
            except TypeError:
                pass  # No connections

    def _stop_timer(self):
        """Stop timeout timer if running."""
        if self._timeout_timer is not None:
            self._timeout_timer.stop()
            self._timeout_timer = None

    @staticmethod
    def _set_label(label, text, align=None):
        """Set label text and optional alignment."""
        label.setText(text)
        if align is not None:
            label.setAlignment(align)

    def _show_layout(self, title, title_icon, message, text_align):
        """Show the appropriate layout based on dialog content."""
        if title_icon is not None:
            self._icon_label.setPixmap(title_icon.pixmap(QtCore.QSize(32, 32)))
            self._set_label(self._icon_title_label, title, QT_ALIGN_LEFT)
            self._icon_widget.show()
            return
        if message is not None:
            self._set_label(self._message_title_label, title, text_align)
            self._set_label(self._message_label, message, text_align)
            self._message_widget.show()
            return
        self._set_label(self._simple_title_label, title, text_align)
        self._simple_title_label.show()

    def _configure_buttons(self, button_num, button_label, fn, back, timeout_seconds):
        """Configure dialog buttons."""
        if button_num == 0:
            self._timeout_timer = QtCore.QTimer()
            self._timeout_timer.setSingleShot(True)
            self._timeout_timer.timeout.connect(back)
            self._timeout_timer.start(timeout_seconds * 1000)
            return

        self._button_widget.show()
        for i, btn in enumerate(self._buttons):
            if i < button_num:
                btn.setText(button_label[i] if i < len(button_label) else "")
                if i == 0 and fn is not None:
                    btn.clicked.connect(self.trigger_ok)
                else:
                    btn.clicked.connect(self.trigger_back)
                btn.show()
            else:
                btn.hide()

    def configure(self, msg, close_callback):
        """
        Configure dialog for display.

        Args:
            msg: dict with title, title_icon, message, button_num,
                 button_label, position, text_align, fn, timeout
            close_callback: function to call on close (receives stored_index)
        """
        self._stop_timer()
        self._disconnect_buttons()
        self._hide_all()

        title = msg.get("title", "")
        title_icon = msg.get("title_icon")
        message = msg.get("message")
        button_num = msg.get("button_num", 0)
        button_label = msg.get("button_label") or ["OK", "Cancel"]
        position = msg.get("position", QT_ALIGN_CENTER)
        text_align = msg.get("text_align", QT_ALIGN_CENTER)
        fn = msg.get("fn")
        timeout_seconds = msg.get("timeout", 5) or 5

        self._current_fn = fn

        # Store back callback
        back = lambda: close_callback(self._stored_index)
        self._background.back = back
        self._ok_fn = fn
        self._back_fn = back

        # Position container
        self._back_layout.setAlignment(self._container, position)

        self._show_layout(title, title_icon, message, text_align)
        self._configure_buttons(button_num, button_label, fn, back, timeout_seconds)

    def add_to_stack(self):
        """Prepare dialog overlay (call after main pages are added)."""
        self._background.hide()
        self._background.raise_()

    def show(self, stack_widget_index):
        """Display dialog (already pre-added to stack)."""
        self._stored_index = stack_widget_index
        self._background.raise_()
        self._background.show()
        QtCore.QTimer.singleShot(0, self._apply_focus)

    def _apply_focus(self):
        """Focus the first visible button when dialog is shown."""
        for btn in self._buttons:
            if btn.isVisible():
                btn.setFocus()
                return
        self._container.setFocus()

    def hide(self):
        """Hide dialog (keep in stack for reuse)."""
        self._stop_timer()
        self._disconnect_buttons()
        self._background.hide()

    def trigger_ok(self):
        """Run OK callback then close dialog."""
        if callable(self._ok_fn):
            result = self._ok_fn()
            if asyncio.iscoroutine(result):
                asyncio.create_task(result)
        self.trigger_back()
        return True

    def trigger_back(self):
        """Close dialog without calling OK callback."""
        if callable(self._back_fn):
            self._back_fn()
        return True

    def click_primary(self):
        """Trigger OK action even if focus is elsewhere."""
        if not self._button_widget.isVisible():
            return False
        return self.trigger_ok()

    def change_title(self, title):
        """Update visible title label."""
        if self._icon_widget.isVisible():
            self._icon_title_label.setText(title)
        elif self._message_widget.isVisible():
            self._message_title_label.setText(title)
        else:
            self._simple_title_label.setText(title)

    def change_button_label(self, label):
        """Update first button label."""
        if self._buttons and self._buttons[0].isVisible():
            self._buttons[0].setText(label)

    @property
    def background(self):
        return self._background
