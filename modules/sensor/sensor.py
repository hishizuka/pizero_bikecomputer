class Sensor():
  config = None
  values = None

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
