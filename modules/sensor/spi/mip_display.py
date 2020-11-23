import time
#import datetime

import numpy as np


_SENSOR_DISPLAY = False
try:
  import pigpio
  _SENSOR_DISPLAY = True
except:
  pass
print('  MIP DISPLAY : ',_SENSOR_DISPLAY)

# https://qiita.com/hishi/items/669ce474fcd76bdce1f1

#GPIO.BCM
GPIO_DISP = 27 #13 in GPIO.BOARD
GPIO_SCS = 22 #15 in GPIO.BOARD
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
  brightness_index = 0
  brightness_table = [0,10,100]

  def __init__(self, config):
    
    self.config = config

    if not _SENSOR_DISPLAY:
      return

    self.pi = pigpio.pi()
    self.spi = self.pi.spi_open(0, 2000000, 0)
    #self.spi = self.pi.spi_open(0, 5500000, 0) #overclocking
    time.sleep(0.1)     #Wait
    
    self.pi.set_mode(GPIO_DISP, pigpio.OUTPUT)
    self.pi.set_mode(GPIO_SCS, pigpio.OUTPUT)
    self.pi.set_mode(GPIO_VCOMSEL, pigpio.OUTPUT)

    self.pi.write(GPIO_SCS, 0)
    self.pi.write(GPIO_DISP, 1)
    self.pi.write(GPIO_VCOMSEL, 1)
    time.sleep(0.1)

    self.pi.set_mode(GPIO_BACKLIGHT, pigpio.OUTPUT)
    self.pi.hardware_PWM(GPIO_BACKLIGHT, GPIO_BACKLIGHT_FREQ, 0)

    if self.config.G_USE_AUTO_BACKLIGHT:
      self.brightness_index = len(self.brightness_table)
    else:
      self.brightness_index = 0

    self.buff_width = int(self.config.G_WIDTH*3/8)+2 #for 3bit update mode
    self.img_buff_rgb8 = np.empty((self.config.G_HEIGHT,self.buff_width), dtype='uint8')
    self.pre_img = np.zeros((self.config.G_HEIGHT,self.buff_width), dtype='uint8')
    self.img_buff_rgb8[:,0] = UPDATE_MODE
    self.img_buff_rgb8[:,1] = np.arange(self.config.G_HEIGHT)
    if self.config.G_HEIGHT > 255: 
      #self.img_buff_rgb8[:,0] = self.img_buff_rgb8[:,0] + (img_buff_rgb8[:,1] >> 8)
      self.img_buff_rgb8[:,0] = self.img_buff_rgb8[:,0] + (np.arange(self.config.G_HEIGHT) >> 8)
    
    #self.clear()
  
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

  def update(self, image):

    im_array = np.array(image)

    #t = datetime.datetime.now()
    
    #3bit mode update
    self.img_buff_rgb8[:,2:] = np.packbits(
      ((im_array > 128).astype('uint8')).reshape(self.config.G_HEIGHT, self.config.G_WIDTH*3),
      axis=1
      )

    #differential update
    rewrite_flag = True
    diff_lines = np.where(np.sum((self.img_buff_rgb8 == self.pre_img), axis=1) != self.buff_width)[0] 
    #print("diff ", int(len(diff_lines)/self.config.G_HEIGHT*100), "%")
    #print(" ")
    img_bytes = self.img_buff_rgb8[diff_lines].tobytes()
    if len(diff_lines) == 0:
      rewrite_flag = False
    self.pre_img[diff_lines] = self.img_buff_rgb8[diff_lines]

    #print("Loading images... :", (datetime.datetime.now()-t).total_seconds(),"sec")
    #t = datetime.datetime.now()
    
    if _SENSOR_DISPLAY and rewrite_flag and not self.config.G_QUIT:
      self.pi.write(GPIO_SCS, 1)
      time.sleep(0.000006)
      if len(img_bytes) > 0:
        self.pi.spi_write(self.spi, img_bytes)
      #dummy output for ghost line
      self.pi.spi_write(self.spi, [0x00000000,0])
      self.pi.write(GPIO_SCS, 0)

    #print("Drawing images... :", (datetime.datetime.now()-t).total_seconds(),"sec")

  def change_brightness(self):
    
    #brightness is changing as followings,
    # [self.brightness_table(0, b1, b2, ..., bmax), G_USE_AUTO_BACKLIGHT]
    self.brightness_index = (self.brightness_index+1)%(len(self.brightness_table)+1)

    if self.brightness_index == len(self.brightness_table):
      self.config.G_USE_AUTO_BACKLIGHT = True
    else:
      self.config.G_USE_AUTO_BACKLIGHT = False
      b = self.brightness_table[self.brightness_index]
      self.set_brightness(b)
  
  def set_brightness(self, b):
    if not _SENSOR_DISPLAY:
      return
    self.pi.hardware_PWM(GPIO_BACKLIGHT, GPIO_BACKLIGHT_FREQ, b*10000)

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
    self.clear()
    self.pi.write(GPIO_DISP, 1)
    time.sleep(0.1)

    self.pi.spi_close(self.spi)
    self.pi.stop()

