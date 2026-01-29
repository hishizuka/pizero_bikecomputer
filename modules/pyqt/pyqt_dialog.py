"""
Cached dialog system for popup messages.
Classes are defined at module level for reuse, avoiding repeated class
definitions and widget creation on each dialog display.
"""
from modules._qt_qtwidgets import (
    QT_ALIGN_CENTER,
    QT_ALIGN_LEFT,
    QtCore,
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

    def __init__(self, *args):
        super().__init__(*args, objectName="background")
        self.setStyleSheet(self.STYLES)
        self.back = None  # Callback for back action


class CachedDialog:
    """
    Manages a reusable dialog instance with three layout modes:
    - icon: title with left icon
    - message: title + message (two lines)
    - simple: title only

    Buttons (up to 2) are pre-created and shown/hidden as needed.
    """

    MAX_BUTTONS = 2

    def __init__(self, stack_widget, main_window, pe_widget):
        self._stack_widget = stack_widget
        self._main_window = main_window
        self._pe_widget = pe_widget

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

        self._build()

    def _build(self):
        """Build all widgets once during initialization."""
        # Background
        self._background = DialogBackground()
        self._back_layout = QtWidgets.QVBoxLayout(self._background)

        # Container
        self._container = DialogContainer(self._background)
        self._container.pe_widget = self._pe_widget
        self._container.setAutoFillBackground(True)
        self._back_layout.addWidget(self._container)
        self._content_layout = QtWidgets.QVBoxLayout(self._container)
        self._content_layout.setSpacing(0)

        # Base font
        font = self._main_window.font()
        base_size = font.pointSize()

        # === Icon layout ===
        self._icon_widget = QtWidgets.QWidget(self._container)
        icon_layout = QtWidgets.QHBoxLayout(self._icon_widget)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon_layout.setSpacing(0)

        self._icon_label = QtWidgets.QLabel()
        font.setPointSize(int(base_size * 2))
        self._icon_title_label = QtWidgets.QLabel(objectName="title_label")
        self._icon_title_label.setWordWrap(True)
        self._icon_title_label.setFont(font)
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

        font.setPointSize(int(base_size * 1.5))
        self._message_title_label = QtWidgets.QLabel(objectName="title_label")
        self._message_title_label.setWordWrap(True)
        self._message_title_label.setFont(font)
        self._message_title_label.setStyleSheet("font-weight: bold;")
        self._message_title_label.setContentsMargins(5, 5, 5, 5)

        self._message_label = QtWidgets.QLabel()
        self._message_label.setWordWrap(True)
        self._message_label.setFont(font)
        self._message_label.setContentsMargins(5, 5, 5, 5)

        message_layout.addWidget(self._message_title_label)
        message_layout.addWidget(self._message_label)
        self._content_layout.addWidget(self._message_widget)

        # === Simple layout ===
        font.setPointSize(int(base_size * 2))
        self._simple_title_label = QtWidgets.QLabel(objectName="title_label")
        self._simple_title_label.setWordWrap(True)
        self._simple_title_label.setFont(font)
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
        timeout = msg.get("timeout", 5) or 5

        self._current_fn = fn

        # Store back callback
        def back():
            close_callback(self._stored_index)

        self._background.back = back

        # Position container
        self._back_layout.setAlignment(self._container, position)

        # Select layout mode
        if title_icon is not None:
            self._icon_label.setPixmap(title_icon.pixmap(QtCore.QSize(32, 32)))
            self._icon_title_label.setText(title)
            self._icon_widget.show()
        elif message is not None:
            self._message_title_label.setText(title)
            self._message_title_label.setAlignment(text_align)
            self._message_label.setText(message)
            self._message_label.setAlignment(text_align)
            self._message_widget.show()
        else:
            self._simple_title_label.setText(title)
            self._simple_title_label.setAlignment(text_align)
            self._simple_title_label.show()

        # Buttons
        if button_num == 0:
            # Auto-close with timeout
            self._timeout_timer = QtCore.QTimer()
            self._timeout_timer.setSingleShot(True)
            self._timeout_timer.timeout.connect(back)
            self._timeout_timer.start(timeout * 1000)
        else:
            self._button_widget.show()
            for i, btn in enumerate(self._buttons):
                if i < button_num:
                    btn.setText(button_label[i] if i < len(button_label) else "")
                    btn.clicked.connect(back)
                    if i == 0 and fn is not None:
                        btn.clicked.connect(fn)
                    btn.show()
                else:
                    btn.hide()

    def show(self, stack_widget_index):
        """Add dialog to stack and display."""
        self._stored_index = stack_widget_index
        self._stack_widget.addWidget(self._background)
        self._stack_widget.setCurrentWidget(self._background)
        self._background.show()

    def hide(self):
        """Remove dialog from stack (without destroying)."""
        self._stop_timer()
        self._disconnect_buttons()
        self._stack_widget.removeWidget(self._background)
        self._background.hide()

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
