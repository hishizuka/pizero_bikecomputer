from logger import app_logger
from modules._qt_qtwidgets import QtCore, QtWidgets, QtGui
from .pyqt_menu_widget import MenuWidget, ListWidget, ListItemWidget


class SensorMenuWidget(MenuWidget):

    def setup_menu(self):
        button_conf = (
            # Name(page_name), button_attribute, connected functions, layout
            ("ANT+ Sensors", "submenu", self.ant_sensors_menu),
            ("Wheel Size", "submenu", self.adjust_wheel_circumference),
            ("Auto Light", "toggle", lambda: self.onoff_auto_light(True)),
            ("Auto Stop", None, None),
            ("Gross Ave Speed", None, None),
            ("Adjust Altitude", "submenu", self.adjust_altitude),
        )
        self.add_buttons(button_conf)
        self.onoff_auto_light(False)
    
    def preprocess(self):
        self.buttons["Auto Light"].onoff_button(self.config.G_ANT["USE"]["LGT"])

    def ant_sensors_menu(self):
        if self.sensor_ant.scanner.isUse:
            # output message dialog "cannot go in multiscan mode"
            return
        self.change_page("ANT+ Sensors")

    def adjust_wheel_circumference(self):
        self.change_page("Wheel Size", preprocess=True)

    def adjust_altitude(self):
        self.change_page("Adjust Altitude")

    def onoff_auto_light(self, change=True):
        if change:
            self.config.G_ANT["USE_AUTO_LIGHT"] = not self.config.G_ANT["USE_AUTO_LIGHT"] 
        self.buttons["Auto Light"].change_toggle(self.config.G_ANT["USE_AUTO_LIGHT"])

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

        if not self.config.display.has_touch:
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
        index = self.config.gui.gui_config.G_GUI_INDEX[self.back_index_key]
        self.parentWidget().widget(index).update_button_label()

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
