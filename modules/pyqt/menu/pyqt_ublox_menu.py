import math
from pathlib import Path

from modules._qt_qtwidgets import (
    QT_NO_FOCUS,
    QT_SCROLLBAR_ALWAYSOFF,
    QT_STRONG_FOCUS,
    QtCore,
    QtGui,
    QtWidgets,
    qasync,
)
from modules.app_logger import app_logger
from modules.pyqt.components.static_map import (
    GeoPoint,
    StaticMapMarker,
    StaticMapRenderer,
    StaticMapScene,
)
from modules.pyqt.menu.pyqt_menu_widget import (
    ListItemWidget,
    ListWidget,
    MenuWidget,
)
from modules.sensor.gps.ublox_support.qzss_dcr import Category, JMA_MESSAGE_TYPE
from modules.sensor.gps.ublox_support.qzss_dcr_view import (
    build_list_view,
    build_popup_view,
    build_typhoon_map_view,
    format_qzss_dcr_detail,
)

_COLLECTING_ICON_PATH = Path("img/qzss_collecting.svg")


class GPSMenuWidget(MenuWidget):
    ASSISTNOW_BUTTON = "AssistNow (u-blox)"
    POWER_SAVE_BUTTON = "Power Save Mode (u-blox)"
    QZSS_DCR_BUTTON = "QZSS DCR (u-blox)"

    def setup_menu(self):
        self.gps_ublox = self.config.G_GPS_UBLOX
        button_conf = (
            (self.ASSISTNOW_BUTTON, "toggle", self.onoff_assistnow),
            (self.POWER_SAVE_BUTTON, "toggle", self.onoff_power_save),
            (self.QZSS_DCR_BUTTON, "toggle", self.onoff_qzss_dcr),
        )
        self.add_buttons(button_conf)
        self.update_toggles()

    def preprocess(self):
        self.update_toggles()

    async def _set_qzss_dcr(self, enabled):
        previous = bool(self.gps_ublox["QZSS_DCR"])
        self.gps_ublox["QZSS_DCR"] = enabled
        self.update_toggles()
        if await self.sensor_gps.set_qzss_dcr_enabled(enabled):
            return True
        self.gps_ublox["QZSS_DCR"] = previous
        self.update_toggles()
        return False

    @qasync.asyncSlot()
    async def onoff_power_save(self):
        enabled = not bool(self.gps_ublox["POWER_SAVE"])
        previous_qzss_dcr = bool(self.gps_ublox["QZSS_DCR"])

        if enabled and self.gps_ublox["QZSS_DCR"]:
            if not await self._set_qzss_dcr(False):
                app_logger.warning(
                    "Power Save Mode toggle skipped: QZSS DCR disable failed"
                )
                return

        self.gps_ublox["POWER_SAVE"] = enabled
        self.update_toggles()
        if not await self.sensor_gps.set_power_save_enabled(enabled):
            self.gps_ublox["POWER_SAVE"] = not enabled
            self.gps_ublox["QZSS_DCR"] = previous_qzss_dcr
            if enabled and previous_qzss_dcr:
                await self.sensor_gps.set_qzss_dcr_enabled(True)
            self.update_toggles()
            power_save_status = self.sensor_gps.power_save_status
            app_logger.warning(
                "Power Save Mode toggle skipped: "
                f"{power_save_status['status']} {power_save_status['error']}"
            )
            return
        self.config.setting.write_config()
        self.update_toggles()

    @qasync.asyncSlot()
    async def onoff_qzss_dcr(self):
        if self.gps_ublox["POWER_SAVE"]:
            self.update_toggles()
            return

        if await self._set_qzss_dcr(not bool(self.gps_ublox["QZSS_DCR"])):
            self.config.setting.write_config()
        self.update_toggles()

    def onoff_assistnow(self):
        assistnow = self.gps_ublox["ASSISTNOW"]
        enabled = not bool(assistnow["STATUS"])
        self.sensor_gps.set_assistnow_enabled(enabled)
        self.config.setting.write_config()
        self.update_toggles()

    def update_toggles(self):
        assistnow_enabled = bool(self.gps_ublox["ASSISTNOW"]["STATUS"])
        self.buttons[self.ASSISTNOW_BUTTON].change_toggle(assistnow_enabled)

        power_save_enabled = bool(self.gps_ublox["POWER_SAVE"])
        self.buttons[self.POWER_SAVE_BUTTON].change_toggle(power_save_enabled)

        self.buttons[self.QZSS_DCR_BUTTON].onoff_button(not power_save_enabled)
        self.buttons[self.QZSS_DCR_BUTTON].change_toggle(
            False if power_save_enabled else bool(self.gps_ublox["QZSS_DCR"])
        )


