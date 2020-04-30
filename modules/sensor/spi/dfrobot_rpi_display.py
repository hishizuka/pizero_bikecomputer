import time

import numpy as np

_SENSOR_DISPLAY = False
try:
  from PIL import Image
  from DFRobot_RPi_Display.devices.dfrobot_epaper import DFRobot_Epaper_SPI
  _SENSOR_DISPLAY = True
except:
  pass
print('  DFRobot RPi Display : ',_SENSOR_DISPLAY)

#SCREEN
SCREEN_WIDTH = 255
SCREEN_HEIGHT = 122 # or 128

RASPBERRY_SPI_BUS = 0
RASPBERRY_SPI_DEV = 0
RASPBERRY_PIN_CS = 27
RASPBERRY_PIN_CD = 17
RASPBERRY_PIN_BUSY = 4


#e-ink Display Module for Raspberry Pi 4B/3B+/Zero W version 1.0
#work in progress

class DFRobotRPiDisplay():

  config = None
  epaper = None

  def __init__(self, config):
    
    self.config = config

    if _SENSOR_DISPLAY:
      self.epaper = DFRobot_Epaper_SPI(
        RASPBERRY_SPI_BUS, 
        RASPBERRY_SPI_DEV, 
        RASPBERRY_PIN_CS, 
        RASPBERRY_PIN_CD, 
        RASPBERRY_PIN_BUSY
        )
      self.epaper.begin()
      self.clear()
  
  def clear(self):
    self.epaper.clear(self.epaper.WHITE)
    self.epaper.flush(self.epaper.FULL)
  
  #work in progress
  def update(self, image):
    self.epaper.bitmap(
      0, 0, #start X and Y
      np.packbits(np.array(Image.open(image).convert('1')), axis=1).flatten(),
      #np.packbits(np.array(Image.open(image).convert('1', dither=Image.FLOYDSTEINBERG)), axis=1).flatten(),
      SCREEN_WIDTH, SCREEN_HEIGHT, #screen size
      65535, 0, #background color(white), drawing color(black)
      )
    self.epaper.flush(self.epaper.PART)

  def quit(self):
    if _SENSOR_DISPLAY:
      self.clear()


