import time
#import datetime
import asyncio
import numpy as np


_SENSOR_DISPLAY = False
MODE="Python"
try:
  import pigpio
  _SENSOR_DISPLAY = True
  import pyximport; pyximport.install()
  from .cython.mip_helper import conv_3bit_color, MipDisplay_CPP
  MODE = "Cython"
  #MODE = "Cython_full" #cannot use with asyncio
except:
  pass
print('  MIP DISPLAY : ',_SENSOR_DISPLAY)


# https://qiita.com/hishi/items/669ce474fcd76bdce1f1
# LPM027M128C, LPM027M128B, 

#GPIO.BCM
GPIO_DISP = 27 #13 in GPIO.BOARD
GPIO_SCS = 23 #16 in GPIO.BOARD
#GPIO_SCS = 22 #15 in GPIO BOARD
GPIO_VCOMSEL = 17 #11 in GPIO.BOARD
GPIO_BACKLIGHT = 18 #12 in GPIO.BOARD with hardware PWM in pigpio

#update mode
# https://www.j-display.com/product/pdf/Datasheet/3LPM027M128C_specification_ver02.pdf
#0x90 4bit update mode
#0x80 3bit update mode (fast)
#0x88 1bit update mode (most fast, but 2-color)
UPDATE_MODE = 0x80

#BACKLIGHT frequency
GPIO_BACKLIGHT_FREQ = 64

