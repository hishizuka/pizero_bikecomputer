import time

from .sensor import Sensor


#GPIO Button
_SENSOR_RPiGPIO = False
try:
  import RPi.GPIO as GPIO
  _SENSOR_RPiGPIO = True
except:
  pass
print('  RPi GPIO : ',_SENSOR_RPiGPIO)


class SensorGPIO(Sensor):

  buttonState = {}
  oldButtonState = {}
  interval = 0.01
  interval_inv = int(1/interval)

  def sensor_init(self):
    if _SENSOR_RPiGPIO and self.config.G_DISPLAY in ['PiTFT', 'Papirus', 'DFRobot_RPi_Display']:
      for key in self.config.G_GPIO_BUTTON_DEF[self.config.G_DISPLAY]['MAIN'].keys():
        self.buttonState[key] = False
        self.oldButtonState[key] = True
        if self.config.G_DISPLAY == 'PiTFT':
          GPIO.setup(key, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        elif self.config.G_DISPLAY in ['Papirus', 'DFRobot_RPi_Display']:
          GPIO.setup(key, GPIO.IN)

  def my_callback(self, channel):
    sw_counter = 0
    s = self.config.gui.stack_widget
    b = self.config.G_GPIO_BUTTON_DEF[self.config.G_DISPLAY]
    t = self.config.G_BUTTON_LONG_PRESS * self.interval_inv

    while True:
      sw_status = GPIO.input(channel)

      i = s.currentIndex()
      m = 'MAIN'
      if i == 1:
        m = 'MAIN'
      elif i >= 0:
        m = 'MENU'

      if sw_status == 0:
        sw_counter = sw_counter + 1
        if sw_counter >= self.config.G_BUTTON_LONG_PRESS * self.interval_inv:
          eval('self.config.gui.'+b[m][channel][1])
          break
      else:
        eval('self.config.gui.'+b[m][channel][0])
        break
      time.sleep(self.interval)

  def update(self):
    #if SENSOR_RPiGPIO:
    if _SENSOR_RPiGPIO and self.config.G_DISPLAY in ['PiTFT', 'Papirus', 'DFRobot_RPi_Display']:
      for key in self.config.G_GPIO_BUTTON_DEF[self.config.G_DISPLAY]['MAIN'].keys():
        GPIO.add_event_detect(key, GPIO.FALLING, callback=self.my_callback, bouncetime=500)

  def quit(self):
    #move to config
    pass

