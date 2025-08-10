import time

import asyncio
import numpy as np

from .display_core import Display


class MipDisplayBase(Display):
    # https://qiita.com/hishi/items/669ce474fcd76bdce1f1
    # LPM027M128C, LPM027M128B,

    # GPIO.BCM
    '''
    SCS = 23  # 16pin
    DISP = 27  # 13pin
    VCOMSEL = 17  # 11pin
    '''
    SCS = 8  # 24pin (CE0)
    DISP = 25  # 22pin
    VCOMSEL = 24  # 18pin
    #'''
    BACKLIGHT = 18  # 12pin with hardware PWM in pigpio
    BACKLIGHT_SWITCH = 24  # 18pin GPIO.BOARD

    # update mode
    # https://www.j-display.com/product/pdf/Datasheet/3LPM027M128C_specification_ver02.pdf
    # 0x90 4bit update mode
    # 0x80 3bit update mode (fast)
    # 0x88 1bit update mode (most fast, but 2-color)
    UPDATE_MODE = 0x80

    # BACKLIGHT frequency
    BACKLIGHT_FREQ = 64

    pi = None
    spi = None
    interval = 0.25
    mip_display_cpp = None

    has_touch = False
    send = True

    brightness_table = [0, 1, 2, 3, 5, 7, 10, 25, 50, 100]
    brightness = 0
    minimum_brightness = 0

    size = (400, 240)
    bpp = 3 # 1/3/6
    color = 8 # 2/8/64

    spi_max_buf_size = 65536
    spi_max_rows = 0

    quit_status = False
    use_cpp = False

    def __init__(self, config, size=None, color=None):
        super().__init__(config)

        if size:
            self.size = size
        if color:
            self.color = color
            if color == 2:
                self.has_color = False
                self.bpp = 1
                if self.config.G_DISPLAY.startswith("MIP_JDI"):
                    self.UPDATE_MODE = 0x88
            if color == 8:
                self.bpp = 3
            if color == 64:
                self.bpp = 6

        self.init_minimum_brightness()
        self.init_backlight_func()

        if self.init_cython():
            # switch to cython
            return

        # init spi/gpio/backlight
        self.init_spi()
        self.init_gpio()
        self.init_gpio_write()
        self.init_backlight()
        self.clear()

        self.init_buffer()

    def init_minimum_brightness(self):
        if self.config.G_DISPLAY == "MIP_JDI_color_400x240":
            self.minimum_brightness = 3
        elif self.config.G_DISPLAY == "MIP_JDI_color_640x480":
            self.minimum_brightness = 10
        elif self.config.G_DISPLAY == "MIP_Azumo_color_272x451":
            self.minimum_brightness = 10

    def init_backlight_func(self):
        pass

    def start_coroutine(self):
        if not self.use_cpp:
            self.draw_queue = asyncio.Queue()
            asyncio.create_task(self.draw_worker())

    def init_spi(self):
        pass

    def init_gpio(self):
        pass

    def init_backlight(self):
        pass

    def init_buffer(self):
        self.buff_width = int(self.size[0] * self.bpp / 8) + 2  # for 3bit update mode
        if self.color == 64:
            self.buff_width += 2
        self.spi_max_rows = int(self.spi_max_buf_size/self.buff_width)

        self.img_buff_rgb8 = np.zeros((self.size[1], self.buff_width), dtype="uint8")
        self.pre_img = np.zeros((self.size[1], self.buff_width), dtype="uint8")
        self.img_buff_rgb8[:, 0] = self.UPDATE_MODE+ (np.arange(self.size[1]) >> 8)
        self.img_buff_rgb8[:, 1] = np.arange(self.size[1]) & 0xFF

# The following code is adapted from an Apache License 2.0 project.
# Copyright (c) 2024 Azumo
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     third_party/apache/LICENSE.Apache2
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# start
        if self.config.G_DISPLAY.startswith("MIP_Azumo_color_272x451") and self.color == 64:
            self.img_buff_rgb8[:, 0] |= 0b10
            self.img_buff_rgb8[:, 2+102] = np.arange(self.size[1]) >> 8
            self.img_buff_rgb8[:, 2+102+1] = np.arange(self.size[1]) & 0xFF
