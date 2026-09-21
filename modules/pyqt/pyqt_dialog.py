"""
Cached dialog system for popup messages.
Classes are defined at module level for reuse, avoiding repeated class
definitions and widget creation on each dialog display.
"""

import asyncio

from modules._qt_qtwidgets import (
    QT_ALIGN_BOTTOM,
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


class RainBannerContent(QtWidgets.QWidget):
    """Center an umbrella and a single phrase with a shared text baseline."""

    def set_content(self, title, icon):
        self.setAccessibleName(title)
        self._icon = icon.pixmap(36, 36)
        self._words = []
        bounds = QtCore.QRectF()
        for word in title.split():
            number = word.isdecimal()
            font = QtGui.QFont(self.font())
            font.setPixelSize(36 if number else 26 if title == "Raining" else 18)
            font.setBold(False)
            path = QtGui.QPainterPath()
            path.addText(0, 0, font, word)
            bounds = bounds.united(path.boundingRect())
            width = QtGui.QFontMetricsF(font).horizontalAdvance(word)
            self._words.append((word, font, width))
        self._baseline = -bounds.center().y()
        self._width = 48 + sum(width for _, _, width in self._words)
        self._width += 6 * (len(self._words) - 1)
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        scale = min(1.0, self.width() / (self._width + 16))
        painter.translate(self.width() / 2, self.height() / 2)
        painter.scale(scale, scale)
        x = -self._width / 2
        painter.drawPixmap(QtCore.QPointF(x, -18), self._icon)
        x += 48
        painter.setPen(QtGui.QColor("white"))
        for word, font, width in self._words:
            painter.setFont(font)
            painter.drawText(QtCore.QPointF(x, self._baseline), word)
            x += width + 6


class CachedDialog:
    """
    Manages a reusable dialog instance with four layout modes:
    - icon: title with left icon
    - message: title with optional icon + multiline message
    - simple: title only
    - rain: centered phrase with a right-side OK button

    The optional banner frame controls only edge-to-edge bottom placement.

    Buttons (up to 2) are pre-created and shown/hidden as needed.
    """

    MAX_BUTTONS = 2
    ALERT_COLORS = {
        "urgent": ("black", "#FF0000"),
        "warning": ("black", "#FFFF00"),
    }

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
        self._message_icon_label = None
        self._message_title_label = None
        self._message_label = None

        self._simple_title_label = None

        # Buttons
        self._button_widget = None
        self._buttons = []

        # State
        self._stored_index = None
        self._ok_fn = None
        self._back_fn = None
        self._qzss_widget = None

        self._build()
        self._timeout_timer = QtCore.QTimer(self._background)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self.trigger_back)

    def _build(self):
        """Build all widgets once during initialization."""
        # Background
        self._background = DialogBackground(
            self._stack_widget, dual_mode=self._dual_mode
        )
        self._back_layout = QtWidgets.QVBoxLayout(self._background)
        self._default_back_margins = self._back_layout.contentsMargins()

        # Container
        self._container = DialogContainer(self._background)
        self._container.pe_widget = self._pe_widget
        self._container.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self._container.setAutoFillBackground(True)
        self._back_layout.addWidget(self._container)
        self._content_layout = QtWidgets.QVBoxLayout(self._container)
        self._content_layout.setSpacing(0)
        self._default_content_margins = self._content_layout.contentsMargins()

        self._rain_widget = RainBannerContent(self._container)
        self._content_layout.addWidget(self._rain_widget, stretch=1)

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

        message_title_layout = QtWidgets.QHBoxLayout()
        message_title_layout.setSpacing(0)
        self._message_icon_label = QtWidgets.QLabel()
        self._message_icon_label.setFixedSize(36, 36)
        message_title_layout.addWidget(self._message_icon_label)
        message_title_layout.addWidget(self._message_title_label, stretch=1)
        message_layout.addLayout(message_title_layout)
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
        self._rain_widget.hide()
        self._icon_widget.hide()
        self._message_widget.hide()
        self._message_icon_label.hide()
        self._simple_title_label.hide()
        self._button_widget.hide()

    def _disconnect_buttons(self):
        """Disconnect all button signals."""
        for btn in self._buttons:
            try:
                btn.clicked.disconnect()
            except TypeError:
                pass  # No connections

    @staticmethod
    def _set_label(label, text, align=None):
        """Set label text and optional alignment."""
        label.setText(text)
        if align is not None:
            label.setAlignment(align)

    def _show_layout(self, title, title_icon, message, text_align):
        """Show the appropriate layout based on dialog content."""
        if message is not None:
            if title_icon is not None:
                self._message_icon_label.setPixmap(title_icon.pixmap(36, 36))
                self._message_icon_label.show()
            self._set_label(self._message_title_label, title, text_align)
            self._set_label(self._message_label, message, text_align)
            self._message_widget.show()
            return
        if title_icon is not None:
            self._icon_label.setPixmap(title_icon.pixmap(QtCore.QSize(32, 32)))
            self._set_label(self._icon_title_label, title, QT_ALIGN_LEFT)
            self._icon_widget.show()
            return
        self._set_label(self._simple_title_label, title, text_align)
        self._simple_title_label.show()

    def _apply_colors(self, background_color, text_color, alert_level):
        background_color, text_color = self.ALERT_COLORS.get(
            alert_level,
            (background_color or "white", text_color or "black"),
        )
        dark = QtGui.QColor(background_color).lightness() < 128
        focus_background = background_color if dark else text_color
        focus_text = text_color if dark else background_color
        focus_border = f"border-color: {text_color};" if dark else ""
        self._container.setStyleSheet(
            f"DialogContainer {{ background-color: {background_color}; }}"
            f"DialogContainer QWidget {{ background-color: {background_color}; }}"
            f"DialogContainer QLabel {{"
            f" background-color: {background_color}; color: {text_color}; }}"
            f"DialogContainer DialogButton {{"
            f" background-color: {background_color}; color: {text_color}; }}"
            f"DialogContainer DialogButton:focus {{"
            f" background-color: {focus_background}; color: {focus_text};"
            f" {focus_border} }}"
            f"DialogContainer DialogButton:pressed {{"
            f" background-color: {text_color}; color: {background_color}; }}"
        )

    def _set_banner_frame(self, enabled):
        self._back_layout.setContentsMargins(
            QtCore.QMargins() if enabled else self._default_back_margins
        )
        if enabled:
            self._container.setStyleSheet(
                self._container.styleSheet()
                + "DialogContainer { border: 0; border-radius: 0; padding: 0; }"
            )

    def _set_rain_layout(self, enabled):
        direction = QtWidgets.QBoxLayout.Direction
        self._content_layout.setDirection(
            direction.LeftToRight if enabled else direction.TopToBottom
        )
        self._content_layout.setContentsMargins(
            QtCore.QMargins(0, 0, 8, 0)
            if enabled else self._default_content_margins
        )
        self._container.setMinimumHeight(72 if enabled else 0)
        self._container.setMaximumHeight(72 if enabled else 16777215)
        self._button_widget.layout().setContentsMargins(
            QtCore.QMargins() if enabled else QtCore.QMargins(5, 10, 5, 10)
        )
        for button in self._buttons:
            button.setFixedWidth(36 if enabled else 70)
            button.setMinimumHeight(32 if enabled else 0)
            button.setMaximumHeight(32 if enabled else 16777215)
            font = QtGui.QFont(self._main_window.font())
            if enabled:
                font.setPixelSize(14)
            button.setFont(font)
        if enabled:
            self._container.setStyleSheet(
                self._container.styleSheet()
                + "DialogContainer DialogButton { border-width: 1px; padding: 0; }"
            )

    def _configure_buttons(
        self, button_num, button_label, timeout_seconds, auto_close=False
    ):
        """Configure dialog buttons."""
        if button_num == 0 or auto_close:
            self._timeout_timer.start(timeout_seconds * 1000)
            if button_num == 0:
                return

        self._button_widget.show()
        for i, btn in enumerate(self._buttons):
            if i < button_num:
                btn.setText(button_label[i] if i < len(button_label) else "")
                if i == 0:
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
        self._timeout_timer.stop()
        self._disconnect_buttons()
        self._hide_all()
        if self._qzss_widget is not None:
            self._qzss_widget.hide()
        self._container.show()

        title = msg.get("title", "")
        title_icon = msg.get("title_icon")
        message = msg.get("message")
        button_num = msg.get("button_num", 0)
        button_label = msg.get("button_label") or ["OK", "Cancel"]
        position = msg.get("position", QT_ALIGN_CENTER)
        text_align = msg.get("text_align", QT_ALIGN_CENTER)
        fn = msg.get("fn")
        timeout_seconds = msg.get("timeout", 5) or 5
        background_color = msg.get("background_color", "white")
        text_color = msg.get("text_color", "black")
        alert_level = msg.get("alert_level")

        # Store back callback
        back = lambda: close_callback(self._stored_index)
        self._background.back = back
        self._ok_fn = fn
        self._back_fn = back

        if msg.get("layout") == "qzss":
            from modules.pyqt.components.qzss_alert import QzssAlertWidget

            self._container.hide()
            if self._qzss_widget is None:
                self._qzss_widget = QzssAlertWidget(self._background, self.trigger_back)
                self._qzss_widget.next_button.clicked.connect(
                    lambda: self._timeout_timer.start(10_000)
                )
            self._qzss_widget.set_event(
                msg["event"], msg["weather_pairs"]
            )
            self._timeout_timer.start(timeout_seconds * 1000)
            return

        # Position container
        banner = msg.get("frame") == "banner"
        self._back_layout.setAlignment(
            self._container, QT_ALIGN_BOTTOM if banner else position
        )

        self._apply_colors(background_color, text_color, alert_level)
        self._set_banner_frame(banner)
        rain = msg.get("layout") == "rain"
        self._set_rain_layout(rain)
        if rain:
            self._rain_widget.set_content(title, title_icon)
            self._rain_widget.show()
        else:
            self._show_layout(title, title_icon, message, text_align)
        self._configure_buttons(
            button_num,
            button_label,
            timeout_seconds,
            auto_close=msg.get("timeout") is not None,
        )

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
        if self._qzss_widget is not None and self._qzss_widget.isVisible():
            self._qzss_widget.setFocus()
            return
        for btn in self._buttons:
            if btn.isVisible():
                btn.setFocus()
                return
        self._container.setFocus()

    def hide(self):
        """Hide dialog (keep in stack for reuse)."""
        self._timeout_timer.stop()
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
        if self._qzss_widget is not None and self._qzss_widget.isVisible():
            return self.trigger_back()
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
