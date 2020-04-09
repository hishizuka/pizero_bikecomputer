import time
import datetime

class Sensor():
  config = None
  values = None

  #for timer
  start_time = None
  wait_time = 1.0
  actual_loop_interval = None

  def __init__(self, config, values):
    self.config = config
    self.values = values
    self.sensor_init()

  def sensor_init(self):
    pass

  def update(self):
    pass

  def get(self):
    pass
    
  def reset(self):
    pass

  def sleep(self):
    time.sleep(self.wait_time)
    self.start_time = datetime.datetime.now()

  def get_sleep_time(self, interval):
    loop_time = (datetime.datetime.now() - self.start_time).total_seconds()
    d1, d2 = divmod(loop_time, interval)
    if d1 > interval * 10: #[s]
      print(loop_time, d1, d2)
      d1 = d2 = 0
    self.wait_time = interval - d2
    self.actual_loop_interval = (d1 + 1)*interval
