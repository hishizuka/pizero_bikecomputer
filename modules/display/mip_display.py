import time

import asyncio
import numpy as np

from logger import app_logger
from .display_core import Display

_SENSOR_DISPLAY = False
MODE = "Python"
try:
    import pigpio

    _SENSOR_DISPLAY = True
    import pyximport

    pyximport.install()
    from .cython.mip_helper import conv_3bit_color, MipDisplay_CPP

    MODE = "Cython_full"
except ImportError:
    pass

app_logger.info(f"MIP DISPLAY: {_SENSOR_DISPLAY}")

# https://qiita.com/hishi/items/669ce474fcd76bdce1f1
# LPM027M128C, LPM027M128B,

# GPIO.BCM
GPIO_DISP = 27  # 13 in GPIO.BOARD
GPIO_SCS = 23  # 16 in GPIO.BOARD
GPIO_VCOMSEL = 17  # 11 in GPIO.BOARD
GPIO_BACKLIGHT = 18  # 12 in GPIO.BOARD with hardware PWM in pigpio

# update mode
# https://www.j-display.com/product/pdf/Datasheet/3LPM027M128C_specification_ver02.pdf
# 0x90 4bit update mode
# 0x80 3bit update mode (fast)
# 0x88 1bit update mode (most fast, but 2-color)
UPDATE_MODE = 0x80

# BACKLIGHT frequency
GPIO_BACKLIGHT_FREQ = 64


