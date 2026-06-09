import copy

from modules.app_logger import app_logger


def _button_key_map(*button_names):
    return {button_name: button_name for button_name in button_names}


def _expand_button_template(button_template, button_map, pages=None):
    button_def = {}
    page_names = pages if pages is not None else button_template.keys()
    for page_name in page_names:
        if page_name not in button_template:
            continue
        button_def[page_name] = {
            button_map[button_name]: copy.deepcopy(actions)
            for button_name, actions in button_template[page_name].items()
            if button_name in button_map
        }
    return button_def


def _build_button_profiles(button_templates, profile_defs):
    button_profiles = {}
    for profile_name, profile_def in profile_defs.items():
        button_profile = _expand_button_template(
            button_templates[profile_def["TEMPLATE"]],
            profile_def["BUTTONS"],
            profile_def.get("PAGES"),
        )
        for page_name, page_buttons in profile_def.get("OVERRIDES", {}).items():
            if page_name not in button_profile:
                button_profile[page_name] = {}
            button_profile[page_name].update(copy.deepcopy(page_buttons))
        button_profiles[profile_name] = button_profile
    return button_profiles


class Button_Config:
    config = None

    # long press threshold of buttons [sec]
    button_long_press = 1

    button_templates = {
        "5_BUTTON": {
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
        "4_BUTTON": {
            "MAIN": {
                "A": ("scroll_prev", "change_mode"),
                "B": ("count_laps", "reset_count"),
                "C": ("scroll_next", "enter_menu"),
                "D": ("start_and_stop_manual", ""),
            },
            "MAIN_1": {
                "A": ("scroll_prev", "change_mode"),
                "B": ("count_laps", ""),
                "C": ("scroll_next", "enter_menu"),
                "D": ("brightness_control", ""),
            },
            "MENU": {
                "A": ("press_shift_tab", ""),
                "B": ("back_menu", ""),
                "C": ("press_tab", ""),
                "D": ("press_space", ""),
            },
            "MAP": {
                "A": ("scroll_prev", ""),
                "B": ("map_zoom_minus", ""),
                "C": ("scroll_next", "enter_menu"),
                "D": ("map_zoom_plus", "change_map_overlays"),
            },
            "COURSE_PROFILE": {
                "A": ("scroll_prev", ""),
                "B": ("map_zoom_minus", ""),
                "C": ("scroll_next", "enter_menu"),
                "D": ("map_zoom_plus", ""),
            },
        },
        "3_BUTTON": {
            "MAIN": {
                "A": ("scroll_prev", "get_screenshot"),
                "B": ("start_and_stop_manual", "count_laps"),
                "C": ("scroll_next", "enter_menu"),
            },
            "MENU": {
                "A": ("back_menu", ""),
                "B": ("press_space", ""),
                "C": ("press_tab", ""),
            },
            "MAP": {
                "A": ("map_zoom_minus", "map_overlay_prev_time"),
                "B": ("change_map_overlays", "change_mode"),
                "C": ("map_zoom_plus", "map_overlay_next_time"),
            },
            "MAP_1": {
                "A": ("map_move_x_minus", "map_zoom_minus"),
                "B": ("change_map_overlays", "change_mode"),
                "C": ("map_move_x_plus", "map_zoom_plus"),
            },
            "COURSE_PROFILE": {
                "A": ("map_zoom_minus", ""),
                "B": ("change_mode", ""),
                "C": ("map_zoom_plus", ""),
            },
            "COURSE_PROFILE_1": {
                "A": ("map_move_x_minus", ""),
                "B": ("change_mode", ""),
                "C": ("map_move_x_plus", ""),
            },
        },
        "2_BUTTON": {
            "MAIN": {
                "A": ("start_and_stop_manual", "reset_count"),
                "B": ("scroll_next", "enter_menu"),
            },
            "MENU": {
                "A": ("press_space", ""),
                "B": ("press_tab", "back_menu"),
            },
        },
    }

    # BCM GPIO pin assignment by display profile.
    gpio_buttons = {
        "PiTFT": {"A": 5, "B": 6, "C": 12, "D": 13, "E": 16},
        "Papirus": {"A": 16, "B": 26, "C": 21, "D": 20},
        "DFRobot_RPi_Display": {"A": 21, "B": 20},
        # Pirate Audio C/D are X/Y buttons.
        "Pirate_Audio": {"A": 5, "B": 6, "C": 16, "D": 24},
        "Pirate_Audio_old": {"A": 5, "B": 6, "C": 16, "D": 20},
        "Display_HAT_Mini": {"A": 5, "B": 6, "C": 16, "D": 24},
    }

    # Select one of 5_BUTTON, 4_BUTTON, 3_BUTTON, or 2_BUTTON.
    custom_gpio_button_template = "5_BUTTON"

    # Enable custom direct GPIO buttons defined below.
    use_custom_gpio_buttons = False

    # BCM GPIO pin assignment for Custom_GPIO.
    # Remove entries to use fewer physical buttons.
    custom_gpio_buttons = {
        "A": 4,
        "B": 27,
        "C": 5,
        "D": 6,
        "E": 26,
    }

    button_profile_defs = {
        "Button_Shim": {
            "TEMPLATE": "5_BUTTON",
            "BUTTONS": _button_key_map("A", "B", "C", "D", "E"),
        },
        "IOExpander": {
            "TEMPLATE": "5_BUTTON",
            "BUTTONS": {
                "A": "GP0",
                "B": "GP1",
                "C": "GP2",
                "D": "GP3",
                "E": "GP4",
            },
        },
        "Custom_GPIO": {
            "TEMPLATE": custom_gpio_button_template,
            "BUTTONS": _button_key_map(*custom_gpio_buttons.keys()),
        },
        "PiTFT": {
            "TEMPLATE": "5_BUTTON",
            "BUTTONS": gpio_buttons["PiTFT"],
            "PAGES": ("MAIN", "MENU"),
            "OVERRIDES": {
                "MAIN": {
                    #5: ("", ""),
                    #6: ("", ""),
                    12: ("brightness_control", ""),
                    #13: ("", ""),
                    #16: ("", ""),
                },
            },
        },
        "Papirus": {
            "TEMPLATE": "4_BUTTON",
            "BUTTONS": gpio_buttons["Papirus"],
            "PAGES": ("MAIN", "MENU"),
            "OVERRIDES": {
                "MAIN": {
                    #16: ("", ""),  # SW1(left)
                    #26: ("", ""),  # SW2
                    #20: ("", ""),  # SW3
                    #21: ("", ""),  # SW4
                },
            },
        },
        "DFRobot_RPi_Display": {
            "TEMPLATE": "2_BUTTON",
            "BUTTONS": gpio_buttons["DFRobot_RPi_Display"],
        },
        "Pirate_Audio": {
            "TEMPLATE": "4_BUTTON",
            "BUTTONS": gpio_buttons["Pirate_Audio"],
        },
        "Pirate_Audio_old": {
            "TEMPLATE": "4_BUTTON",
            "BUTTONS": gpio_buttons["Pirate_Audio_old"],
        },
        "Display_HAT_Mini": {
            "TEMPLATE": "4_BUTTON",
            "BUTTONS": gpio_buttons["Display_HAT_Mini"],
        },
    }

    button_def = _build_button_profiles(button_templates, button_profile_defs)
    button_def.update({
        # call from sensor_ant
        "Edge_Remote": {
            "MAIN": {
                "PAGE": ("scroll_prev", "scroll_next"),
                "CUSTOM": ("turn_on_off_light", "enter_menu"),
                "LAP": ("count_laps",),
            },
            #"MAIN": {
            #    "PAGE": ("scroll_prev", "scroll_next"),
            #    "CUSTOM": ("start_and_stop_manual", "reset_count"),
            #    "LAP": ("count_laps",),
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
                "NAVIGATION_LEFT": ("", ""),
                "NAVIGATION_RIGHT": ("", ""),
                "SHIFT_UP_LEFT": ("scroll_prev", "get_screenshot"),
                "SHIFT_UP_RIGHT": ("scroll_next", "start_and_stop_manual"),
                "SHIFT_UP_BOTH": ("count_laps", "reset_count"),
                "A": ("", ""),
                "B": ("", ""),
                "Y": ("change_mode", "enter_menu"),
                "Z": ("turn_on_off_light", ""),
            },
            "MENU": {
                "NAVIGATION_UP": ("press_shift_tab", ""),
                "NAVIGATION_DOWN": ("press_tab", ""),
                "NAVIGATION_LEFT": ("back_menu", ""),
                "NAVIGATION_RIGHT": ("press_space", ""),
                "SHIFT_UP_LEFT": ("press_tab", "get_screenshot"),
                "SHIFT_UP_RIGHT": ("press_space", ""),
                "SHIFT_UP_BOTH": ("back_menu", ""),
                "A": ("press_space", ""),
                "B": ("back_menu", ""),
                "Y": ("", ""),
                "Z": ("", ""),
            },
            "DIALOG": {
                "NAVIGATION_UP": ("press_shift_tab", ""),
                "NAVIGATION_DOWN": ("press_tab", ""),
                "NAVIGATION_LEFT": ("press_shift_tab", ""),
                "NAVIGATION_RIGHT": ("press_tab", ""),
                "SHIFT_UP_LEFT": ("press_shift_tab", "get_screenshot"),
                "SHIFT_UP_RIGHT": ("press_tab", ""),
                "SHIFT_UP_BOTH": ("press_space", ""),
                "A": ("press_space", ""),
                "B": ("", ""),
                "Y": ("", ""),
                "Z": ("", ""),
            },
            "MAP": {
                "NAVIGATION_UP": ("", ""),
                "NAVIGATION_DOWN": ("", ""),
                "NAVIGATION_LEFT": ("", "map_overlay_prev_time"),
                "NAVIGATION_RIGHT": ("", "map_overlay_next_time"),
                "SHIFT_UP_LEFT": ("scroll_prev", "get_screenshot"),
                "SHIFT_UP_RIGHT": ("scroll_next", "start_and_stop_manual"),
                "SHIFT_UP_BOTH": ("count_laps", "reset_count"),
                "A": ("map_zoom_plus", ""),
                "B": ("map_zoom_minus", ""),
                "Y": ("change_mode", ""),
                "Z": ("change_map_overlays", ""),
            },
            "MAP_1": {
                "NAVIGATION_UP": ("map_move_y_plus", ""),
                "NAVIGATION_DOWN": ("map_move_y_minus", ""),
                "NAVIGATION_LEFT": ("map_move_x_minus", "map_overlay_prev_time"),
                "NAVIGATION_RIGHT": ("map_move_x_plus", "map_overlay_next_time"),
                "SHIFT_UP_LEFT": ("scroll_prev", "get_screenshot"),
                "SHIFT_UP_RIGHT": ("scroll_next", "start_and_stop_manual"),
                "SHIFT_UP_BOTH": ("count_laps", "reset_count"),
                "A": ("map_zoom_plus", ""),
                "B": ("map_zoom_minus", ""),
                "Y": ("change_mode", ""),
                "Z": ("change_map_overlays", ""),
            },
            "COURSE_PROFILE": {
                "NAVIGATION_UP": ("", ""),
                "NAVIGATION_DOWN": ("", ""),
                "NAVIGATION_LEFT": ("", ""),
                "NAVIGATION_RIGHT": ("", ""),
                "SHIFT_UP_LEFT": ("scroll_prev", "get_screenshot"),
                "SHIFT_UP_RIGHT": ("scroll_next", "start_and_stop_manual"),
                "SHIFT_UP_BOTH": ("count_laps", "reset_count"),
                "A": ("map_zoom_plus", ""),
                "B": ("map_zoom_minus", ""),
                "Y": ("change_mode", ""),
                "Z": ("", ""),
            },
            "COURSE_PROFILE_1": {
                "NAVIGATION_UP": ("", ""),
                "NAVIGATION_DOWN": ("", ""),
                "NAVIGATION_LEFT": ("map_move_x_minus", ""),
                "NAVIGATION_RIGHT": ("map_move_x_plus", ""),
                "SHIFT_UP_LEFT": ("scroll_prev", "get_screenshot"),
                "SHIFT_UP_RIGHT": ("scroll_next", "start_and_stop_manual"),
                "SHIFT_UP_BOTH": ("count_laps", "reset_count"),
                "A": ("map_zoom_plus", ""),
                "B": ("map_zoom_minus", ""),
                "Y": ("change_mode", ""),
                "Z": ("", ""),
            },
        },
        # override from "Zwift Click V2 (BLE)"
        "Zwift_Click_V2_DUAL": {
            "MAIN": {
                #"NAVIGATION_UP": ("gadgetbridge_termux_voice_command", ""),
                "NAVIGATION_UP": ("", ""),
                "NAVIGATION_DOWN": ("gadgetbridge_google_assistant", ""),
                #"NAVIGATION_DOWN": ("", ""),
                "NAVIGATION_LEFT": ("", ""),
                "NAVIGATION_RIGHT": ("", ""),
                "SHIFT_UP_LEFT": ("scroll_prev", "get_screenshot"),
                "SHIFT_UP_RIGHT": ("scroll_next", "start_and_stop_manual"),
                "SHIFT_UP_BOTH": ("count_laps", "reset_count"),
                "A": ("map_zoom_plus", ""),
                "B": ("map_zoom_minus", ""),
                "Y": ("change_mode", "enter_menu"),
                "Z": ("turn_on_off_light", ""),
            },
            "MAP_1": {
                "NAVIGATION_UP": ("map_move_y_plus", ""),
                "NAVIGATION_DOWN": ("map_move_y_minus", ""),
                "NAVIGATION_LEFT": ("map_move_x_minus", ""),
                "NAVIGATION_RIGHT": ("map_move_x_plus", ""),
                "SHIFT_UP_LEFT": ("map_overlay_prev_time", "get_screenshot"),
                "SHIFT_UP_RIGHT": ("map_overlay_next_time", ""),
                "SHIFT_UP_BOTH": ("", ""),
                "A": ("map_zoom_plus", ""),
                "B": ("map_zoom_minus", ""),
                "Y": ("change_mode", ""),
                "Z": ("change_map_overlays", ""),
            },
        },
    })

    # Build dedicated profile for dual display + Zwift Click V2.
    # 1) copy from base profile
    # 2) override only entries defined in Zwift_Click_V2_DUAL
    zwift_click_v2_dual_overrides = copy.deepcopy(
        button_def["Zwift_Click_V2_DUAL"]
    )
    button_def["Zwift_Click_V2_DUAL"] = copy.deepcopy(button_def["Zwift_Click_V2"])
    for page_name, page_overrides in zwift_click_v2_dual_overrides.items():
        if page_name not in button_def["Zwift_Click_V2_DUAL"]:
            button_def["Zwift_Click_V2_DUAL"][page_name] = {}
        button_def["Zwift_Click_V2_DUAL"][page_name].update(page_overrides)

    for profile_button_def in button_def.values():
        if "MENU" in profile_button_def and "DIALOG" not in profile_button_def:
            profile_button_def["DIALOG"] = copy.deepcopy(profile_button_def["MENU"])

    page_mode = "MAIN"

    # mode group setting changed by change_mode
    button_mode_is_change = False
    button_mode_pages = {
        "MAIN": ["MAIN", "MAIN_1"],
        "MAP": ["MAP", "MAP_1"],
        "COURSE_PROFILE": ["COURSE_PROFILE", "COURSE_PROFILE_1"],
    }
    button_mode_index = {
        "MAIN": 0,
        "MAP": 0,
        "COURSE_PROFILE": 0,
    }

    def __init__(self, config):
        self.config = config
        self._dual_map_mode_active = False
        if hasattr(config, "use_custom_gpio_buttons"):
            self.use_custom_gpio_buttons = config.use_custom_gpio_buttons

    def _resolve_button_profile(self, button_hard):
        if button_hard != "Zwift_Click_V2":
            return button_hard
        if not self.config.G_DUAL_DISPLAY_MODE:
            return button_hard
        if "Zwift_Click_V2_DUAL" not in self.button_def:
            return button_hard

        cfg = self.config.G_ZWIFT_CLICK_V2
        if not cfg["STATUS"]:
            return button_hard

        return "Zwift_Click_V2_DUAL"

    def press_button(self, button_hard, press_button, index):
        gui = self.config.gui
        if gui is None or gui.stack_widget is None:
            return
        profile = self._resolve_button_profile(button_hard)
        stack_index = gui.stack_widget.currentIndex()
        main_page_index = -1
        if gui.main_page is not None:
            try:
                main_page_index = gui.main_page.currentIndex()
            except Exception:
                main_page_index = -1

        dialog_active = gui.dialog_exists()

        if dialog_active:
            profile_buttons = self.button_def[profile]
            if "DIALOG" in profile_buttons:
                self.page_mode = "DIALOG"
            elif "MENU" in profile_buttons:
                self.page_mode = "MENU"
            else:
                self.page_mode = "MAIN"
        else:
            w_index = stack_index
            if w_index == 1:
                current_widget = gui.main_page.widget(gui.main_page.currentIndex())
                if self.config.G_DUAL_DISPLAY_MODE:
                    if current_widget == gui.course_profile_graph_widget:
                        mode_key = "COURSE_PROFILE"
                    elif self._dual_map_mode_active:
                        mode_key = "MAP"
                    elif current_widget == gui.map_widget:
                        mode_key = "MAP"
                    else:
                        mode_key = "MAIN"
                else:
                    if current_widget == gui.map_widget:
                        mode_key = "MAP"
                    elif current_widget == gui.course_profile_graph_widget:
                        mode_key = "COURSE_PROFILE"
                    else:
                        mode_key = "MAIN"

                pages = self.button_mode_pages[mode_key]
                if pages:
                    mode_index = self.button_mode_index[mode_key]
                    if mode_index < 0 or mode_index >= len(pages):
                        mode_index = 0
                    self.page_mode = pages[mode_index]
                else:
                    self.page_mode = mode_key
                # for no implementation
                if self.page_mode not in self.button_def[profile]:
                    self.page_mode = "MAIN"
                    if self.config.G_DUAL_DISPLAY_MODE and mode_key == "MAP":
                        self._dual_map_mode_active = False
                        map_widget = gui.map_widget
                        if map_widget is not None:
                            map_widget.lock_on()
            elif w_index >= 2:
                self.page_mode = "MENU"

        if press_button not in self.button_def[profile][self.page_mode]:
            app_logger.warning(
                "button key error: "
                f"'{press_button}' is not defined in "
                f"self.button_def['{profile}']['{self.page_mode}']"
            )
            return
        func_str = self.button_def[profile][self.page_mode][press_button][index]
        if func_str in ("", "dummy"):
            app_logger.debug(
                "[BUTTON] noop "
                f"device={button_hard}, profile={profile}, page={self.page_mode}, "
                f"key={press_button}, index={index}, action={func_str!r}"
            )
            return

        app_logger.debug(
            "[BUTTON] dispatch "
            f"device={button_hard}, profile={profile}, "
            f"stack_index={stack_index}, main_page_index={main_page_index}, "
            f"dialog_active={dialog_active}, page={self.page_mode}, "
            f"key={press_button}, index={index}, action={func_str}"
        )

        getattr(self.config.gui, func_str)()

    def change_mode(self):
        # check MAP
        w = self.config.gui.main_page.widget(self.config.gui.main_page.currentIndex())
        map_widget = self.config.gui.map_widget

        if self.config.G_DUAL_DISPLAY_MODE:
            if w == self.config.gui.course_profile_graph_widget:
                self.change_mode_index("COURSE_PROFILE")
                if not self.button_mode_is_change:
                    w.lock_on()
                else:
                    w.lock_off()
                return

            map_pages = self.button_mode_pages["MAP"]
            if not map_pages or map_widget is None:
                self.change_mode_index("MAIN")
                return

            if not self._dual_map_mode_active:
                self._dual_map_mode_active = True
                # Start from MAP_1 behavior when switching from MAIN in dual mode.
                initial_map_mode_index = 1 if len(map_pages) > 1 else 0
                self.button_mode_index["MAP"] = initial_map_mode_index
                self.button_mode_is_change = True
                self.page_mode = map_pages[initial_map_mode_index]
                map_widget.lock_off()
                return

            self.change_mode_index("MAP")
            if not self.button_mode_is_change:
                self._dual_map_mode_active = False
                self.page_mode = "MAIN"
                map_widget.lock_on()
            else:
                map_widget.lock_off()
            return

        if "MAIN" in self.page_mode:
            self.change_mode_index("MAIN")
        # if display is MAP: change MAP_1 -> MAP_2 -> MAP -> ...
        elif w == self.config.gui.map_widget:
            self.change_mode_index("MAP")
            # additional: lock current position when normal page
            if not self.button_mode_is_change:
                w.lock_on()
            else:
                w.lock_off()
        elif w == self.config.gui.course_profile_graph_widget:
            self.change_mode_index("COURSE_PROFILE")
            # additional: lock current position when normal page
            if not self.button_mode_is_change:
                w.lock_on()
            else:
                w.lock_off()

    def change_mode_index(self, mode):
        self.button_mode_index[mode] = self.button_mode_index[mode] + 1
        self.button_mode_is_change = True
        if self.button_mode_index[mode] >= len(self.button_mode_pages[mode]):
            self.button_mode_index[mode] = 0
            self.button_mode_is_change = False
        self.page_mode = self.button_mode_pages[mode][
            self.button_mode_index[mode]
        ]