class QzssDcrViewerWidget(MenuWidget):
    ACTIVE_PAGE = "Active Alerts"
    HISTORY_PAGE = "History"

    def setup_menu(self):
        button_conf = (
            (self.ACTIVE_PAGE, "submenu", self.show_active),
            (self.HISTORY_PAGE, "submenu", self.show_history),
        )
        self.add_buttons(button_conf)

    def preprocess(self):
        store = getattr(self.sensor_gps, "qzss_dcr_store", None)
        active = store.get_active_events() if store else ()
        history = store.get_history() if store else ()
        self.buttons[self.ACTIVE_PAGE].setText(f"{self.ACTIVE_PAGE} ({len(active)})")
        self.buttons[self.HISTORY_PAGE].setText(f"{self.HISTORY_PAGE} ({len(history)})")

    def show_active(self):
        self.change_page(self.ACTIVE_PAGE, preprocess=True)

    def show_history(self):
        self.change_page(self.HISTORY_PAGE, preprocess=True)


class QzssDcrDetailBrowser(QtWidgets.QTextBrowser):
    def focusNextPrevChild(self, is_next):
        scrollbar = self.verticalScrollBar()
        page_step = max(1, int(self.viewport().height() * 0.8))
        direction = 1 if is_next else -1
        scrollbar.setValue(scrollbar.value() + direction * page_step)
        return True


