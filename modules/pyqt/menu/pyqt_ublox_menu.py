from modules.app_logger import app_logger
from modules.qt._qt_qtwidgets import qasync
from .pyqt_qzss_menu import GPSMenuWidget as QzssGPSMenuWidget


class GPSMenuWidget(QzssGPSMenuWidget):
    ASSISTNOW_BUTTON = "AssistNow (u-blox)"
    POWER_SAVE_BUTTON = "Power Save Mode (u-blox)"

    def setup_menu(self):
        self.gps_ublox = self.config.G_GPS_UBLOX
        button_conf = (
            (self.ASSISTNOW_BUTTON, "toggle", self.onoff_assistnow),
            (self.POWER_SAVE_BUTTON, "toggle", self.onoff_power_save),
            (self.QZSS_DCR_BUTTON, "toggle", self.onoff_qzss_dcr),
        )
        self.add_buttons(button_conf)
        self.update_toggles()

    @qasync.asyncSlot()
    async def onoff_power_save(self):
        if self._settings_changing or self.sensor_gps.qzss_dcr_changing:
            return
        with self.changing_settings():
            await self._set_power_save()

    async def _set_power_save(self):
        enabled = not bool(self.gps_ublox["POWER_SAVE"])
        previous_qzss_dcr = bool(self.config.G_GPS_QZSS_DCR["STATUS"])

        if enabled and self.config.G_GPS_QZSS_DCR["STATUS"]:
            if not await self._set_qzss_dcr(False):
                app_logger.warning(
                    "Power Save Mode toggle skipped: QZSS DCR disable failed"
                )
                return

        self.gps_ublox["POWER_SAVE"] = enabled
        self.update_toggles()
        if not await self.sensor_gps.set_power_save_enabled(enabled):
            self.gps_ublox["POWER_SAVE"] = not enabled
            if enabled and previous_qzss_dcr:
                if not await self._set_qzss_dcr(True):
                    self.config.setting.write_config()
            self.update_toggles()
            power_save_status = self.sensor_gps.power_save_status
            app_logger.warning(
                "Power Save Mode toggle skipped: "
                f"{power_save_status['status']} {power_save_status['error']}"
            )
            return
        self.config.setting.write_config()
        self.update_toggles()

    def onoff_assistnow(self):
        if self._settings_changing or self.sensor_gps.qzss_dcr_changing:
            return
        assistnow = self.gps_ublox["ASSISTNOW"]
        enabled = not bool(assistnow["STATUS"])
        self.sensor_gps.set_assistnow_enabled(enabled)
        self.config.setting.write_config()
        self.update_toggles()

    def update_toggles(self):
        changing = self._settings_changing or self.sensor_gps.qzss_dcr_changing
        self.buttons[self.ASSISTNOW_BUTTON].onoff_button(not changing)
        self.buttons[self.POWER_SAVE_BUTTON].onoff_button(not changing)
        assistnow_enabled = bool(self.gps_ublox["ASSISTNOW"]["STATUS"])
        self.buttons[self.ASSISTNOW_BUTTON].change_toggle(assistnow_enabled)

        power_save_enabled = bool(self.gps_ublox["POWER_SAVE"])
        self.buttons[self.POWER_SAVE_BUTTON].change_toggle(power_save_enabled)

        self.buttons[self.QZSS_DCR_BUTTON].onoff_button(
            not power_save_enabled and not changing
        )
        self.buttons[self.QZSS_DCR_BUTTON].change_toggle(
            False if power_save_enabled else bool(self.config.G_GPS_QZSS_DCR["STATUS"])
        )
