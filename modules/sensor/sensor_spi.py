from .sensor import Sensor
import numpy as np
from PIL import Image


class SensorSPI(Sensor):

  sensor = {}
  elements = ()
  display = None
  send_display = False

  def sensor_init(self):
    self.reset()

    if not self.config.G_IS_RASPI:
      return
    
    if self.config.G_DISPLAY == 'PiTFT':
      try:
        from .spi.pitft_28_r import PiTFT28r
        self.display = PiTFT28r(self.config)
      except:
        pass
    elif self.config.G_DISPLAY == 'MIP':
      try:
        from .spi.mip_display import MipDisplay
        self.display = MipDisplay(self.config)
        self.send_display = True
      except:
        pass
    elif self.config.G_DISPLAY == 'MIP_Sharp':
      #try:
      from .spi.mip_sharp_display import MipSharpDisplay
      self.display = MipSharpDisplay(self.config)
      self.send_display = True
      #except:
      #  pass
    elif self.config.G_DISPLAY == 'Papirus':
      try:
        from .spi.papirus_display import PapirusDisplay
        self.display = PapirusDisplay(self.config)
        self.send_display = True
      except:
        pass
    elif self.config.G_DISPLAY == 'DFRobot_RPi_Display':
      try:
        from .spi.dfrobot_rpi_display import DFRobotRPiDisplay
        self.display = DFRobotRPiDisplay(self.config)
        self.send_display = True
      except:
        pass

  def quit(self):
    if not self.config.G_IS_RASPI:
      return
    if self.config.G_DISPLAY == 'PiTFT':
      pass
    elif self.config.G_DISPLAY in ['MIP', 'MIP_Sharp', 'Papirus', 'DFRobot_RPi_Display'] and self.send_display:
      self.display.quit()
    
  def update(self, buf):
    if not self.config.G_IS_RASPI:
      return

    if self.config.G_DISPLAY == 'PiTFT':
      pass
    elif self.config.G_DISPLAY in ['MIP', 'MIP_Sharp', 'Papirus',] and self.send_display:
      self.display.update(Image.open(buf))
    elif self.config.G_DISPLAY in ['DFRobot_RPi_Display'] and self.send_display:
      self.display.update(buf)

  def screen_flash_long(self):
    if self.config.G_DISPLAY in ['MIP','MIP_Sharp'] and self.send_display:
      self.display.inversion(0.8)
      #self.display.blink(1.0)

  def screen_flash_short(self):
    if self.config.G_DISPLAY in ['MIP','MIP_Sharp'] and self.send_display:
      self.display.inversion(0.3)

  def brightness_control(self):
    if not self.config.G_IS_RASPI:
      return
    if self.config.G_DISPLAY == 'PiTFT':
      self.display.change_brightness()
    elif self.config.G_DISPLAY == 'MIP' and self.send_display:
      self.display.change_brightness()


