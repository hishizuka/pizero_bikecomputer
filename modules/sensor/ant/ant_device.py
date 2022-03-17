import struct
import time
import datetime

from . import ant_code


class ANT_Device():

  config = None
  node = None
  channel = None
  timeout = 0xFF #0xFF #0: disable high priority search mode, 0xFF: infinite search timeout
  values = None
  ant_state = None
  name = ""
  elements = ()
  stop_cutoff = 60
  structPattern = {
    'ID':struct.Struct('<HB'),
    0x50:struct.Struct('<xxxBHH'),
    0x51:struct.Struct('<xxBBL'),
  }
  common_page_elements = ('hw_ver','manu_id','manu_name','model_num','sw_ver', 'serial_num','battery_status','battery_voltage')
  battery_status = {
    0:"None", 1:"New", 2:"Good", 3:"Ok", 4:"Low", 5:"Critical", 6:"None", 7:"Invalid"
  }
  #detect spike for excluding erroneous value accumulation
  # (speed -> distance, power -> accumulated_power)
  #spike_threshold is defined by "new value - pre value"
  spike_threshold = {
    'speed': 15, #m/s
    'power': 500, #w
    'cadence': 255, #rpm
  }
  ant_idle_interval = {'NORMAL':0.20, 'QUICK':0.01, 'SCAN': 0.20}

  def __init__(self, node=None, config=None, values={}, name=''):
    self.node = node
    self.config = config
    self.name = name
    self.values = values
    self.add_struct_pattern()
    self.init_value()
    
    if node == None: return #for dummy device
    self.make_channel(self.ant_config['channel_type'])
    self.init_extra()
    self.ready_connect()
    self.connect(isCheck=True, isChange=False) #USE: True -> True

  def on_data(self):
    pass

  def add_struct_pattern(self):
    pass

  def init_value(self):
    self.set_null_value()
    self.reset_value()
  
  def init_extra(self):
    pass

  def set_null_value(self):
    for element in self.elements:
      self.values[element] = self.config.G_ANT_NULLVALUE
    self.init_common_page_status()
  
  def init_common_page_status(self):
    for element in self.common_page_elements:
      self.values[element] = self.config.G_ANT_NULLVALUE
    self.values["stored_page"] = {}
    for key in (0x50, 0x51):
      self.values["stored_page"][key] = False

  #reset total value with reset button 
  def reset_value(self):
    pass

  def make_channel(self, c_type, ext_assign=None):
    if self.config.G_ANT['STATUS'] and self.channel == None:
      self.channel = self.node.new_channel(c_type, ext_assign=ext_assign)
      print(self.name, ': channel_num: ', self.channel.id)
      self.channel.on_broadcast_data = self.on_data
      self.channel.on_burst_data = self.on_data
      self.channel.on_acknowledge_data = self.on_data

  def channel_set_id(self): #for slave
    self.channel.set_id(self.config.G_ANT['ID'][self.name], self.ant_config['type'], self.ant_config['transmission_type'])

  def ready_connect(self):
    if self.config.G_ANT['STATUS']:
      self.channel_set_id()
      self.channel.set_period(self.ant_config['interval'][self.config.G_ANT['INTERVAL']])
      self.set_timeout()
      self.channel.set_rf_freq(57)
      self.setup_channel_extra()
  
  def set_timeout(self):
    #for sending acknowledged messages (e.g.: LIGHT)
    # high priority search is off
    # and low priority search is on 
    self.channel.set_search_timeout(0x00)
    self.channel.set_low_priority_search_timeout(self.timeout)
      
  def setup_channel_extra(self):
    #set_channel_tx_power, etc
    pass

  def connect(self, isCheck=True, isChange=False):
    if not self.config.G_ANT['STATUS']: return
    if isCheck:
      if not self.config.G_ANT['USE'][self.name]: return
    if self.stateCheck('OPEN'):
      if isChange: self.config.G_ANT['USE'][self.name] = True
      return
    try:
      self.channel.open()
      if isChange: self.config.G_ANT['USE'][self.name] = True
    except:
      pass
  
  def init_after_connect(self):
    pass

  def disconnect(self, isCheck=True, isChange=False, wait=0):
    if not self.config.G_ANT['STATUS']: return
    if isCheck:
      if not self.config.G_ANT['USE'][self.name]: return
    if self.stateCheck('CLOSE'):
      if isChange: self.config.G_ANT['USE'][self.name] = False
      return
    try:
      self.close_extra()
      self.channel.close()
      time.sleep(wait)
      if isChange: self.config.G_ANT['USE'][self.name] = False
    except:
      pass
  
  def delete(self):
    self.node.delete_channel()

  def stateCheck(self, mode):
    result = self.channel.get_channel_status()
    #Bits 4~7: Channel type, Bits 2~3: Network number, Bits 0~1: Channel State
    #  Channel State: Un-Assigned = 0, Assigned = 1, Searching = 2, Tracking = 3
    channelState = result[2][0] & 0b00000011
    state = False
    if mode == 'OPEN' and channelState != 1: state = True
    elif mode == 'CLOSE' and (channelState == 0 or channelState == 1): state = True
    return state
  
  def close_extra(self):
    pass
  
  def stop(self):
    self.disconnect(self, isCheck=True, isChange=False, wait=0)

  ##############
  # ANT+ pages #
  ##############
  def setCommonPage80(self, data, values):
    (values['hw_ver'], values['manu_id'], values['model_num']) \
      = self.structPattern[0x50].unpack(data[0:8])
    if values['manu_id'] in ant_code.AntCode.MANUFACTURER:
      values['manu_name'] = ant_code.AntCode.MANUFACTURER[values['manu_id']]
    values["stored_page"][0x50] = True

  def setCommonPage81(self, data, values):
    (sw1, sw2, values['serial_num']) = self.structPattern[0x51].unpack(data[0:8])
    if sw1 != 0xFF:
      values['sw_ver'] = float((sw2 * 100 + sw1) / 1000)
    else:
      values['sw_ver'] = float(sw2 / 10)
    values["stored_page"][0x51] = True

  #data is 2byte only (trim from common page 82 and page 4 of speed or cadence only sensor)
  def setCommonPage82(self, data, values):
    values['battery_status'] = self.battery_status[(data[1] >> 4) & 0b111]
    values['battery_voltage'] = round(float(data[1] & 0b1111) + data[0]/256, 2)
  
  def print_spike(self, device_str, val, pre_val, delta, delta_t):
    print(
      "ANT+ {0} spike: ".format(device_str),
      datetime.datetime.now().strftime("%Y%m%d %H:%M:%S"), 
      "value:{0:.0f}, pre:{1:.0f}".format(val, pre_val),
      "delta:", delta, 
      "delta_t:", delta_t,
      )

  def set_wait(self, interval):
    self.node.ant.set_wait(interval)
  
  #ant_idle_interval = {'NORMAL':0.20, 'QUICK':0.01, 'SCAN': 0.20}
  def set_wait_normal_mode(self):
    self.set_wait(self.ant_idle_interval['NORMAL'])

  def set_wait_quick_mode(self):
    self.set_wait(self.ant_idle_interval['QUICK'])

  def set_wait_scan_mode(self):
    self.set_wait(self.ant_idle_interval['SCAN'])