class QzssDcrTyphoonWidget(QtWidgets.QWidget):
    MAP_ZOOM = 4

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.renderer = StaticMapRenderer(config, zoom=self.MAP_ZOOM)
        self.scene = None
        self.map_source_image = None

        self.summary = QtWidgets.QLabel()
        self.summary.setWordWrap(True)
        self.summary.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.summary.setStyleSheet("font-weight: 700; padding: 3px;")

        self.map_label = QtWidgets.QLabel()
        self.map_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.map_label.setMinimumSize(120, 100)

        layout_type = (
            QtWidgets.QHBoxLayout if config.gui.horizontal else QtWidgets.QVBoxLayout
        )
        layout = layout_type(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        if config.gui.horizontal:
            layout.addWidget(self.map_label, 2)
            layout.addWidget(self.summary, 1)
        else:
            layout.addWidget(self.summary)
            layout.addWidget(self.map_label, 1)

    @staticmethod
    def _marker_label(forecast):
        try:
            date, time = forecast.reference_time.split()
            day = date.split("/")[1]
            hour, minute = time.split(":")
            clock = f"{hour}時" if minute == "00" else time
            label = f"{day}日{clock}"
            if forecast.reference_type in {"実況", "推定"}:
                label += f" {forecast.reference_type}"
            return label
        except (IndexError, ValueError):
            return forecast.reference_time

    def _current_location_marker(self):
        gps_values = self.config.logger.sensor.values["GPS"]
        latitude = gps_values["lat"]
        longitude = gps_values["lon"]
        try:
            valid = math.isfinite(float(latitude)) and math.isfinite(float(longitude))
        except (TypeError, ValueError):
            valid = False
        if not valid:
            return None
        return StaticMapMarker(
            GeoPoint(float(latitude), float(longitude)),
            label="現在地",
            color="#1565C0",
            radius=5,
        )

    def set_view(self, view):
        actual = next(
            (
                forecast
                for forecast in view.forecasts
                if forecast.reference_type in {"実況", "推定"}
            ),
            view.forecasts[0] if view.forecasts else None,
        )
        if actual is None:
            self.summary.setText(view.timestamp)
            self.scene = None
            return

        strength = "　".join(
            value for value in (actual.scale, actual.intensity) if value
        )
        metrics = "　".join(
            value
            for value in (
                actual.pressure,
                f"最大{actual.wind}" if actual.wind else "",
                f"瞬間{actual.gust}" if actual.gust else "",
            )
            if value
        )
        self.summary.setText(
            "\n".join(value for value in (view.timestamp, strength, metrics) if value)
        )

        path = tuple(
            GeoPoint(forecast.latitude, forecast.longitude)
            for forecast in view.forecasts
        )
        markers = [
            StaticMapMarker(
                point,
                label=self._marker_label(forecast),
                color=(
                    "#D7191C"
                    if forecast.reference_type in {"実況", "推定"}
                    else "#F4A300"
                ),
                radius=6 if forecast.reference_type in {"実況", "推定"} else 4,
            )
            for point, forecast in zip(path, view.forecasts)
        ]
        current_location = self._current_location_marker()
        if current_location is not None:
            markers.append(current_location)
        self.scene = StaticMapScene(
            path=path,
            markers=tuple(markers),
            line_color="#D7191C",
            line_width=3,
        )
        self.map_source_image = None

    def _target_size(self):
        return (
            max(160, self.map_label.width()),
            max(100, self.map_label.height()),
        )

    def _update_pixmap(self):
        if self.map_source_image is None:
            return
        pixmap = QtGui.QPixmap.fromImage(self.map_source_image).scaled(
            self.map_label.size(),
            QtCore.Qt.AspectRatioMode.IgnoreAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        self.map_label.setPixmap(pixmap)

    async def render_map(self):
        if self.scene is None:
            return True
        rendered = await self.renderer.render(self.scene, self._target_size())
        self.map_source_image = rendered.image
        self._update_pixmap()
        return rendered.complete

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_pixmap()


class QzssDcrDetailWidget(MenuWidget):
    STYLES = """
      QTextBrowser {
        background-color: white;
        border: 0;
        padding: 6px;
      }
      QScrollBar:vertical {
        width: 10px;
      }
    """

    def setup_menu(self):
        self.make_menu_layout(QtWidgets.QVBoxLayout)
        self.detail_screen = QzssDcrDetailBrowser()
        self.detail_screen.setHorizontalScrollBarPolicy(QT_SCROLLBAR_ALWAYSOFF)
        self.detail_screen.setFocusPolicy(QT_STRONG_FOCUS)
        self.detail_screen.setStyleSheet(self.STYLES)
        self.typhoon_screen = QzssDcrTyphoonWidget(self.config)
        self.detail_stack = QtWidgets.QStackedLayout()
        self.detail_stack.addWidget(self.detail_screen)
        self.detail_stack.addWidget(self.typhoon_screen)
        self.menu_layout.addLayout(self.detail_stack)
        self.typhoon_timer = QtCore.QTimer(parent=self)
        self.typhoon_timer.timeout.connect(self.update_typhoon_map)
        self.focus_widget = self.detail_screen

    def preprocess(self, event):
        self.typhoon_timer.stop()
        if (
            event.get("message_type") == JMA_MESSAGE_TYPE
            and event.get("category_no") == Category.TYPHOON
        ):
            view = build_typhoon_map_view(event)
            if view.forecasts:
                self.page_name_label.setText(view.title)
                self.typhoon_screen.set_view(view)
                self.detail_stack.setCurrentWidget(self.typhoon_screen)
                self.focus_widget = self.back_button
                self.typhoon_timer.start(self.config.G_DRAW_INTERVAL)
                QtCore.QTimer.singleShot(0, self.update_typhoon_map)
                self._resize_title()
                return

        title, detail = format_qzss_dcr_detail(event)
        self.page_name_label.setText(title)
        self.detail_screen.setHtml(detail)
        self.detail_screen.verticalScrollBar().setValue(0)
        self.detail_stack.setCurrentWidget(self.detail_screen)
        self.focus_widget = self.detail_screen
        self._resize_title()

    @qasync.asyncSlot()
    async def update_typhoon_map(self):
        if await self.typhoon_screen.render_map():
            self.typhoon_timer.stop()

    def on_back_menu(self):
        self.typhoon_timer.stop()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_title()

    def _resize_title(self):
        available_width = max(1, self.width() - 2 * self.icon_x - 20)
        font = self.page_name_label.font()
        for size in range(max(14, min(self.width(), self.height()) // 12), 13, -1):
            font.setPixelSize(size)
            if (
                QtGui.QFontMetrics(font).horizontalAdvance(self.page_name_label.text())
                <= available_width
            ):
                break
        self.page_name_label.setFont(font)


class QzssDcrEventListWidget(ListWidget):
    def connect_buttons(self):
        self.list.itemClicked.connect(self._show_clicked_event)

    def preprocess(self):
        active = self.page_name == QzssDcrViewerWidget.ACTIVE_PAGE
        store = getattr(self.sensor_gps, "qzss_dcr_store", None)
        events = (
            (store.get_active_events() if active else store.get_history())
            if store
            else ()
        )
        self.list.clear()
        self.list.verticalScrollBar().setValue(0)
        self.focus_widget = self.back_button

        if not events:
            empty_text = "No active alerts" if active else "No alert history"
            empty_item = ListItemWidget(self, empty_text)
            empty_item.setFocusPolicy(QT_NO_FOCUS)
            self.add_list_item(empty_item)
            return

        first_item = None
        for event in events:
            view = build_list_view(event, history=not active)
            item = ListItemWidget(
                self,
                view.title,
                view.detail,
                detail_icon=self._event_list_icon(event) if active else None,
                detail_left=15,
            )
            item.qzss_event = event
            item.enter_signal.connect(
                lambda current_event=event: self._show_event_detail(current_event)
            )
            self.add_list_item(item)
            if first_item is None:
                first_item = item

        self.list.setCurrentRow(0)
        self.focus_widget = first_item

    def _show_clicked_event(self, list_item):
        item = self.list.itemWidget(list_item)
        event = getattr(item, "qzss_event", None)
        if event:
            self._show_event_detail(event)

    @staticmethod
    def _event_list_icon(event):
        if event.get("status") == "active":
            return None
        return QtGui.QIcon(str(_COLLECTING_ICON_PATH))

    def _show_event_detail(self, event):
        self.change_page(
            "QZSS DCR Detail",
            preprocess=True,
            event=event,
        )


def start_qzss_dcr_popup_monitor(gui):
    timer = QtCore.QTimer(parent=gui)
    timer.timeout.connect(lambda: _check_qzss_dcr_popup(gui))
    timer.start(1000)
    gui._qzss_dcr_popup_timer = timer


def _check_qzss_dcr_popup(gui):
    qzss_config = gui.config.G_GPS_UBLOX
    sensor_gps = getattr(gui.sensor, "sensor_gps", None)
    store = getattr(sensor_gps, "qzss_dcr_store", None)
    if store is None:
        return

    pending_events = store.get_pending_popup_events()
    if not qzss_config["QZSS_DCR"] and not any(
        event.get("is_test") for event in pending_events
    ):
        return

    gps_values = getattr(sensor_gps, "values", {})
    latitude = gps_values.get("lat")
    longitude = gps_values.get("lon")
    margin_km = qzss_config["QZSS_DCR_POPUP_DISTANCE_KM"]

    for event in pending_events:
        weather_pairs = None
        if event.get("is_training") and not gui.config.G_DEBUG:
            store.mark_popup_handled(event)
            continue

        if not event.get("is_cancel") and not event.get("is_test"):
            location_status = store.popup_location_status(
                event,
                latitude,
                longitude,
                margin_km=margin_km,
            )
            if location_status == "far":
                continue
            if event.get("category_no") == Category.WEATHER:
                weather_pairs = store.popup_weather_pairs(
                    event,
                    latitude,
                    longitude,
                    margin_km,
                )
                if weather_pairs == set():
                    continue

        priority = event.get("priority")
        if priority not in ("urgent", "warning"):
            store.mark_popup_handled(event)
            continue

        view = build_popup_view(event, weather_pairs=weather_pairs)
        timeout = 10
        buzzer_sound = "alert" if priority == "urgent" else "beep"
        if priority == "urgent" and gui.dialog_exists():
            gui.delete_popup()
        gui.show_popup_multiline(
            view.title,
            "\n".join(view.lines),
            timeout=timeout,
            buzzer_sound=buzzer_sound,
            alert_level=(
                None if event.get("is_cancel") or event.get("is_training") else priority
            ),
        )
        store.mark_popup_handled(event, displayed=True)
        break
