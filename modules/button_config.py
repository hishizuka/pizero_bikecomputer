import copy

from modules.app_logger import app_logger


class Button_Config:
    config = None

    # long press threshold of buttons [sec]
    G_BUTTON_LONG_PRESS = 1

    G_BUTTON_DEF = {
        # call from ButtonShim
        "Button_Shim": {
            "MAIN": {
                "A": ("scroll_prev", "get_screenshot"),
                "B": ("count_laps", "reset_count"),
                "C": ("multiscan", ""),
                "D": ("start_and_stop_manual", ""),
                "E": ("scroll_next", "enter_menu"),
            },
            "MENU": {
                "A": ("back_menu", ""),
                "B": ("brightness_control", ""),
                "C": ("press_space", ""),
                "D": ("press_shift_tab", ""),
                "E": ("press_tab", ""),
            },
            "MAP": {
                "A": ("scroll_prev", "get_screenshot"),
                "B": ("map_zoom_minus", "map_overlay_prev_time"),
                "C": ("change_map_overlays", "change_mode"),
                "D": ("map_zoom_plus", "map_overlay_next_time"),
                "E": ("scroll_next", "modify_map_tile"),
            },
            "MAP_1": {
                "A": ("map_move_x_minus", "get_screenshot"),
                "B": ("map_move_y_minus", "map_zoom_minus"),
                "C": ("change_map_overlays", "change_mode"),
                "D": ("map_move_y_plus", "map_zoom_plus"),
                "E": ("map_move_x_plus", "map_search_route"),
                # todo: move_past, move_future
            },
            "COURSE_PROFILE": {
                "A": ("scroll_prev", ""),
                "B": ("map_zoom_minus", ""),
                "C": ("change_mode", ""),
                "D": ("map_zoom_plus", ""),
                "E": ("scroll_next", "enter_menu"),
            },
            "COURSE_PROFILE_1": {
                "A": ("map_move_x_minus", ""),
                "B": ("map_zoom_minus", ""),
                "C": ("change_mode", ""),
                "D": ("map_zoom_plus", ""),
                "E": ("map_move_x_plus", ""),
            },
        },
        # copy from Button_Shim: see ioexpander_change_keys
        "IOExpander": {},
        # call from sensor_ant
        "Edge_Remote": {
            "MAIN": {
                "PAGE": ("scroll_prev", "scroll_next"),
                "CUSTOM": ("turn_on_off_light", "enter_menu"),
                "LAP": ("count_laps",),
            },
            #"MAIN_1": {
            #    "PAGE": ("turn_on_off_light", "brightness_control"),
            #    "CUSTOM": ("change_mode", ""),
            #    "LAP": ("start_and_stop_manual",),
            #},
            "MENU": {
                "PAGE": ("press_tab", ""),
                "CUSTOM": ("press_shift_tab", "back_menu"),
                "LAP": ("press_space",),
            },
            "MAP": {
                "PAGE": ("scroll_prev", "scroll_next"),
                "CUSTOM": ("change_mode", "map_zoom_minus"),
                "LAP": ("map_zoom_plus",),
            },
            "MAP_1": {
                "PAGE": ("", ""),  # go along the route / back along the route
                "CUSTOM": ("change_mode", "map_zoom_minus"),
                "LAP": ("map_zoom_plus",),
            },
            "COURSE_PROFILE": {
                "PAGE": ("scroll_prev", "scroll_next"),
                "CUSTOM": ("change_mode", "map_zoom_minus"),
                "LAP": ("map_zoom_plus",),
            },
            "COURSE_PROFILE_1": {
                "PAGE": ("", ""),  # go along the route / back along the route
                "CUSTOM": ("change_mode", "map_move_x_minus"),
                "LAP": ("map_move_x_plus",),
            },
        },
        # Zwift Click V2 (BLE)
        "Zwift_Click_V2": {
            "MAIN": {
                "NAVIGATION_UP": ("", ""),
                "NAVIGATION_DOWN": ("", ""),
                "NAVIGATION_LEFT": ("scroll_prev", ""),
                "NAVIGATION_RIGHT": ("scroll_next", ""),
                "SHIFT_UP_LEFT": ("", ""),
                "SHIFT_UP_RIGHT": ("", ""),
                "A": ("start_and_stop_manual", ""),
                "B": ("count_laps", "reset_count"),
                "Y": ("enter_menu", ""),
                "Z": ("turn_on_off_light", ""),
            },
            "MENU": {
                "NAVIGATION_UP": ("press_shift_tab", ""),
                "NAVIGATION_DOWN": ("press_tab", ""),
                "NAVIGATION_LEFT": ("back_menu", ""),
                "NAVIGATION_RIGHT": ("press_space", ""),
                "SHIFT_UP_LEFT": ("", ""),
                "SHIFT_UP_RIGHT": ("", ""),
                "A": ("press_space", ""),
                "B": ("back_menu", ""),
                "Y": ("", ""),
                "Z": ("", ""),
            },
            "MAP": {
                "NAVIGATION_UP": ("", ""),
                "NAVIGATION_DOWN": ("", ""),
                "NAVIGATION_LEFT": ("scroll_prev", "map_overlay_prev_time"),
                "NAVIGATION_RIGHT": ("scroll_next", "map_overlay_next_time"),
                "SHIFT_UP_LEFT": ("map_zoom_minus", ""),
                "SHIFT_UP_RIGHT": ("map_zoom_plus", ""),
                "A": ("start_and_stop_manual", ""),
                "B": ("count_laps", "reset_count"),
                "Y": ("change_mode", ""),
                "Z": ("change_map_overlays", ""),
            },
            "MAP_1": {
                "NAVIGATION_UP": ("map_move_y_plus", ""),
                "NAVIGATION_DOWN": ("map_move_y_minus", ""),
                "NAVIGATION_LEFT": ("map_move_x_minus", "map_overlay_prev_time"),
                "NAVIGATION_RIGHT": ("map_move_x_plus", "map_overlay_next_time"),
                "SHIFT_UP_LEFT": ("map_zoom_minus", ""),
                "SHIFT_UP_RIGHT": ("map_zoom_plus", ""),
                "A": ("start_and_stop_manual", ""),
                "B": ("count_laps", "reset_count"),
                "Y": ("change_mode", ""),
                "Z": ("change_map_overlays", ""),
            },
            "COURSE_PROFILE": {
                "NAVIGATION_UP": ("", ""),
                "NAVIGATION_DOWN": ("", ""),
                "NAVIGATION_LEFT": ("scroll_prev", ""),
                "NAVIGATION_RIGHT": ("scroll_next", ""),
                "SHIFT_UP_LEFT": ("map_zoom_minus", ""),
                "SHIFT_UP_RIGHT": ("map_zoom_plus", ""),
                "A": ("start_and_stop_manual", ""),
                "B": ("count_laps", "reset_count"),
                "Y": ("change_mode", ""),
                "Z": ("", ""),
            },
            "COURSE_PROFILE_1": {
                "NAVIGATION_UP": ("", ""),
                "NAVIGATION_DOWN": ("", ""),
                "NAVIGATION_LEFT": ("map_move_x_minus", ""),
                "NAVIGATION_RIGHT": ("map_move_x_plus", ""),
                "SHIFT_UP_LEFT": ("map_zoom_minus", ""),
                "SHIFT_UP_RIGHT": ("map_zoom_plus", ""),
                "A": ("start_and_stop_manual", ""),
                "B": ("count_laps", "reset_count"),
                "Y": ("change_mode", ""),
                "Z": ("", ""),
            },
        },
        # GPIO button action (short press / long press) from gui_pyqt
        # call from SensorGPIO.my_callback(self, channel)
        # number is from GPIO.setmode(GPIO.BCM)
        "PiTFT": {
            "MAIN": {
                5: ("scroll_prev", ""),
                6: ("count_laps", "reset_count"),
                12: ("brightness_control", ""),
                13: ("start_and_stop_manual", ""),
                16: ("scroll_next", "enter_menu"),
            },
            "MENU": {
                5: ("back_menu", ""),
                6: ("", ""),
                12: ("press_space", ""),
                13: ("press_shift_tab", ""),
                16: ("press_tab", ""),
            },
        },
        "Papirus": {
            "MAIN": {
                16: ("scroll_prev", ""),            # SW1(left)
                26: ("count_laps", "reset_count"),  # SW2
                20: ("start_and_stop_manual", ""),  # SW3
                21: ("scroll_next", "enter_menu"),  # SW4
            },
            "MENU": {
                16: ("back_menu", ""),
                26: ("press_space", ""),
                20: ("press_shift_tab", ""),
                21: ("press_tab", ""),
            },
        },
        "DFRobot_RPi_Display": {
            "MAIN": {
                21: ("start_and_stop_manual", "reset_count"),
                20: ("scroll_next", "enter_menu"),
            },
            "MENU": {
                21: ("press_space", ""),
                20: ("press_tab", "back_menu"),
            },
        },
        "Pirate_Audio": {
            "MAIN": {
                5: ("scroll_prev", "change_mode"),  # A
                6: ("count_laps", "reset_count"),   # B
                16: ("scroll_next", "enter_menu"),  # X
                24: ("start_and_stop_manual", ""),  # Y
            },
            "MAIN_1": {
                5: ("scroll_prev", "change_mode"),
                6: ("count_laps", ""),
                16: ("scroll_next", "enter_menu"),
                24: ("brightness_control", ""),
            },
            "MENU": {
                5: ("press_shift_tab", ""),
                6: ("back_menu", ""),
                16: ("press_tab", ""),
                24: ("press_space", ""),
            },
            "MAP": {
                5: ("scroll_prev", ""),
                6: ("map_zoom_minus", ""),
                16: ("scroll_next", "enter_menu"),
                24: ("map_zoom_plus", "change_map_overlays"),
            },
            "COURSE_PROFILE": {
                5: ("scroll_prev", ""),
                6: ("map_zoom_minus", ""),
                16: ("scroll_next", "enter_menu"),
                24: ("map_zoom_plus", ""),
            },
        },
        "Pirate_Audio_old": {},
        "Display_HAT_Mini": {},
    }
    # copy button definition
    G_BUTTON_DEF["IOExpander"] = copy.deepcopy(G_BUTTON_DEF["Button_Shim"])
    # change button keys
    ioexpander_change_keys = {
        "A": "GP0", "B": "GP1", "C": "GP2", "D": "GP3", "E": "GP4",
        #"A": "GP1", "B": "GP2", "C": "GP3", "D": "GP4", "E": "GP6",
    }
    for k1 in G_BUTTON_DEF["IOExpander"]:
        b = G_BUTTON_DEF["IOExpander"][k1]
        for k2 in ioexpander_change_keys:
            b[ioexpander_change_keys[k2]] = b.pop(k2)
            
    G_BUTTON_DEF["Display_HAT_Mini"] = copy.deepcopy(G_BUTTON_DEF["Pirate_Audio"])
    G_BUTTON_DEF["Pirate_Audio_old"] = copy.deepcopy(G_BUTTON_DEF["Pirate_Audio"])
    for k in G_BUTTON_DEF["Pirate_Audio_old"]:
        # Y key is GPIO 20, not 24
        G_BUTTON_DEF["Pirate_Audio_old"][k][20] = G_BUTTON_DEF["Pirate_Audio_old"][k].pop(24)

    G_PAGE_MODE = "MAIN"

    # mode group setting changed by change_mode
    G_BUTTON_MODE_IS_CHANGE = False
    G_BUTTON_MODE_PAGES = {
        "MAIN": ["MAIN", "MAIN_1"],
        # 'MAP': ['MAP','MAP_1','MAP_2'],
        "MAP": ["MAP", "MAP_1"],
        "COURSE_PROFILE": ["COURSE_PROFILE", "COURSE_PROFILE_1"],
    }
    G_BUTTON_MODE_INDEX = {
        "MAIN": 0,
        "MAP": 0,
        "COURSE_PROFILE": 0,
    }

    def __init__(self, config):
        self.config = config

    def press_button(self, button_hard, press_button, index):
        if self.config.gui is None or self.config.gui.stack_widget is None:
            return

        w_index = self.config.gui.stack_widget.currentIndex()
        if w_index == 1:
            current_widget = self.config.gui.main_page.widget(
                self.config.gui.main_page.currentIndex()
            )
            if current_widget == self.config.gui.map_widget:
                mode_key = "MAP"
            elif current_widget == self.config.gui.course_profile_graph_widget:
                mode_key = "COURSE_PROFILE"
            else:
                mode_key = "MAIN"

            pages = self.G_BUTTON_MODE_PAGES.get(mode_key)
            if pages:
                mode_index = self.G_BUTTON_MODE_INDEX.get(mode_key, 0)
                if mode_index < 0 or mode_index >= len(pages):
                    mode_index = 0
                self.G_PAGE_MODE = pages[mode_index]
            else:
                self.G_PAGE_MODE = mode_key
            # for no implementation
            if self.G_PAGE_MODE not in self.G_BUTTON_DEF[button_hard]:
                self.G_PAGE_MODE = "MAIN"
        elif w_index >= 2:
            self.G_PAGE_MODE = "MENU"

        if press_button not in self.G_BUTTON_DEF[button_hard][self.G_PAGE_MODE]:
            app_logger.warning(
                f"buton key error: '{press_button}' is not defined in self.G_BUTTON_DEF['{button_hard}']['{self.G_PAGE_MODE}']"
            )
            return
        func_str = self.G_BUTTON_DEF[button_hard][self.G_PAGE_MODE][press_button][index]
        if func_str in ("", "dummy"):
            return
        
        getattr(self.config.gui, func_str)()

    def change_mode(self):
        # check MAP
        w = self.config.gui.main_page.widget(self.config.gui.main_page.currentIndex())

        if "MAIN" in self.G_PAGE_MODE:
            self.change_mode_index("MAIN")
        # if display is MAP: change MAP_1 -> MAP_2 -> MAP -> ...
        elif w == self.config.gui.map_widget:
            self.change_mode_index("MAP")
            # additional: lock current position when normal page
            if not self.G_BUTTON_MODE_IS_CHANGE:
                w.lock_on()
            else:
                w.lock_off()
        elif w == self.config.gui.course_profile_graph_widget:
            self.change_mode_index("COURSE_PROFILE")
            # additional: lock current position when normal page
            if not self.G_BUTTON_MODE_IS_CHANGE:
                w.lock_on()
            else:
                w.lock_off()

    def change_mode_index(self, mode):
        self.G_BUTTON_MODE_INDEX[mode] = self.G_BUTTON_MODE_INDEX[mode] + 1
        self.G_BUTTON_MODE_IS_CHANGE = True
        if self.G_BUTTON_MODE_INDEX[mode] >= len(self.G_BUTTON_MODE_PAGES[mode]):
            self.G_BUTTON_MODE_INDEX[mode] = 0
            self.G_BUTTON_MODE_IS_CHANGE = False
        self.G_PAGE_MODE = self.G_BUTTON_MODE_PAGES[mode][
            self.G_BUTTON_MODE_INDEX[mode]
        ]
