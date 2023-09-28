import time

import asyncio
import numpy as np

from logger import app_logger

_SENSOR_DISPLAY = False
try:
    import pigpio

    _SENSOR_DISPLAY = True
except ImportError:
    pass

app_logger.info(f"MIP SHARP DISPLAY: {_SENSOR_DISPLAY}")

# https://qiita.com/hishi/items/669ce474fcd76bdce1f1
# LS027B7DH01

# GPIO.BCM
GPIO_DISP = 27  # 13 in GPIO.BOARD
GPIO_SCS = 23  # 16 in GPIO.BOARD
GPIO_VCOMSEL = 17  # 11 in GPIO.BOARD

# update mode
UPDATE_MODE = 0x80


class MipSharpDisplay:
    config = None
    pi = None
    spi = None
    interval = 0.25

    def __init__(self, config):
        self.config = config
        self.init_buffer()

        if not _SENSOR_DISPLAY:
            return

        self.pi = pigpio.pi()
        self.spi = self.pi.spi_open(0, self.config.G_DISPLAY_PARAM["SPI_CLOCK"], 0)

        self.pi.set_mode(GPIO_DISP, pigpio.OUTPUT)
        self.pi.set_mode(GPIO_SCS, pigpio.OUTPUT)
        self.pi.set_mode(GPIO_VCOMSEL, pigpio.OUTPUT)

        self.pi.write(GPIO_SCS, 0)
        self.pi.write(GPIO_DISP, 1)
        self.pi.write(GPIO_VCOMSEL, 1)
        time.sleep(0.1)

        self.update(self.pre_img[:, 2:], direct_update=True)

    def start_coroutine(self):
        self.draw_queue = asyncio.Queue()
        asyncio.create_task(self.draw_worker())

    def init_buffer(self):
        self.buff_width = int(self.config.G_WIDTH / 8) + 2
        self.img_buff_rgb8 = np.zeros(
            (self.config.G_HEIGHT, self.buff_width), dtype="uint8"
        )
        self.pre_img = np.full(
            (self.config.G_HEIGHT, self.buff_width), 255, dtype="uint8"
        )
        self.img_buff_rgb8[:, 0] = UPDATE_MODE
        # address is set in reversed bits
        self.img_buff_rgb8[:, 1] = [
            int("{:08b}".format(a)[::-1], 2) for a in range(self.config.G_HEIGHT)
        ]

    def clear(self):
        self.pi.write(GPIO_SCS, 1)
        time.sleep(0.000006)
        self.pi.spi_write(self.spi, [0b00100000, 0])  # ALL CLEAR MODE
        self.pi.write(GPIO_SCS, 0)
        time.sleep(0.000006)

    def inversion(self, sec):
        if not _SENSOR_DISPLAY:
            return
        s = sec
        state = True
        while s > 0:
            self.pi.write(GPIO_SCS, 1)
            time.sleep(0.000006)
            img_buff = self.img_buff_rgb8.copy()
            if state:
                img_buff[:, 2:] = np.invert(img_buff[:, 2:])
            self.pi.spi_write(self.spi, img_buff.tobytes())
            self.pi.spi_write(self.spi, [0x00000000, 0])
            self.pi.write(GPIO_SCS, 0)
            time.sleep(self.interval)
            s -= self.interval
            state = not state

        time.sleep(0.000006)
        self.pi.write(GPIO_SCS, 1)
        self.pi.spi_write(self.spi, self.img_buff_rgb8.tobytes())
        self.pi.spi_write(self.spi, [0x00000000, 0])
        self.pi.write(GPIO_SCS, 0)

    async def draw_worker(self):
        while True:
            img_bytes = await self.draw_queue.get()
            if img_bytes is None:
                break
            self.pi.write(GPIO_SCS, 1)
            await asyncio.sleep(0.000006)
            if len(img_bytes):
                self.pi.spi_write(self.spi, img_bytes)
            # dummy output for ghost line
            self.pi.spi_write(self.spi, [0x00000000, 0])
            await asyncio.sleep(0.000006)
            self.pi.write(GPIO_SCS, 0)
            self.draw_queue.task_done()

    def update(self, im_array, direct_update):
        if not _SENSOR_DISPLAY or self.config.G_QUIT:
            return

        # self.config.check_time("mip_sharp_update start")
        self.img_buff_rgb8[:, 2:] = ~im_array

        # differential update
        diff_lines = np.where(
            np.sum((self.img_buff_rgb8 == self.pre_img), axis=1) != self.buff_width
        )[0]
        # print("diff ", int(len(diff_lines)/self.config.G_HEIGHT*100), "%")
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
        else:
            asyncio.create_task(
                self.draw_queue.put((self.img_buff_rgb8[diff_lines].tobytes()))
            )

    def quit(self):
        asyncio.create_task(self.draw_queue.put(None))
        self.clear()

        self.pi.write(GPIO_DISP, 1)
        time.sleep(0.01)

        self.pi.spi_close(self.spi)
        self.pi.stop()