# end
        elif self.config.G_DISPLAY.startswith("MIP_Sharp_mono"):
            self.img_buff_rgb8[:, 2:] = 255
            self.pre_img[:, 2:] = 255
            # address is set in reversed bits
            self.img_buff_rgb8[:, 1] = [
                int("{:08b}".format(a)[::-1], 2) for a in range(self.size[1])
            ]
            self.update(self.pre_img[:, 2:], direct_update=True)

    def init_gpio_write(self):
        self.gpio_write(self.SCS, 0)
        self.gpio_write(self.DISP, 1)
        self.gpio_write(self.VCOMSEL, 1)

    def clear(self):
        self.gpio_write(self.SCS, 1)
        time.sleep(0.000006)
        self.spi_write([0b00100000, 0])  # ALL CLEAR MODE
        self.gpio_write(self.SCS, 0)
        time.sleep(0.000006)
        self.set_brightness(0)

    def no_update(self):
        self.gpio_write(self.SCS, 1)
        time.sleep(0.000006)
        self.spi_write([0b00000000, 0])  # NO UPDATE MODE
        self.gpio_write(self.SCS, 0)
        time.sleep(0.000006)

    def blink(self, sec):
        s = sec
        state = True
        while s > 0:
            self.gpio_write(self.SCS, 1)
            time.sleep(0.000006)
            if state:
                self.spi_write([0b00010000, 0])  # BLINK(BLACK) MODE
            else:
                self.spi_write([0b00011000, 0])  # BLINK(WHITE) MODE
            self.gpio_write(self.SCS, 0)
            time.sleep(self.interval)
            s -= self.interval
            state = not state
        self.no_update()

    def inversion_draw(self, inv_buf):
        buf = self.split_buffer(inv_buf, np.arange(0, inv_buf.shape[0]), False)
        for b in buf:
            if b is not None:
                self.spi_write(b)

    def inversion(self, sec):
        s = sec
        state = True
        do_manual_inversion = self.config.G_DISPLAY.startswith((
            "MIP_Azumo_color_272x451",
            "MIP_Sharp_mono"
        ))

        while s > 0:
            self.gpio_write(self.SCS, 1)
            time.sleep(0.000006)

            if do_manual_inversion:
                if state:
                    buf = self.img_buff_rgb8.copy()
                    if self.config.G_DISPLAY == "MIP_Azumo_color_272x451" and self.color == 64:
                        buf[:,2:2+102] = np.invert(buf[:,2:2+102])
                        buf[:,2+102+2:] = np.invert(buf[:,2+102+2:])
                    else:
                        buf[:,2:] = np.invert(buf[:,2:])
                    self.inversion_draw(buf)
                else:
                    self.inversion_draw(self.img_buff_rgb8)
            else:
                # use inversion mode
                if state:
                    self.spi_write([0b00010100, 0])  # INVERSION MODE
                else:
                    self.no_update()

            self.gpio_write(self.SCS, 0)
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
            # t = datetime.now()
            self.gpio_write(self.SCS, 1)
            await asyncio.sleep(0.000006)
            self.spi_write(img_bytes)
            await asyncio.sleep(0.000006)
            self.gpio_write(self.SCS, 0)
            # self.config.check_time("mip_draw_worker end")
            # print("####### draw(Py)", (datetime.now()-t).total_seconds())
            self.draw_queue.task_done()

    def update(self, im_array, direct_update):
        if self.quit_status:
            return

        # self.config.check_time("mip_update start")
        self.img_buff_rgb8[:, 2:] = self.conv_color(im_array)
        # self.config.check_time("packbits")

        # differential update
        diff_lines = np.where(
            np.sum((self.img_buff_rgb8 == self.pre_img), axis=1) != self.buff_width
        )[0]
        # print(f"diff {int(len(diff_lines)/self.size[1]*100)}%")

        if not len(diff_lines):
            return
        self.pre_img[diff_lines] = self.img_buff_rgb8[diff_lines]
        # self.config.check_time("diff_lines")

        buf = self.split_buffer(self.img_buff_rgb8, diff_lines, direct_update)
        if direct_update:
        #if True:
            self.gpio_write(self.SCS, 1)
            time.sleep(0.000006)
            for b in buf:
                if b is not None:
                    self.spi_write(b)
            time.sleep(0.000006)
            self.gpio_write(self.SCS, 0)
        # put queue
        else:
            for b in buf:
                if b is not None:
                    asyncio.create_task(self.draw_queue.put((b)))

    def split_buffer(self, img_buff, diff_lines, direct_update):
        if len(diff_lines) < self.spi_max_rows:
            buf = self.conv_bytes(img_buff[diff_lines])
            return [buf.tobytes(), None]            
        else:
            # for MIP 640x480, MIP_Azumo_color_272x451
            l = int(len(diff_lines) / 2)
            b1_orig = img_buff[diff_lines[:l]]
            end = -2 if direct_update else b1_orig.size
            b1 = self.conv_bytes(b1_orig)
            b2 = self.conv_bytes(img_buff[diff_lines[l:]])
            buf = [
                b1[:end].tobytes(),
                b2.tobytes()
            ]
            return buf

    def conv_bytes(self, buf):
        bytes_data = np.empty(buf.size + 2, dtype=np.uint8)
        bytes_data[:-2] = buf.ravel()
        bytes_data[-2:] = 0
        return bytes_data

    def conv_1bit_2colors_py(self, im_array):
        return ~im_array.reshape(im_array.shape[:2])

    def conv_3bit_8colors_py(self, im_array):
        return np.packbits(
            (im_array >> 7).astype("bool").reshape(self.size[1], self.size[0] * 3),
            axis=1,
        )

    def conv_3bit_27colors_py(self, im_array, th=216):
        # pseudo 27 colors

        # 1. convert 2bit color
        im_array_bin = (im_array >> 7).astype("bool")
        # 2. set even pixel (2n, 2n) to 0
        im_array_bin[0::2, 0::2, :][im_array[0::2, 0::2, :] <= th] = False
        # 3. set odd pixel (2n+1, 2n+1) to 0
        im_array_bin[1::2, 1::2, :][im_array[1::2, 1::2, :] <= th] = False

        return np.packbits(im_array_bin.reshape(self.size[1], self.size[0] * 3), axis=1)

