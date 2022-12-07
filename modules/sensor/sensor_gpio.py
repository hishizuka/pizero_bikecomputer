import time

from .sensor import Sensor


#GPIO Button
_SENSOR_RPiGPIO = False
try:
  import RPi.GPIO as GPIO
  _SENSOR_RPiGPIO = True
except:
  pass

if _SENSOR_RPiGPIO:
  print('GPIO ', end='')


class SensorGPIO(Sensor):

  buttonState = {}
  oldButtonState = {}
  interval = 0.01
  interval_inv = int(1/interval)
  mode = 'MAIN'

  def sensor_init(self):
    if _SENSOR_RPiGPIO and self.config.G_DISPLAY in ['PiTFT', 'Papirus', 'DFRobot_RPi_Display']:
      for key in self.config.button_config.G_BUTTON_DEF[self.config.G_DISPLAY]['MAIN'].keys():
        self.buttonState[key] = False
        self.oldButtonState[key] = True
        if self.config.G_DISPLAY in ['PiTFT', 'DFRobot_RPi_Display']:
          GPIO.setup(key, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        elif self.config.G_DISPLAY in ['Papirus']:
          GPIO.setup(key, GPIO.IN)

  def my_callback(self, channel):
    sw_counter = 0

    while True:
      sw_status = GPIO.input(channel)

      if sw_status == 0:
        sw_counter = sw_counter + 1
        if sw_counter >= self.config.button_config.G_BUTTON_LONG_PRESS * self.interval_inv:
          self.config.press_button(self.config.G_DISPLAY, channel, 1) #long press
          break
      else:
        self.config.press_button(self.config.G_DISPLAY, channel, 0)
        break
      time.sleep(self.interval)

  def update(self):
    if _SENSOR_RPiGPIO and self.config.G_DISPLAY in ['PiTFT', 'Papirus', 'DFRobot_RPi_Display']:
      for key in self.config.button_config.G_BUTTON_DEF[self.config.G_DISPLAY]['MAIN'].keys():
        GPIO.add_event_detect(key, GPIO.FALLING, callback=self.my_callback, bouncetime=500)

  def quit(self):
    if _SENSOR_RPiGPIO:
      GPIO.cleanup()

