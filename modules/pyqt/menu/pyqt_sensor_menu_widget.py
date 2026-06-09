from modules.app_logger import app_logger
from modules._qt_qtwidgets import QtCore, QtWidgets, QtGui, qasync
from .pyqt_menu_widget import MenuWidget, ListWidget, ListItemWidget


class SensorMenuWidget(MenuWidget):

    def setup_menu(self):
        button_conf = (
            # Name(page_name), button_attribute, connected functions, layout
            ("ANT+ Sensors", "submenu", self.ant_sensors_menu),
            ("BLE Sensors", "submenu", self.ble_sensors_menu),
            ("GPS", "submenu", self.gps_menu),
            ("Wheel Size", "submenu", self.adjust_wheel_circumference),
            ("Auto Stop", None, None),
            ("Gross Ave Speed", None, None),
            ("I2C Sensors", "submenu", self.i2c_sensors_menu),
        )
        self.add_buttons(button_conf)
        self.buttons["GPS"].onoff_button(self.sensor_gps.__class__.__name__ == "UBlox")

    def preprocess(self):
        pass

    def ant_sensors_menu(self):
        if self.sensor_ant.scanner.isUse:
            # output message dialog "cannot go in multiscan mode"
            return
        self.change_page("ANT+ Sensors")

    def ble_sensors_menu(self):
        self.change_page("BLE Sensors", preprocess=True)

    def gps_menu(self):
        self.change_page("GPS", preprocess=True)

    def adjust_wheel_circumference(self):
        self.change_page("Wheel Size", preprocess=True)

    def i2c_sensors_menu(self):
        self.change_page("I2C Sensors", preprocess=True)


class I2CMenuWidget(MenuWidget):
    MAG_CALIBRATION_BUTTON = "Mag Calibration"
    PITCH_ROLL_CALIBRATION_BUTTON = "Pitch/Roll Calibration"

    def setup_menu(self):
        button_conf = (
            # Name(page_name), button_attribute, connected functions, layout
            ("Auto Light", "toggle", lambda: self.onoff_auto_light(True)),
            ("Adjust Altitude", "submenu", self.adjust_altitude),
            (self.MAG_CALIBRATION_BUTTON, "toggle", self.calib_mag),
            (self.PITCH_ROLL_CALIBRATION_BUTTON, "toggle", self.calib_pitch_roll),
        )
        self.add_buttons(button_conf)
        self.update_button_status()

    def preprocess(self):
        self.update_button_status()

    def adjust_altitude(self):
        self.change_page("Adjust Altitude")

    def onoff_auto_light(self, change=True):
        if change:
            self.config.G_ANT["USE_AUTO_LIGHT"] = not self.config.G_ANT["USE_AUTO_LIGHT"]
        self.buttons["Auto Light"].change_toggle(self.config.G_ANT["USE_AUTO_LIGHT"])

    def calib_mag(self):
        self.config.gui.calib_mag()
        self.update_button_status()

    def calib_pitch_roll(self):
        self.config.gui.calib_pitch_roll()
        self.update_button_status()

    def update_button_status(self):
        self.buttons["Auto Light"].onoff_button(self.config.G_ANT["USE"]["LGT"])
        self.buttons["Auto Light"].change_toggle(self.config.G_ANT["USE_AUTO_LIGHT"])
        self.buttons[self.MAG_CALIBRATION_BUTTON].change_toggle(
            self.sensor_i2c.do_mag_calibration
        )
        self.buttons[self.PITCH_ROLL_CALIBRATION_BUTTON].change_toggle(
            self.sensor_i2c.do_pitch_roll_calibration
        )