class MipDisplay(Display):
    pi = None
    spi = None
    interval = 0.25
    mip_display_cpp = None

    has_auto_brightness = True
    has_touch = False
    send = True

    brightness_table = [0, 1, 2, 3, 5, 7, 10, 25, 50, 100]
    brightness = 0

    size = (400, 240)

    def __init__(self, config, size=None):
        super().__init__(config)

        if size:
            self.size = size

        if MODE == "Cython":
            self.conv_color = conv_3bit_color
        elif MODE == "Cython_full":
            self.mip_display_cpp = MipDisplay_CPP(config.G_DISPLAY_PARAM["SPI_CLOCK"])
            self.mip_display_cpp.set_screen_size(self.size[0], self.size[1])
            self.update = self.mip_display_cpp.update
            self.set_brightness = self.mip_display_cpp.set_brightness
            self.inversion = self.mip_display_cpp.inversion
            self.quit = self.mip_display_cpp.quit
            return
        else:
            self.conv_color = self.conv_3bit_color_py

        self.init_buffer()

        # spi
        self.pi = pigpio.pi()
        self.spi = self.pi.spi_open(0, config.G_DISPLAY_PARAM["SPI_CLOCK"], 0)

        self.pi.set_mode(GPIO_DISP, pigpio.OUTPUT)
        self.pi.set_mode(GPIO_SCS, pigpio.OUTPUT)
        self.pi.set_mode(GPIO_VCOMSEL, pigpio.OUTPUT)

        self.pi.write(GPIO_SCS, 0)
        self.pi.write(GPIO_DISP, 1)
        self.pi.write(GPIO_VCOMSEL, 1)
        time.sleep(0.01)

        # backlight
        self.pi.set_mode(GPIO_BACKLIGHT, pigpio.OUTPUT)
        self.pi.hardware_PWM(GPIO_BACKLIGHT, GPIO_BACKLIGHT_FREQ, 0)

    def init_buffer(self):
        self.buff_width = int(self.size[0] * 3 / 8) + 2  # for 3bit update mode
        self.img_buff_rgb8 = np.empty((self.size[1], self.buff_width), dtype="uint8")
        self.pre_img = np.zeros((self.size[1], self.buff_width), dtype="uint8")
        self.img_buff_rgb8[:, 0] = UPDATE_MODE
        self.img_buff_rgb8[:, 1] = np.arange(self.size[1])
        # for MIP_640
        self.img_buff_rgb8[:, 0] = self.img_buff_rgb8[:, 0] + (
            np.arange(self.size[1]) >> 8
        )

    def start_coroutine(self):
        self.draw_queue = asyncio.Queue()
        asyncio.create_task(self.draw_worker())

    def clear(self):
        self.pi.write(GPIO_SCS, 1)
        time.sleep(0.000006)
        self.pi.spi_write(self.spi, [0b00100000, 0])  # ALL CLEAR MODE
        self.pi.write(GPIO_SCS, 0)
        time.sleep(0.000006)
        self.set_brightness(0)

    def no_update(self):
        self.pi.write(GPIO_SCS, 1)
        time.sleep(0.000006)
        self.pi.spi_write(self.spi, [0b00000000, 0])  # NO UPDATE MODE
        self.pi.write(GPIO_SCS, 0)
        time.sleep(0.000006)

    def blink(self, sec):
        s = sec
        state = True
        while s > 0:
            self.pi.write(GPIO_SCS, 1)
            time.sleep(0.000006)
            if state:
                self.pi.spi_write(self.spi, [0b00010000, 0])  # BLINK(BLACK) MODE
            else:
                self.pi.spi_write(self.spi, [0b00011000, 0])  # BLINK(WHITE) MODE
            self.pi.write(GPIO_SCS, 0)
            time.sleep(self.interval)
            s -= self.interval
            state = not state
        self.no_update()

    def inversion(self, sec):
        s = sec
        state = True
        while s > 0:
            self.pi.write(GPIO_SCS, 1)
            time.sleep(0.000006)
            if state:
                self.pi.spi_write(self.spi, [0b00010100, 0])  # INVERSION MODE
            else:
                self.no_update()
            self.pi.write(GPIO_SCS, 0)
            time.sleep(self.interval)
            s -= self.interval
            state = not state
        self.no_update()

    async def draw_worker(self):
        while True:
            img_bytes = await self.draw_queue.get()
            if img_bytes is None:
                break
            # self.config.check_time("mip_draw_worker start")
            # t = datetime.datetime.now()
            self.pi.write(GPIO_SCS, 1)
            await asyncio.sleep(0.000006)
            self.pi.spi_write(self.spi, img_bytes)
            # dummy output for ghost line
            self.pi.spi_write(self.spi, [0x00000000, 0])
            await asyncio.sleep(0.000006)
            self.pi.write(GPIO_SCS, 0)
            # self.config.check_time("mip_draw_worker end")
            # print("####### draw(Py)", (datetime.datetime.now()-t).total_seconds())
            self.draw_queue.task_done()

    def update(self, im_array, direct_update):
        # direct update not yet supported for MPI_640
        if direct_update and self.config.G_DISPLAY in ("MIP_640",):
            direct_update = False

        # self.config.check_time("mip_update start")
        self.img_buff_rgb8[:, 2:] = self.conv_color(im_array)
        # self.config.check_time("packbits")

        # differential update
        diff_lines = np.where(
            np.sum((self.img_buff_rgb8 == self.pre_img), axis=1) != self.buff_width
        )[0]
        # print("diff ", int(len(diff_lines)/self.size[1]*100), "%")
        # print(" ")

        if not len(diff_lines):
            return
        self.pre_img[diff_lines] = self.img_buff_rgb8[diff_lines]
        # self.config.check_time("diff_lines")

        if direct_update:
            self.pi.write(GPIO_SCS, 1)
            time.sleep(0.000006)
            self.pi.spi_write(self.spi, self.img_buff_rgb8[diff_lines].tobytes())
            time.sleep(0.000006)
            self.pi.write(GPIO_SCS, 0)
        # put queue
        elif len(diff_lines) < 270:
            # await self.draw_queue.put((self.img_buff_rgb8[diff_lines].tobytes()))
            asyncio.create_task(
                self.draw_queue.put((self.img_buff_rgb8[diff_lines].tobytes()))
            )
        else:
            # for MIP 640x480
            l = int(len(diff_lines) / 2)
            # await self.draw_queue.put((self.img_buff_rgb8[diff_lines[0:l]].tobytes()))
            # await self.draw_queue.put((self.img_buff_rgb8[diff_lines[l:]].tobytes()))
            asyncio.create_task(
                self.draw_queue.put((self.img_buff_rgb8[diff_lines[0:l]].tobytes()))
            )
            asyncio.create_task(
                self.draw_queue.put((self.img_buff_rgb8[diff_lines[l:]].tobytes()))
            )

    def conv_2bit_color_py(self, im_array):
        return np.packbits(
            (im_array >= 128).reshape(self.size[1], self.size[0] * 3),
            axis=1,
        )

    def conv_3bit_color_py(self, im_array):
        # pseudo 3bit color (128~216: simple dithering)
        # set even pixel and odd pixel to 0
        # 1. convert 2bit color
        # im_array_bin = (im_array >= 128)

        # 2. set even pixel (2n, 2n) to 0
        # im_array_bin[0::2, 0::2, :][im_array[0::2, 0::2, :] <= 216] = 0
        # 3. set odd pixel (2n+1, 2n+1) to 0
        # im_array_bin[1::2, 1::2, :][im_array[1::2, 1::2, :] <= 216] = 0

        im_array_bin = np.zeros(im_array.shape).astype("bool")
        im_array_bin[0::2, 0::2, :][
            im_array[0::2, 0::2, :]
            >= self.config.G_DITHERING_CUTOFF["LOW"][
                self.config.G_DITHERING_CUTOFF_LOW_INDEX
            ]
        ] = 1
        im_array_bin[1::2, 1::2, :][
            im_array[1::2, 1::2, :]
            >= self.config.G_DITHERING_CUTOFF["LOW"][
                self.config.G_DITHERING_CUTOFF_LOW_INDEX
            ]
        ] = 1
        im_array_bin[0::2, 1::2, :][
            im_array[0::2, 1::2, :]
            > self.config.G_DITHERING_CUTOFF["HIGH"][
                self.config.G_DITHERING_CUTOFF_HIGH_INDEX
            ]
        ] = 1
        im_array_bin[1::2, 0::2, :][
            im_array[1::2, 0::2, :]
            > self.config.G_DITHERING_CUTOFF["HIGH"][
                self.config.G_DITHERING_CUTOFF_HIGH_INDEX
            ]
        ] = 1

        return np.packbits(im_array_bin.reshape(self.size[1], self.size[0] * 3), axis=1)

    def set_brightness(self, b):
        if b == self.brightness:
            return
        self.pi.hardware_PWM(GPIO_BACKLIGHT, GPIO_BACKLIGHT_FREQ, b * 10000)
        self.brightness = b

    def backlight_blink(self):
        for x in range(2):
            for pw in range(0, 100, 1):
                self.pi.hardware_PWM(GPIO_BACKLIGHT, GPIO_BACKLIGHT_FREQ, pw * 10000)
                time.sleep(0.05)
            for pw in range(100, 0, -1):
                self.pi.hardware_PWM(GPIO_BACKLIGHT, GPIO_BACKLIGHT_FREQ, pw * 10000)
                time.sleep(0.05)

    def quit(self):
        asyncio.create_task(self.draw_queue.put(None))
        self.set_brightness(0)
        self.clear()

        self.pi.write(GPIO_DISP, 1)
        time.sleep(0.01)

        self.pi.spi_close(self.spi)
        self.pi.stop()

    def screen_flash_long(self):
        return self.inversion(0.8)

    def screen_flash_short(self):
        return self.inversion(0.3)