# The following code is adapted from an Apache License 2.0 project.
# Copyright (c) 2024 Azumo
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     third_party/apache/LICENSE.Apache2
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
    def conv_4bit_64colors_py(self, im_array):
        im_array_u8 = np.zeros((self.size[1], self.buff_width)).astype("uint8")
        im_array_u8[:,2:2+102] = np.packbits(
            ((im_array >> 6)&0b01).reshape(
                im_array.shape[0], im_array.shape[1] * im_array.shape[2]
            ),
            axis=1
        )
        im_array_u8[:, 2+102:2+102+2] = self.img_buff_rgb8[:, 2+102:2+102+2]
        im_array_u8[:,106:106+102] = np.packbits(
            (im_array >> 7).reshape(
                im_array.shape[0], im_array.shape[1] * im_array.shape[2]
            ),
            axis=1
        )
        return im_array_u8[:, 2:]

    def set_brightness(self, b):
        if b == self.brightness or self.quit_status:
            return
        self.set_PWM(b)
        self.brightness = b

    def set_minimum_brightness(self):
        self.set_brightness(self.minimum_brightness)

    def backlight_blink(self):
        for x in range(2):
            for pw in range(0, 100, 1):
                self.set_PWM(pw)
                time.sleep(0.05)
            for pw in range(100, 0, -1):
                self.set_PWM(pw)
                time.sleep(0.05)

    def quit(self):
        self.quit_status = True
        asyncio.create_task(self.draw_queue.put(None))
        self.set_brightness(0)
        self.clear()
        self.spi_close()

    def screen_flash_long(self):
        return self.inversion(0.8)

    def screen_flash_short(self):
        return self.inversion(0.3)