class GPSMenuWidget(MenuWidget):
    ASSISTNOW_BUTTON = "AssistNow (u-blox)"
    POWER_SAVE_BUTTON = "Power Save Mode (u-blox)"
    QZSS_DCR_BUTTON = "QZSS DCR (u-blox)"

    def setup_menu(self):
        self.gps_ublox = self.config.G_GPS_UBLOX
        button_conf = (
            # Name(page_name), button_attribute, connected functions, layout
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


class ANTMenuWidget(MenuWidget):
    def setup_menu(self):
        button_conf = []

        for antName in self.config.G_ANT["ORDER"]:
            # Name(page_name), button_attribute, connected functions, layout
            button_conf.append(
                (antName, "submenu", eval("self.setting_ant_" + antName))
            )
        self.add_buttons(button_conf)

        # modify label from antName to self.get_button_state()
        for antName in self.config.G_ANT["ORDER"]:
            self.buttons[antName].setText(self.get_button_state(antName))

        if self.config.uses_keyboard_navigation:
            self.focus_widget = self.buttons[self.config.G_ANT["ORDER"][0]]

    def get_button_state(self, antName):
        status = "OFF"
        if antName in self.config.G_ANT["USE"] and self.config.G_ANT["USE"][antName]:
            status = "{0:05d}".format(self.config.G_ANT["ID"][antName])
        return self.config.G_ANT["NAME"][antName] + ": " + status

    def setting_ant_HR(self):
        self.setting_ant("HR")

    def setting_ant_SPD(self):
        self.setting_ant("SPD")

    def setting_ant_CDC(self):
        self.setting_ant("CDC")

    def setting_ant_PWR(self):
        self.setting_ant("PWR")

    def setting_ant_LGT(self):
        self.setting_ant("LGT")

    def setting_ant_CTRL(self):
        self.setting_ant("CTRL")

    def setting_ant_TEMP(self):
        self.setting_ant("TEMP")

    def setting_ant(self, ant_name):
        if self.config.G_ANT["USE"][ant_name]:
            # disable ANT+ sensor
            self.sensor_ant.disconnect_ant_sensor(ant_name)
            self.config.setting.write_config()
        else:
            # search ANT+ sensor
            self.change_page(
                "ANT+ Detail", preprocess=True, reset=True, list_type=ant_name
            )

        self.update_button_label()

    def update_button_label(self):
        for ant_name in self.buttons.keys():
            self.buttons[ant_name].setText(self.get_button_state(ant_name))


class ANTListWidget(ListWidget):
    ant_sensor_types = None

    def __init__(self, parent, page_name, config):
        self.ant_sensor_types = {}
        super().__init__(parent, page_name, config)

    def setup_menu(self):
        super().setup_menu()
        # update panel for every 1 seconds
        self.timer = QtCore.QTimer(parent=self)
        self.timer.timeout.connect(self.update_display)

    async def button_func_extra(self):
        if self.selected_item is None:
            return

        app_logger.info(f"connect {self.list_type}: {self.selected_item.id}")

        ant_id = int(self.selected_item.id)
        self.sensor_ant.connect_ant_sensor(
            self.list_type,  # sensor type
            ant_id,  # ID
            self.ant_sensor_types[ant_id][0],  # id_type
            self.ant_sensor_types[ant_id][1],  # connection status
        )
        self.config.setting.write_config()

    def on_back_menu(self):
        self.timer.stop()
        self.sensor_ant.searcher.stop_search()
      	# button update
        back_index_key = self.back_index_key
        gui_index = self.config.gui.gui_config.G_GUI_INDEX
        if back_index_key in gui_index:
            index = gui_index[back_index_key]
            self.parentWidget().widget(index).update_button_label()
        else:
            app_logger.warning(
                f"on_back_menu skipped update: back_index_key {back_index_key} missing in G_GUI_INDEX"
            )
            app_logger.warning(f"{gui_index}")

    def preprocess_extra(self):
        self.ant_sensor_types.clear()
        self.sensor_ant.searcher.search(self.list_type)
        self.timer.start(self.config.G_DRAW_INTERVAL)

    def update_display(self):
        detected_sensors = self.sensor_ant.searcher.getSearchList()

        for ant_id, ant_type_array in detected_sensors.items():
            ant_id_str = f"{ant_id:05d}"
            add = ant_id not in self.ant_sensor_types
            if add:
                self.ant_sensor_types[ant_id] = ant_type_array
                status = ant_type_array[1]
                status_str = " (connected)" if status else ""
                sensor_type = self.config.G_ANT["TYPE_NAME"][ant_type_array[0]]
                title = f"{sensor_type} {status_str}".strip()
                ant_item = ANTListItemWidget(self, ant_id_str, title)

                self.add_list_item(ant_item)

                app_logger.debug(f"Adding ANT+ sensor: {title}")


class ANTListItemWidget(ListItemWidget):
    id = None

    def __init__(self, parent, ant_id, title):
        self.id = ant_id
        super().__init__(parent, title, detail=f"   ID: {ant_id}")

    def setup_ui(self):
        super().setup_ui()
        dummy_px = QtGui.QPixmap(20, 20)
        dummy_px.fill(QtGui.QColor("#008000"))
        icon = QtWidgets.QLabel()
        icon.setPixmap(dummy_px)
        icon.setContentsMargins(5, 0, 10, 0)

        # outer layout (custom)
        self.outer_layout.insertWidget(0, icon)
        self.enter_signal.connect(self.parentWidget().button_func)


class BLEMenuWidget(MenuWidget):
    def setup_menu(self):
        button_conf = (
            # Name(page_name), button_attribute, connected functions, layout
            ("Zwift Click V2", "toggle", lambda: self.onoff_zwift_click_v2(True)),
            ("Fake Trainer for Zwift", "toggle", lambda: self.onoff_fake_trainer(True)),
        )
        self.add_buttons(button_conf)
        self.onoff_zwift_click_v2(False)

        #if self.config.logger.sensor.sensor_ble.enabled():
        #    self.buttons["Zwift Click V2"].disable()

        if self.config.ble_uart is None:
            self.buttons["Fake Trainer for Zwift"].disable()

    def preprocess(self):
        self.onoff_zwift_click_v2(False)
        self.onoff_fake_trainer(False)

    def onoff_zwift_click_v2(self, change=True):
        if change:
            self.config.G_ZWIFT_CLICK_V2["STATUS"] = not self.config.G_ZWIFT_CLICK_V2["STATUS"]
            sensor_ble = self.config.logger.sensor.sensor_ble
            if self.config.G_ZWIFT_CLICK_V2["STATUS"]:
                if not sensor_ble.connect_zwift_click_v2():
                    app_logger.warning("Zwift Click V2 toggle skipped: BLE not enabled")
            else:
                sensor_ble.disconnect_zwift_click_v2()
        self.buttons["Zwift Click V2"].change_toggle(self.config.G_ZWIFT_CLICK_V2["STATUS"])
    
    def onoff_fake_trainer(self, change=True):
        sensor_ble = self.config.logger.sensor.sensor_ble
        if change:
            sensor_ble.toggle_fake_trainer()

        fake_trainer_status = sensor_ble.is_fake_trainer_running()
        self.buttons["Fake Trainer for Zwift"].change_toggle(fake_trainer_status)

        if change:
            if fake_trainer_status:
                self.buttons["Zwift Click V2"].disable()
                self.buttons["Zwift Click V2"].change_toggle(False)
            else:
                self.buttons["Zwift Click V2"].enable()
                self.buttons["Zwift Click V2"].change_toggle(True)
