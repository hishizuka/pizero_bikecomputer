import time
#import datetime

import numpy as np


_SENSOR_DISPLAY = False
try:
  import RPi.GPIO as GPIO
  import pigpio
  import spidev
  _SENSOR_DISPLAY = True
except:
  pass
print('  MIP DISPLAY : ',_SENSOR_DISPLAY)

# https://qiita.com/hishi/items/669ce474fcd76bdce1f1

#GPIO.BCM
GPIO_CHANNEL = 0
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

#SCREEN
SCREEN_WIDTH = 400
SCREEN_HEIGHT = 240

#BACKLIGHT frequency
GPIO_BACKLIGHT_FREQ = 64

class MipDisplay():

  config = None
  spi = None
  interval = 0.25
  pre_img = np.array([])
  buff_width = int(SCREEN_WIDTH*3/8)+2 #for 3bit update mode
  brightness_index = 0
  brightness_table = [0,10,100]

  def __init__(self, config):
    
    self.config = config

    if not _SENSOR_DISPLAY:
      return

    self.spi = spidev.SpiDev()
    self.spi.open(0, 0)
    self.spi.mode = 0b00 #SPI MODE0
    self.spi.max_speed_hz = 2000000 #MAX 2MHz
    #self.spi.max_speed_hz = 7000000 #overclocking
    self.spi.no_cs 
    time.sleep(0.1)     #Wait
     
    GPIO.setup(GPIO_DISP, GPIO.OUT)
    GPIO.setup(GPIO_SCS, GPIO.OUT)
    GPIO.setup(GPIO_VCOMSEL, GPIO.OUT)
     
    GPIO.output(GPIO_SCS, 0) #1st=L
    GPIO.output(GPIO_DISP, 1) #1st=Display On
    #GPIO.output(GPIO_DISP, 0) #1st=No Display
    #GPIO.output(GPIO_VCOMSEL, 0) #L=VCOM(1Hz)
    GPIO.output(GPIO_VCOMSEL, 1) #H=VCOM(64Hz)
    time.sleep(0.1)

    self.pig = pigpio.pi()
    self.pig.set_mode(GPIO_BACKLIGHT, pigpio.OUTPUT)
    self.pig.hardware_PWM(GPIO_BACKLIGHT, GPIO_BACKLIGHT_FREQ, 0)

    if self.config.G_USE_AUTO_BACKLIGHT:
      self.brightness_index = len(self.brightness_table)
    else:
      self.brightness_index = 0

    self.clear()
  
  def clear(self):
    GPIO.output(GPIO_SCS, 1)
    time.sleep(0.000006)
    self.spi.xfer2([0x20,0]) # ALL CLEAR MODE
    GPIO.output(GPIO_SCS, 0)
    time.sleep(0.000006)
    self.set_brightness(0)
  
  def no_update(self):
    GPIO.output(GPIO_SCS, 1)
    time.sleep(0.000006)
    self.spi.xfer2([0b00000000,0]) # NO UPDATE MODE
    GPIO.output(GPIO_SCS, 0)
    time.sleep(0.000006)

  def blink(self, sec):
    if not _SENSOR_DISPLAY:
      return
    s = sec
    state = True
    while s > 0:
      GPIO.output(GPIO_SCS, 1)
      time.sleep(0.000006)
      if state:
        self.spi.xfer2([0b00010000,0]) # BLINK(BLACK) MODE
      else:
        self.spi.xfer2([0b00011000,0]) # BLINK(WHITE) MODE
      GPIO.output(GPIO_SCS, 0)
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
      GPIO.output(GPIO_SCS, 1)
      time.sleep(0.000006)
      if state:
        self.spi.xfer2([0b00010100,0]) # INVERSION MODE
      else:
        self.no_update()
      GPIO.output(GPIO_SCS, 0)
      time.sleep(self.interval)
      s -= self.interval
      state = not state
    self.no_update()

  def update(self, image):

    im_array = np.array(image)

    #t = datetime.datetime.now()
    
    #3bit mode update
    im_array = ((im_array > 128).astype('uint8')).reshape(SCREEN_HEIGHT,SCREEN_WIDTH*3)
    img_buff_rgb8 = np.empty((SCREEN_HEIGHT,int(SCREEN_WIDTH*3/8)+2), dtype='uint8')
    img_bytes = bytearray()

    img_buff_rgb8[:,0] = 0x80
    img_buff_rgb8[:,1] = range(SCREEN_HEIGHT)
    img_buff_rgb8[:,2:] = np.packbits(im_array, axis=1)

    #differential update
    rewrite_flag = True
    if self.pre_img.size == 0:
      img_bytes = img_buff_rgb8.tobytes()
    else:
      diff_lines = np.where(np.sum((img_buff_rgb8 == self.pre_img), axis=1) != self.buff_width)[0] 
      #print("diff ", int(len(diff_lines)/SCREEN_HEIGHT*100), "%")
      #print(" ")
      img_bytes = img_buff_rgb8[diff_lines].tobytes()
      if len(diff_lines) == 0:
        rewrite_flag = False
    self.pre_img = img_buff_rgb8

    #print("Loading images... :", (datetime.datetime.now()-t).total_seconds(),"sec")
    #t = datetime.datetime.now()
    
    if _SENSOR_DISPLAY and rewrite_flag and not self.config.G_QUIT:
      GPIO.output(GPIO_SCS, 1)
      time.sleep(0.000006)
      if len(img_bytes) > 0:
        self.spi.xfer3(img_bytes)
      #dummy output for ghost line
      self.spi.xfer2([0x00000000,0])
      GPIO.output(GPIO_SCS, 0)

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
    self.pig.hardware_PWM(GPIO_BACKLIGHT, GPIO_BACKLIGHT_FREQ, b*10000)

  def backlight_blink(self):
    if not _SENSOR_DISPLAY:
      return
    for x in range(2):
      for pw in range(0,100,1):
        self.pig.hardware_PWM(GPIO_BACKLIGHT, GPIO_BACKLIGHT_FREQ, pw*10000)
        time.sleep(0.05)
      for pw in range(100,0,-1):
        self.pig.hardware_PWM(GPIO_BACKLIGHT, GPIO_BACKLIGHT_FREQ, pw*10000)
        time.sleep(0.05)

  def quit(self):
    if not _SENSOR_DISPLAY:
      return
    self.clear()
    self.pig.stop()
    self.spi.close()
    GPIO.output(GPIO_DISP, 1)



