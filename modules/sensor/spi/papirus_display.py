import time
import datetime


_SENSOR_DISPLAY = False
try:
  import RPi.GPIO as GPIO
  from papirus import Papirus
  _SENSOR_DISPLAY = True
except:
  pass
print('  PAPIRUS E-INK DISPLAY : ',_SENSOR_DISPLAY)

#SCREEN
SCREEN_WIDTH = 264
SCREEN_HEIGHT = 176


class PapirusDisplay():

  config = None
  papirus = None

  def __init__(self, config):
    
    self.config = config

    if _SENSOR_DISPLAY:
      self.papirus = Papirus(rotation=180)
      self.clear()
  
  def clear(self):
    self.papirus.clear()
  
  def update(self, image):
    self.papirus.display(image)
    self.papirus.fast_update()

  def quit(self):
    if _SENSOR_DISPLAY:
      self.clear()


