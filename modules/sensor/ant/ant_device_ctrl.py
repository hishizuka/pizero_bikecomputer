import struct
import array

from . import ant_device


class ANT_Device_CTRL(ant_device.ANT_Device):

  ant_config = {
    'interval':(8192, 16384, 16384), #8192, 16384, 32768
    'type':0x10,
    'transmission_type':0x05,
    'channel_type':0x10, #Channel.Type.BIDIRECTIONAL_TRANSMIT,
    'master_id': 123,
    }
  elements = ('ctrl_cmd','slave_id')
  send_data = False
  data_page_02 = array.array("B", [0x02,0x00,0x00,0x00,0x00,0x00,0x00,0x10])
  pickle_key = "ant+_ctrl_values"

  def channel_set_id(self): #for master
    self.channel.set_id(self.ant_config['master_id'], self.ant_config['type'], self.ant_config['transmission_type'])

  def init_extra(self):
    self.channel.on_broadcast_tx_data = self.on_tx_data
    self.channel.send_broadcast_data(self.data_page_02)
  
  def on_tx_data(self, data):
    if self.send_data:
      self.channel.send_broadcast_data(self.data_page_02)

  def addStructPattern(self):
    self.structPattern[self.name] = struct.Struct('<xxxxxxH')

  def on_data(self, data):
    (self.values['ctrl_cmd'],) = self.structPattern[self.name].unpack(data[0:8])
    if self.values['ctrl_cmd'] == 0x0024: #lap
      self.config.press_button('Edge_Remote', 'LAP', 0)
    elif self.values['ctrl_cmd'] == 0x0001: #page
      self.config.press_button('Edge_Remote', 'PAGE', 0)
    elif self.values['ctrl_cmd'] == 0x0000: #page(long press)
      self.config.press_button('Edge_Remote', 'PAGE', 1)
    elif self.values['ctrl_cmd'] == 0x8000: #custom
      self.config.press_button('Edge_Remote', 'CUSTOM', 0)
      #self.config.logger.sensor.sensor_ant.set_light_mode("ON_OFF_FLASH_LOW")
    elif self.values['ctrl_cmd'] == 0x8001: #custom(long press)
      self.config.press_button('Edge_Remote', 'CUSTOM', 1)
