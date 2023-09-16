import os

from ..sensor.sensor import Sensor

DISPLAY = None


class Display(Sensor):
    sensor = {}
    elements = ()
    display = None
    send_display = False

    def sensor_init(self):
        self.detect_display()
        self.set_resolution()

        self.reset()

        if not self.config.G_IS_RASPI:
            self.config.G_DISPLAY = "None"
            return

        if self.config.G_DISPLAY == "PiTFT":
            from .pitft_28_r import PiTFT28r

            self.display = PiTFT28r(self.config)
        elif self.config.G_DISPLAY in ("MIP", "MIP_640"):
            from .mip_display import MipDisplay

            self.display = MipDisplay(self.config)
            self.send_display = True
        elif self.config.G_DISPLAY in ("MIP_Sharp", "MIP_Sharp_320"):
            from .mip_sharp_display import MipSharpDisplay

            self.display = MipSharpDisplay(self.config)
            self.send_display = True
        elif self.config.G_DISPLAY == "Papirus":
            from .papirus_display import PapirusDisplay

            self.display = PapirusDisplay(self.config)
            self.send_display = True
        elif self.config.G_DISPLAY == "DFRobot_RPi_Display":
            from .dfrobot_rpi_display import DFRobotRPiDisplay

            self.display = DFRobotRPiDisplay(self.config)
            self.send_display = True

    def detect_display(self):
        hatdir = "/proc/device-tree/hat"
        product_file = hatdir + "/product"
        vendor_file = hatdir + "/vendor"

        if (os.path.exists(product_file)) and (os.path.exists(vendor_file)):
            with open(hatdir + "/product") as f:
                p = f.read()
            with open(hatdir + "/vendor") as f:
                v = f.read()
            print(product_file, ":", p)
            print(vendor_file, ":", v)

            # set display
            if p.find("Adafruit PiTFT HAT - 2.4 inch Resistive Touch") == 0:
                self.config.G_DISPLAY = "PiTFT"
            elif (p.find("PaPiRus ePaper HAT") == 0) and (v.find("Pi Supply") == 0):
                self.config.G_DISPLAY = "Papirus"

    def set_resolution(self):
        for key in self.config.G_AVAILABLE_DISPLAY.keys():
            if self.config.G_DISPLAY == key:
                self.config.G_WIDTH = self.config.G_AVAILABLE_DISPLAY[key]["size"][0]
                self.config.G_HEIGHT = self.config.G_AVAILABLE_DISPLAY[key]["size"][1]
                break

    def has_touch(self):
        return self.config.G_AVAILABLE_DISPLAY[self.config.G_DISPLAY]["touch"]

    def has_color(self):
        return self.config.G_AVAILABLE_DISPLAY[self.config.G_DISPLAY]["color"]

    def start_coroutine(self):
        if self.config.G_DISPLAY in ("MIP", "MIP_640", "MIP_Sharp", "MIP_Sharp_320"):
            self.display.start_coroutine()

    def quit(self):
        if not self.config.G_IS_RASPI:
            return
        if self.config.G_DISPLAY == "PiTFT":
            pass
        elif (
            self.config.G_DISPLAY in ("MIP", "MIP_640", "MIP_Sharp", "MIP_Sharp_320")
            and self.send_display
        ):
            self.display.quit()
        elif self.config.G_DISPLAY in ("Papirus", "DFRobot_RPi_Display"):
            self.display.quit()

    def update(self, buf, direct_update):
        if not self.config.G_IS_RASPI or not self.send_display:
            return

        if direct_update and self.config.G_DISPLAY in (
            "MIP",
            "MIP_Sharp",
            "MIP_Sharp_320",
        ):
            self.display.update(buf, direct_update)
        elif self.config.G_DISPLAY in ("MIP", "MIP_640", "MIP_Sharp", "MIP_Sharp_320"):
            self.display.update(buf, direct_update=False)
        elif self.config.G_DISPLAY in ("Papirus", "DFRobot_RPi_Display"):
            self.display.update(buf)

    def screen_flash_long(self):
        if (
            self.config.G_DISPLAY in ("MIP", "MIP_640", "MIP_Sharp", "MIP_Sharp_320")
            and self.send_display
        ):
            self.display.inversion(0.8)
            # self.display.blink(1.0)

    def screen_flash_short(self):
        if (
            self.config.G_DISPLAY in ("MIP", "MIP_640", "MIP_Sharp", "MIP_Sharp_320")
            and self.send_display
        ):
            self.display.inversion(0.3)

    def brightness_control(self):
        if not self.config.G_IS_RASPI:
            return
        if self.config.G_DISPLAY == "PiTFT":
            self.display.change_brightness()
        elif self.config.G_DISPLAY in ("MIP", "MIP_640") and self.send_display:
            self.display.change_brightness()