class MipDisplay():

  config = None
  pi = None
  spi = None
  interval = 0.25
  spi_clock = 2000000 #normal
  #spi_clock = 5000000 #overclocking
  brightness_index = 0
  brightness_table = [0,10,100]
  brightness = 0
  mip_display_cpp = None

  def __init__(self, config):
    self.config = config
    
    if not _SENSOR_DISPLAY:
      return

    if MODE == "Cython":
      self.conv_color = conv_3bit_color
    elif MODE == "Cython_full": 
      self.mip_display_cpp = MipDisplay_CPP(self.spi_clock)
      self.mip_display_cpp.set_screen_size(self.config.G_WIDTH, self.config.G_HEIGHT)
      self.update = self.mip_display_cpp.update
      self.set_brightness = self.mip_display_cpp.set_brightness
      self.inversion = self.mip_display_cpp.inversion
      self.quit = self.mip_display_cpp.quit
      return
    else:
      self.conv_color = self.conv_3bit_color_py
    
    self.init_buffer()

    #spi
    self.pi = pigpio.pi()
    self.spi = self.pi.spi_open(0, self.spi_clock, 0)
    
    self.pi.set_mode(GPIO_DISP, pigpio.OUTPUT)
    self.pi.set_mode(GPIO_SCS, pigpio.OUTPUT)
    self.pi.set_mode(GPIO_VCOMSEL, pigpio.OUTPUT)

    self.pi.write(GPIO_SCS, 0)
    self.pi.write(GPIO_DISP, 1)
    self.pi.write(GPIO_VCOMSEL, 1)
    time.sleep(0.01)

    #backlight
    self.pi.set_mode(GPIO_BACKLIGHT, pigpio.OUTPUT)
    self.pi.hardware_PWM(GPIO_BACKLIGHT, GPIO_BACKLIGHT_FREQ, 0)
    if self.config.G_USE_AUTO_BACKLIGHT:
      self.brightness_index = len(self.brightness_table)
    else:
      self.brightness_index = 0

  def init_buffer(self):
    self.buff_width = int(self.config.G_WIDTH*3/8)+2 #for 3bit update mode
    self.img_buff_rgb8 = np.empty((self.config.G_HEIGHT,self.buff_width), dtype='uint8')
    self.pre_img = np.zeros((self.config.G_HEIGHT,self.buff_width), dtype='uint8')
    self.img_buff_rgb8[:,0] = UPDATE_MODE
    self.img_buff_rgb8[:,1] = np.arange(self.config.G_HEIGHT)
    #for MIP_640
    self.img_buff_rgb8[:,0] = self.img_buff_rgb8[:,0] + (np.arange(self.config.G_HEIGHT) >> 8)
  
  def start_coroutine(self):
    self.draw_queue = asyncio.Queue()
    asyncio.create_task(self.draw_worker())

  def clear(self):
    self.pi.write(GPIO_SCS, 1)
    time.sleep(0.000006)
    self.pi.spi_write(self.spi, [0b00100000,0]) # ALL CLEAR MODE
    self.pi.write(GPIO_SCS, 0)
    time.sleep(0.000006)
    self.set_brightness(0)
  
  def no_update(self):
    self.pi.write(GPIO_SCS, 1)
    time.sleep(0.000006)
    self.pi.spi_write(self.spi, [0b00000000,0]) # NO UPDATE MODE
    self.pi.write(GPIO_SCS, 0)
    time.sleep(0.000006)

  def blink(self, sec):
    if not _SENSOR_DISPLAY:
      return
    s = sec
    state = True
    while s > 0:
      self.pi.write(GPIO_SCS, 1)
      time.sleep(0.000006)
      if state:
        self.pi.spi_write(self.spi, [0b00010000,0]) # BLINK(BLACK) MODE
      else:
        self.pi.spi_write(self.spi, [0b00011000,0]) # BLINK(WHITE) MODE
      self.pi.write(GPIO_SCS, 0)
      time.sleep(self.interval)
      s -= self.interval
      state = not state
    self.no_update()

  def inversion(self, sec):
    if not _SENSOR_DISPLAY:
      return
    s = sec
    state = True
    while s > 0:
      self.pi.write(GPIO_SCS, 1)
      time.sleep(0.000006)
      if state:
        self.pi.spi_write(self.spi, [0b00010100,0]) # INVERSION MODE
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
      if img_bytes == None:
        break
      #self.config.check_time("mip_draw_worker start")
      #t = datetime.datetime.now()
      self.pi.write(GPIO_SCS, 1)
      await asyncio.sleep(0.000006)
      self.pi.spi_write(self.spi, img_bytes)
      #dummy output for ghost line
      self.pi.spi_write(self.spi, [0x00000000,0])
      await asyncio.sleep(0.000006)
      self.pi.write(GPIO_SCS, 0)
      #self.config.check_time("mip_draw_worker end")
      #print("####### draw(Py)", (datetime.datetime.now()-t).total_seconds())
      self.draw_queue.task_done()

  def update(self, im_array, direct_update):
    if not _SENSOR_DISPLAY or self.config.G_QUIT:
      return

    #self.config.check_time("mip_update start")
    self.img_buff_rgb8[:,2:] = self.conv_color(im_array)
    #self.config.check_time("packbits")
   
    #differential update
    diff_lines = np.where(np.sum((self.img_buff_rgb8 == self.pre_img), axis=1) != self.buff_width)[0]
    #print("diff ", int(len(diff_lines)/self.config.G_HEIGHT*100), "%")
    #print(" ")
    
    if len(diff_lines) == 0:
      return
    self.pre_img[diff_lines] = self.img_buff_rgb8[diff_lines]
    #self.config.check_time("diff_lines")
      
    if direct_update:
      self.pi.write(GPIO_SCS, 1)
      time.sleep(0.000006)
      self.pi.spi_write(self.spi, self.img_buff_rgb8[diff_lines].tobytes())
      time.sleep(0.000006)
      self.pi.write(GPIO_SCS, 0)
    #put queue
    elif len(diff_lines) < 270:
      #await self.draw_queue.put((self.img_buff_rgb8[diff_lines].tobytes()))
      asyncio.create_task(self.draw_queue.put((self.img_buff_rgb8[diff_lines].tobytes())))
    else:
      #for MIP 640x480
      l = int(len(diff_lines)/2)
      #await self.draw_queue.put((self.img_buff_rgb8[diff_lines[0:l]].tobytes()))
      #await self.draw_queue.put((self.img_buff_rgb8[diff_lines[l:]].tobytes()))
      asyncio.create_task(self.draw_queue.put((self.img_buff_rgb8[diff_lines[0:l]].tobytes())))
      asyncio.create_task(self.draw_queue.put((self.img_buff_rgb8[diff_lines[l:]].tobytes())))

  def conv_2bit_color_py(self, im_array):
    return np.packbits(
      (im_array >= 128).reshape(self.config.G_HEIGHT, self.config.G_WIDTH*3),
      axis=1
    )

  def conv_3bit_color_py(self, im_array):
    #pseudo 3bit color (128~216: simple dithering)
    #set even pixel and odd pixel to 0   
    #1. convert 2bit color
    im_array_bin = (im_array >= 128)
    #2. set even pixel (2n, 2n) to 0
    im_array_bin[0::2, 0::2, :][im_array[0::2, 0::2, :] <= 216] = 0
    #3. set odd pixel (2n+1, 2n+1) to 0
    im_array_bin[1::2, 1::2, :][im_array[1::2, 1::2, :] <= 216] = 0

    return np.packbits(
      im_array_bin.reshape(self.config.G_HEIGHT, self.config.G_WIDTH*3),
      axis=1
    )

  def change_brightness(self):
    
    #brightness is changing as following,
    # [self.brightness_table(0, b1, b2, ..., bmax), self.display.G_USE_AUTO_BACKLIGHT]
    self.brightness_index = (self.brightness_index+1)%(len(self.brightness_table)+1)

    if self.brightness_index == len(self.brightness_table):
      self.config.G_USE_AUTO_BACKLIGHT = True
    else:
      self.config.G_USE_AUTO_BACKLIGHT = False
      b = self.brightness_table[self.brightness_index]
      self.set_brightness(b)
  
  def set_brightness(self, b):
    if not _SENSOR_DISPLAY or b == self.brightness:
      return
    self.pi.hardware_PWM(GPIO_BACKLIGHT, GPIO_BACKLIGHT_FREQ, b*10000)
    self.brightness = b

  def backlight_blink(self):
    if not _SENSOR_DISPLAY:
      return
    for x in range(2):
      for pw in range(0,100,1):
        self.pi.hardware_PWM(GPIO_BACKLIGHT, GPIO_BACKLIGHT_FREQ, pw*10000)
        time.sleep(0.05)
      for pw in range(100,0,-1):
        self.pi.hardware_PWM(GPIO_BACKLIGHT, GPIO_BACKLIGHT_FREQ, pw*10000)
        time.sleep(0.05)

  def quit(self):
    if not _SENSOR_DISPLAY:
      return
    
    asyncio.create_task(self.draw_queue.put(None))
    self.set_brightness(0)
    self.clear()

    self.pi.write(GPIO_DISP, 1)
    time.sleep(0.01)
    
    self.pi.spi_close(self.spi)
    self.pi.stop()

