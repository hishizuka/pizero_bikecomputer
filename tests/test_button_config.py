import unittest

from modules.button_config import Button_Config, _build_button_profiles


class ButtonConfigTemplateTest(unittest.TestCase):
    def test_button_shim_and_ioexpander_use_same_five_button_actions(self):
        button_shim = Button_Config.button_def["Button_Shim"]
        ioexpander = Button_Config.button_def["IOExpander"]

        self.assertEqual(button_shim["MAIN"]["A"], ioexpander["MAIN"]["GP0"])
        self.assertEqual(button_shim["MAIN"]["E"], ioexpander["MAIN"]["GP4"])
        self.assertEqual(button_shim["MAP_1"]["C"], ioexpander["MAP_1"]["GP2"])
        self.assertNotIn("A", ioexpander["MAIN"])

    def test_gpio_profiles_expand_to_expected_pins(self):
        self.assertEqual(
            set(Button_Config.button_def["PiTFT"]["MAIN"]),
            {5, 6, 12, 13, 16},
        )
        self.assertEqual(
            set(Button_Config.button_def["Papirus"]["MAIN"]),
            {16, 20, 21, 26},
        )
        self.assertEqual(
            Button_Config.button_def["Pirate_Audio_old"]["MAIN"][20],
            ("start_and_stop_manual", ""),
        )
        self.assertNotIn(24, Button_Config.button_def["Pirate_Audio_old"]["MAIN"])
        self.assertEqual(
            Button_Config.button_def["DFRobot_RPi_Display"]["MENU"][20],
            ("press_tab", "back_menu"),
        )

    def test_custom_gpio_keeps_logical_buttons_separate_from_pins(self):
        custom_gpio = Button_Config.button_def["Custom_GPIO"]

        self.assertEqual(set(custom_gpio["MAIN"]), {"A", "B", "C", "D", "E"})
        self.assertEqual(Button_Config.custom_gpio_buttons["A"], 4)
        self.assertEqual(
            custom_gpio["MAIN"]["E"],
            ("scroll_next", "enter_menu"),
        )

    def test_custom_gpio_enable_flag_lives_in_button_config(self):
        class Config:
            pass

        button_config = Button_Config(Config())
        self.assertFalse(button_config.use_custom_gpio_buttons)

    def test_config_enable_flag_is_absorbed(self):
        class Config:
            use_custom_gpio_buttons = True

        button_config = Button_Config(Config())
        self.assertTrue(button_config.use_custom_gpio_buttons)

    def test_button_profile_overrides_update_template_actions(self):
        button_templates = {
            "TWO": {
                "MAIN": {
                    "A": ("template_a_short", "template_a_long"),
                    "B": ("template_b_short", "template_b_long"),
                },
            },
        }
        profile_defs = {
            "Profile": {
                "TEMPLATE": "TWO",
                "BUTTONS": {"A": 1, "B": 2},
                "OVERRIDES": {
                    "MAIN": {
                        1: ("override_a_short", ""),
                    },
                },
            },
        }

        button_def = _build_button_profiles(button_templates, profile_defs)

        self.assertEqual(button_def["Profile"]["MAIN"][1], ("override_a_short", ""))
        self.assertEqual(
            button_def["Profile"]["MAIN"][2],
            ("template_b_short", "template_b_long"),
        )


if __name__ == "__main__":
    unittest.main()
