import copy

class Button_Config:
    config = None

    # long press threshold of buttons [sec]
    G_BUTTON_LONG_PRESS = 1

    G_BUTTON_DEF = {
        # call from ButtonShim
        "Button_Shim": {
            "MAIN": {
                "A": ("scroll_prev", ""),
                "B": ("count_laps", "reset_count"),
                "C": ("get_screenshot", ""),
                #"C": ("multiscan", ""),
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
                "A": ("scroll_prev", ""),
                "B": ("map_zoom_minus", ""),
                "C": ("change_map_overlays", "change_mode"),
                "D": ("map_zoom_plus", ""),
                "E": ("scroll_next", "enter_menu"),
            },
            "MAP_1": {
                "A": ("map_move_x_minus", ""),
                "B": ("map_move_y_minus", "map_zoom_minus"),
                "C": ("change_map_overlays", "change_mode"),
                "D": ("map_move_y_plus", "map_zoom_plus"),
                "E": ("map_move_x_plus", "map_search_route"),
            },
            #"MAP_2": {
            #    "A": ("timeline_past", ""),
            #    "B": ("map_zoom_minus", ""),
            #    "C": ("timeline_reset", "change_mode"),
            #    "D": ("map_zoom_plus", ""),
            #    "E": ("timeline_future", ""),
            #},
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
        # call from sensor_ant
        "Edge_Remote": {
            "MAIN": {
                "PAGE": ("scroll_prev", "scroll_next"),
                "CUSTOM": ("change_mode", "enter_menu"),
                #"CUSTOM": ("get_screenshot", "enter_menu"),
                #"CUSTOM": ("get_screenshot", "turn_on_off_light"),
                "LAP": ("count_laps",),
            },
            "MAIN_1": {
                "PAGE": ("turn_on_off_light", "brightness_control"),
                "CUSTOM": ("change_mode", ""),
                "LAP": ("start_and_stop_manual",),
            },
            "MENU": {
                "PAGE": ("press_tab", ""),
                "CUSTOM": ("press_shift_tab", "back_menu"),
                "LAP": ("press_space",),
            },
            "MAP": {
                "PAGE": ("scroll_prev", "scroll_next"),
                "CUSTOM": ("change_mode", "map_zoom_minus"),
                #"CUSTOM": ("get_screenshot", "map_zoom_minus"),
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
            if (
                self.config.gui.main_page.widget(
                    self.config.gui.main_page.currentIndex()
                )
                == self.config.gui.map_widget
            ):
                if not self.G_BUTTON_MODE_IS_CHANGE:
                    self.G_PAGE_MODE = "MAP"
            elif (
                self.config.gui.main_page.widget(
                    self.config.gui.main_page.currentIndex()
                )
                == self.config.gui.course_profile_graph_widget
            ):
                if not self.G_BUTTON_MODE_IS_CHANGE:
                    self.G_PAGE_MODE = "COURSE_PROFILE"
            else:
                if not self.G_BUTTON_MODE_IS_CHANGE:
                    self.G_PAGE_MODE = "MAIN"
            # for no implementation
            if self.G_PAGE_MODE not in self.G_BUTTON_DEF[button_hard]:
                self.G_PAGE_MODE = "MAIN"
        elif w_index >= 2:
            self.G_PAGE_MODE = "MENU"

        func_str = self.G_BUTTON_DEF[button_hard][self.G_PAGE_MODE][press_button][index]
        if func_str in ("", "dummy"):
            return
        
        func = eval("self.config.gui." + func_str)
        func()

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
