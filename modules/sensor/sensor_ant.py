import time
import datetime
import random
import math
import os
import sys
import struct

import array
import numpy as np

from .sensor import Sensor
from . import ant_code

#ANT+
_SENSOR_ANT = False
f = open(os.devnull, 'w')
sys.stdout = f
try:
  from ant.easy.node import Node
  from ant.easy.channel import Channel
  from ant.base.commons import format_list
  from ant.base.message import Message
  from ant.base.driver import find_driver
  #device test
  _driver = find_driver()
  _SENSOR_ANT = True
except:
  pass
f.close()
sys.stdout = sys.__stdout__
print("  ANT : ",_SENSOR_ANT)

MATH_PI = math.pi

class SensorANT(Sensor):

  #for openant
  node = None
  NETWORK_KEY= [0xb9, 0xa5, 0x21, 0xfb, 0xbd, 0x72, 0xc3, 0x45]
  NETWORK_NUM = 0x00
  CHANNEL = 0x00
  DEVICE_ALL = 0
  scanner = None
  device = {}

  def sensor_init(self):
   
    if not self.config.G_ANT['STATUS']:
      global _SENSOR_ANT
      _SENSOR_ANT = False

    if _SENSOR_ANT:
      self.node = Node()
      self.node.set_network_key(self.NETWORK_NUM, self.NETWORK_KEY)

    #initialize scan channel (reserve ch0)
    self.scanner = ANT_Device_MultiScan(self.node, self.config)
    self.searcher = ANT_Device_Search(self.node, self.config, self.values)
    self.scanner.setMainAntDevice(self.device)
   
    #auto connect ANT+ sensor from setting.conf
    if _SENSOR_ANT and not self.config.G_DUMMY_OUTPUT:
      for key in self.config.G_ANT['ID'].keys():
        if self.config.G_ANT['USE'][key]:
          antID = self.config.G_ANT['ID'][key]
          antType = self.config.G_ANT['TYPE'][key]
          self.connectAntSensor(key, antID, antType, False)
      return
    #otherwise, initialize
    else:
      for key in self.config.G_ANT['ID'].keys():
        self.config.G_ANT['USE'][key] = False
        self.config.G_ANT['ID'][key] = 0
        self.config.G_ANT['TYPE'][key] = 0

    #for dummy output
    if not _SENSOR_ANT and self.config.G_DUMMY_OUTPUT:
      #need to set dummy ANT+ device id 0
      self.config.G_ANT['USE'] = {
        'HR': True,
        'SPD': True,
        'CDC': True, #same as SPD
        'PWR': True,
      }
      self.config.G_ANT['ID_TYPE'] = { 
        'HR': struct.pack('<HB', 0, 0x78),
        'SPD': struct.pack('<HB', 0, 0x79),
        'CDC': struct.pack('<HB', 0, 0x79), #same as SPD
        'PWR': struct.pack('<HB', 0, 0x0B),
      }
      self.config.G_ANT['TYPE'] =  {
        'HR': 0x78,
        'SPD': 0x79,
        'CDC': 0x79, #same as SPD
        'PWR': 0x0B,
      }
      ac = self.config.G_ANT['ID_TYPE']
      self.values[ac['HR']] = {}
      self.values[ac['SPD']] = {'distance':0}
      self.values[ac['PWR']] = {}
      for key in [0x10,0x11,0x12]:
        self.values[ac['PWR']][key] = {'accumulated_power':0}

    self.reset()

  def start(self):
    if _SENSOR_ANT:
      self.node.start()
 
  def update(self):
    if _SENSOR_ANT or not self.config.G_DUMMY_OUTPUT:
      return
    
    hr_value = random.randint(70,130)
    speed_value = random.randint(5,30)/3.6 #5 - 30km/h [unit:m/s]
    cad_value = random.randint(0,80)
    power_value = random.randint(0,250)
    timestamp = datetime.datetime.now()
    #if 0 < timestamp.second%60 < 10:
    #  hr_value = speed_value = cad_value = power_value = self.config.G_ANT_NULLVALUE
    #if 8 < timestamp.second%60 < 10:
    #  speed_value = cad_value = power_value = 0

    ac = self.config.G_ANT['ID_TYPE']
    self.values[ac['HR']]['hr'] = hr_value
    self.values[ac['SPD']]['speed'] = speed_value
    self.values[ac['CDC']]['cadence'] = cad_value
    self.values[ac['PWR']][0x10]['power'] = power_value

    #TIMESTAMP
    self.values[ac['HR']]['timestamp'] = timestamp
    self.values[ac['SPD']]['timestamp'] = timestamp
    self.values[ac['PWR']][0x10]['timestamp'] = timestamp
    #DISTANCE, TOTAL_WORK
    if self.config.G_MANUAL_STATUS == "START":  
      #DISTANCE: unit: m
      if not np.isnan(self.values[ac['SPD']]['speed']):
        self.values[ac['SPD']]['distance'] += \
          self.values[ac['SPD']]['speed']*self.config.G_SENSOR_INTERVAL
      #TOTAL_WORK: unit: j
      if not np.isnan(self.values[ac['PWR']][0x10]['power']):
        self.values[ac['PWR']][0x10]['accumulated_power'] += \
          self.values[ac['PWR']][0x10]['power']*self.config.G_SENSOR_INTERVAL

  def reset(self):
    for dv in self.device.values():
      dv.resetValue()

  def quit(self):
    if not _SENSOR_ANT:
      return
    self.searcher.set_wait_quick_mode()
    #stop scanner and searcher
    if not self.scanner.stop():
      for dv in self.device.values():
        dv.ant_state = 'quit'
        dv.disconnect(isCheck=True, isChange=False, wait=0) #USE: True -> True
      self.searcher.stopSearch(resetWait=False)
    self.node.stop()

  def connectAntSensor(self, antName, antID, antType, connectStatus):
    if not _SENSOR_ANT:
      return
    self.config.G_ANT['ID'][antName] = antID
    self.config.G_ANT['TYPE'][antName] = antType
    self.config.G_ANT['ID_TYPE'][antName] = struct.pack('<HB', antID, antType)
    antIDType = self.config.G_ANT['ID_TYPE'][antName]
    self.searcher.stopSearch(resetWait=False)
    
    self.config.G_ANT['USE'][antName] = True

    self.searcher.set_wait_normal_mode()

    #existing connection 
    if connectStatus:
      return

    #recconect
    if antIDType in self.device:
      self.device[antIDType].connect(isCheck=False, isChange=False) #USE: True -> True)
      self.device[antIDType].ant_state = 'connectAntSensor'
      return
   
    #newly connect
    self.values[antIDType] = {}
    if antType == 0x78:
      self.device[antIDType] \
        = ANT_Device_HeartRate(self.node, self.config, self.values[antIDType], antName)
    elif antType == 0x79:
      self.device[antIDType] \
        = ANT_Device_Speed_Cadence(self.node, self.config, self.values[antIDType], antName)
    elif antType == 0x7A:
      self.device[antIDType] \
        = ANT_Device_Cadence(self.node, self.config, self.values[antIDType], antName)
    elif antType == 0x7B:
      self.device[antIDType] \
        = ANT_Device_Speed(self.node, self.config, self.values[antIDType], antName)
    elif antType == 0x0B:
      self.device[antIDType] \
        = ANT_Device_Power(self.node, self.config, self.values[antIDType], antName)
    elif antType == 0x23:
      self.device[antIDType] \
        = ANT_Device_Light(self.node, self.config, self.values[antIDType], antName)
    elif antType == 0x10:
      self.device[antIDType] \
        = ANT_Device_CTRL(self.node, self.config, self.values[antIDType], antName)
    self.device[antIDType].ant_state = 'connectAntSensor'

  def disconnectAntSensor(self, antName):
    antIDType = self.config.G_ANT['ID_TYPE'][antName]
    antNames = []
    for k,v in self.config.G_ANT['USE'].items():
      if v and k in self.config.G_ANT['ID_TYPE']:
        if self.config.G_ANT['ID_TYPE'][k] == antIDType:
          antNames.append(k)
    for k in antNames:
      #USE: True -> False
      self.device[self.config.G_ANT['ID_TYPE'][k]].ant_state = 'disconnectAntSensor'
      self.device[self.config.G_ANT['ID_TYPE'][k]].disconnect(isCheck=True, isChange=True)
      self.config.G_ANT['ID_TYPE'][k] = 0
      self.config.G_ANT['ID'][k] = 0
      self.config.G_ANT['TYPE'][k] = 0
      self.config.G_ANT['USE'][k] = False

  def continuousScan(self):
    if not _SENSOR_ANT:
      return
    self.scanner.set_wait_quick_mode()
    for dv in self.device.values():
      dv.ant_state = 'continuousScan'
      dv.disconnect(isCheck=True, isChange=False, wait=0.5) #USE: True -> True
    time.sleep(0.5)
    self.scanner.set_wait_scan_mode()
    self.scanner.scan()

  def stopContinuousScan(self):
    self.scanner.set_wait_quick_mode()
    self.scanner.stopScan()
    antIDTypes = []
    for k,v in self.config.G_ANT['USE'].items():
      if v and not self.config.G_ANT['ID_TYPE'][k] in antIDTypes: 
        antIDTypes.append(self.config.G_ANT['ID_TYPE'][k])
    for antIDType in antIDTypes:
      self.device[antIDType].connect(isCheck=True, isChange=False) #USE: True -> True
    self.scanner.set_wait_normal_mode()
  
  def set_light_mode(self, mode, auto=False):
    if not self.config.G_ANT['USE']['LGT']: return
    if mode == "OFF":
      self.device[self.config.G_ANT['ID_TYPE']['LGT']].send_light_setting_light_off(auto)
    elif mode == "FLASH_LOW":
      self.device[self.config.G_ANT['ID_TYPE']['LGT']].send_light_setting_flash_low(auto)
    elif mode == "FLASH_HIGH":
      self.device[self.config.G_ANT['ID_TYPE']['LGT']].send_light_setting_flash_high(auto)
    elif mode == "STEADY_HIGH":
      self.device[self.config.G_ANT['ID_TYPE']['LGT']].send_light_setting_steady_high(auto)
    elif mode == "STEADY_MID":
      self.device[self.config.G_ANT['ID_TYPE']['LGT']].send_light_setting_steady_mid(auto)
    elif mode == "ON_OFF_FLASH_LOW":
      self.device[self.config.G_ANT['ID_TYPE']['LGT']].send_light_setting_light_off_flash_low(auto)


################################################

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
  stored_page = {0x50: False, 0x51: False}
  ant_idle_interval = {'NORMAL':0.20, 'QUICK':0.01, 'SCAN': 0.20}

  def __init__(self, node=None, config=None, values={}, name=''):
    self.node = node
    self.config = config
    self.name = name
    self.values = values
    self.addStructPattern()
    self.initValue()
    
    if node == None: return #for dummy device
    self.makeChannel(self.ant_config['channel_type'])
    self.init_extra()
    self.readyConnect()
    self.connect(isCheck=True, isChange=False) #USE: True -> True

  def on_data(self):
    pass

  def addStructPattern(self):
    pass

  def initValue(self):
    self.setNullValue()
    self.resetValue()
  
  def init_extra(self):
    pass

  def setNullValue(self):
    for element in self.elements:
      self.values[element] = self.config.G_ANT_NULLVALUE

  #reset total value with reset button 
  def resetValue(self):
    pass

  def makeChannel(self, c_type, ext_assign=None):
    if _SENSOR_ANT and self.channel == None:
      self.channel = self.node.new_channel(c_type, ext_assign=ext_assign)
      print(self.name, ': channel_num: ', self.channel.id)
      self.channel.on_broadcast_data = self.on_data
      self.channel.on_burst_data = self.on_data
      self.channel.on_acknowledge_data = self.on_data

  def channel_set_id(self): #for slave
    self.channel.set_id(self.config.G_ANT['ID'][self.name], self.ant_config['type'], self.ant_config['transmission_type'])

  def readyConnect(self):
    if _SENSOR_ANT:
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
    if not _SENSOR_ANT: return
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

  def disconnect(self, isCheck=True, isChange=False, wait=0):
    if not _SENSOR_ANT: return
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

  def setCommonPage81(self, data, values):
    (sw1, sw2, values['serial_num']) = self.structPattern[0x51].unpack(data[0:8])
    if sw1 != 0xFF:
      values['sw_ver'] = float((sw2 * 100 + sw1) / 1000)
    else:
      values['sw_ver'] = float(sw2 / 10)

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

class ANT_Device_HeartRate(ANT_Device):
  
  ant_config = {
    'interval':(8070, 16140, 32280),
    'type':0x78,
    'transmission_type':0x00,
    'channel_type':Channel.Type.BIDIRECTIONAL_RECEIVE,
    } 
  elements = ('hr',)

  def on_data(self, data):
    self.values['hr'] = data[7]
    self.values['timestamp'] = datetime.datetime.now()
    #self.channel.send_acknowledged_data(array.array('B',[0x46,0xFF,0xFF,0xFF,0xFF,0x88,0x06,0x01]))
    #if data[0] & 0b1111 == 0b000: # 0x00 or 0x80
    #  print("0x00 : ", format_list(data))
    #elif data[0] & 0b1111 == 0b010: # 0x02 or 0x82
    #  print("HR serial: {0:05d}".format(data[3]*256+data[2]))
    #elif data[0] & 0b1111 == 0b011: # 0x03 or 0x83
    #  print("0x03 : ", format_list(data))
    #elif data[0] & 0b1111 == 0b110: # 0x06 or 0x86
    #  print("0x06 capabilities: ", format_list(data))
    #elif data[0] & 0b1111 == 0b111: # 0x07 or 0x87
    #  print("0x07 battery status: ", format_list(data))


class ANT_Device_Speed_Cadence(ANT_Device):

  ant_config = {
    'interval':(8086, 16172, 32344),
    'type':0x79,
    'transmission_type':0x00,
    'channel_type':Channel.Type.BIDIRECTIONAL_RECEIVE,
    }
  sc_values  = [] #cad_time, cad, speed_time, speed
  pre_values = [] #cad_time, cad, speed_time, speed
  delta      = [] #cad_time, cad, speed_time, speed
  pre_values = [] #cad_time, cad, speed_time, speed
  elements = ('speed','cadence','distance')

  pickle_key = "ant+_sc_values"

  def addStructPattern(self):
    self.structPattern[self.name] = struct.Struct('<HHHH')

  def resetValue(self):
    self.values['distance'] = 0.0
    self.sc_values = [-1,-1,-1,-1]
    self.pre_values = [-1,-1,-1,-1]
    self.delta = [-1,-1,-1,-1]
    self.values['on_data_timestamp'] = None
 
  def on_data(self, data):
    self.sc_values = self.structPattern[self.name].unpack(data[0:8])
    t = datetime.datetime.now()

    if self.pre_values[0] == -1:
      self.pre_values = list(self.sc_values)
      self.values['speed'] = 0
      self.values['cadence'] = 0
      self.values['on_data_timestamp'] = t
      
      pre_speed_value = self.config.get_config_pickle(self.pickle_key, self.pre_values[3])
      diff = self.pre_values[3] - pre_speed_value
      if -65535 <= diff < 0:
        diff += 65536
      if diff > 0:
        self.values['distance'] += self.config.G_WHEEL_CIRCUMFERENCE * diff
        print("### resume spd ", self.pre_values[3], pre_speed_value, diff, "###")
        print("### resume spd ", self.values['distance'], self.config.G_WHEEL_CIRCUMFERENCE * diff, "[m] ###")

      return

    #cad_time, cad, speed_time, speed
    self.delta = [a - b for(a, b) in zip(self.sc_values, self.pre_values)]
    for i in range(len(self.delta)):
      if -65535 <= self.delta[i] < 0: self.delta[i] += 65536
    
    #speed
    if self.delta[2] > 0 and 0 <= self.delta[3] < 6553: #for spike
      #unit: m/s
      spd = self.config.G_WHEEL_CIRCUMFERENCE * self.delta[3] * 1024 / self.delta[2]
      #max value in .fit file is 65.536 [m/s]
      if spd <= 65 and (spd - self.values['speed']) < self.spike_threshold['speed']:
        self.values['speed'] = spd
        if self.config.G_MANUAL_STATUS == "START":
          #unit: m
          self.values['distance'] += self.config.G_WHEEL_CIRCUMFERENCE * self.delta[3]
        #refresh timestamp called from sensor_core
        self.values['timestamp'] = t
      else:
        self.print_spike("Speed(S&C)", spd, self.values['speed'], self.delta, [])
    elif self.delta[2] == 0 and self.delta[3] == 0:
      #if self.values['on_data_timestamp'] != None and (t - self.values['on_data_timestamp']).total_seconds() >= self.stop_cutoff:
      self.values['speed'] = 0
    else:
      print("ANT+ S&C(speed) err: ", datetime.datetime.now().strftime("%Y%m%d %H:%M:%S"), self.delta)
    #store raw speed
    self.config.set_config_pickle(self.pickle_key, self.sc_values[3])
    
    #cadence
    if self.delta[0] > 0 and 0 <= self.delta[1] < 6553: #for spike
      cad = 60 * self.delta[1] * 1024 / self.delta[0]
      if cad <= 255: #max value in .fit file is 255 [rpm]
        self.values['cadence'] = cad
        #refresh timestamp called from sensor_core
        self.values['timestamp'] = t
    elif self.delta[0] == 0 and self.delta[1] == 0: 
      #if self.values['on_data_timestamp'] != None and (t - self.values['on_data_timestamp']).total_seconds() >= self.stop_cutoff:
      self.values['cadence'] = 0
    else:
      print("ANT+ S&C(cadence) err: ", datetime.datetime.now().strftime("%Y%m%d %H:%M:%S"), self.delta)

    self.pre_values = list(self.sc_values)
    #on_data timestamp
    self.values['on_data_timestamp'] = t

class ANT_Device_Cadence(ANT_Device):

  ant_config = {
    'interval':(8102, 16204, 32408),
    'type':0x7A,
    'transmission_type':0x00,
    'channel_type':Channel.Type.BIDIRECTIONAL_RECEIVE,
    }
  sc_values  = [] #time, value
  pre_values = []
  delta      = []
  elements = ('cadence',)
  const = 60
  fit_max = 255
  
  pickle_key = "ant+_sc_values"

  def addStructPattern(self):
    self.structPattern[self.name] = struct.Struct('<xxxxHH')

  def resetValue(self):
    self.sc_values = [-1,-1]
    self.pre_values = [-1,-1]
    self.delta = [-1,-1]
    self.values['on_data_timestamp'] = None
    for key in ['hw_ver','manu_id','manu_name','model_num','sw_ver', \
                'serial_num','battery_status','battery_voltage']:
      self.values[key] = self.config.G_ANT_NULLVALUE
    self.resetExtra()

  def resetExtra(self):
    pass
 
  def on_data(self, data):
    self.sc_values = self.structPattern[self.name].unpack(data[0:8])
    t = datetime.datetime.now()

    if self.pre_values[0] == -1:
      self.pre_values = list(self.sc_values)
      self.values[self.elements[0]] = 0
      self.values['on_data_timestamp'] = t
      self.resumeAccumulatedValue()
      return

    #time, value
    self.delta = [a - b for(a, b) in zip(self.sc_values, self.pre_values)]
    for i in range(len(self.delta)):
      if -65535 <= self.delta[i] < 0: self.delta[i] += 65536
   
    if self.delta[0] > 0 and  0 <= self.delta[1] < 6553: #for spike
      val = self.const * self.delta[1] * 1024 / self.delta[0]
      #max value in .fit file is fit_max
      if val <= self.fit_max \
        and (val - self.values[self.elements[0]]) < self.spike_threshold[self.elements[0]]:
        self.values[self.elements[0]] = val
        self.accumulateValue()
        #refresh timestamp called from sensor_core
        self.values['timestamp'] = t
      else:
        self.print_spike(self.elements[0], val, self.values[self.elements[0]], self.delta, [])
    elif self.delta[0] == 0 and self.delta[1] == 0:
      #if self.values['on_data_timestamp'] != None and (t - self.values['on_data_timestamp']).total_seconds() >= self.stop_cutoff:
      self.values[self.elements[0]] = 0
    else:
      print("ANT+", self.elements[0], "err: ", datetime.datetime.now().strftime("%Y%m%d %H:%M:%S"), self.delta)
    
    self.pre_values = list(self.sc_values)
    #on_data timestamp
    self.values['on_data_timestamp'] = t

    page = (data[0] & 0b111)
    #Data Page 2: Manufacturer ID
    if page == 2:
      self.values['manu_id'] = data[1]
      if self.values['manu_id'] in ant_code.AntCode.MANUFACTURER:
        self.values['manu_name'] = ant_code.AntCode.MANUFACTURER[self.values['manu_id']]
      self.values['serial_num'] = data[3]*256 + data[2]
    #Data Page 3: Product ID
    elif page == 3:
      self.values['hw_ver'] = data[1]
      self.values['sw_ver'] = data[2]
      self.values['model_num'] = data[3]
    #Data Page 4: Battery Status
    elif page == 4:
      self.setCommonPage82(data[2:4], self.values)

  def resumeAccumulatedValue(self):
    pass

  def accumulateValue(self):
    pass


class ANT_Device_Speed(ANT_Device_Cadence):

  ant_config = {
    'interval':(8118, 16236, 32472),
    'type':0x7B,
    'transmission_type':0x00,
    'channel_type':Channel.Type.BIDIRECTIONAL_RECEIVE,
    }
  elements = ('speed','distance')
  const = None
  fit_max = 65
  
  pickle_key = "ant+_spd_values"

  def resetExtra(self):
    self.values['distance'] = 0.0
    self.const = self.config.G_WHEEL_CIRCUMFERENCE
  
  def resumeAccumulatedValue(self):
    pre_speed_value = self.config.get_config_pickle(self.pickle_key, self.pre_values[1])
    diff = self.pre_values[1] - pre_speed_value
    if -65535 <= diff < 0:
      diff += 65536
    if diff > 0:
      self.values['distance'] += self.config.G_WHEEL_CIRCUMFERENCE * diff
 
  def accumulateValue(self):
    if self.config.G_MANUAL_STATUS == "START":
      #unit: m
      self.values['distance'] += self.config.G_WHEEL_CIRCUMFERENCE * self.delta[1]
    #store raw speed
    self.config.set_config_pickle(self.pickle_key, self.sc_values[1])


class ANT_Device_Power(ANT_Device):

  ant_config = {
    'interval':(8182, 16364, 32728),
    'type':0x0B,
    'transmission_type':0x00,
    'channel_type':Channel.Type.BIDIRECTIONAL_RECEIVE,
    }
  pre_values = {0x10:[], 0x11:[], 0x12:[], 0x13:[]}
  power_values = {0x10:[], 0x11:[], 0x12:[], 0x13:[]}
  elements = {
    0x10:('power','power_l','power_r','lr_balance','power_16_simple','cadence','accumulated_power'),
    0x11:('power','speed','distance','accumulated_power'),
    0x12:('power','cadence','accumulated_power'),
    0x13:('torque_eff','pedal_sm'),
  }

  def addStructPattern(self):
    self.structPattern[self.name] = {
      #(page), evt_count, lr_balance, cadence, accumlated power(2byte), instantaneous power(2byte)
      0x10:struct.Struct('<xBBBHH'),
      #(page), evt_count, wheel_ticks, x, wheel period(2byte), accumulatd power(2byte)
      0x11:struct.Struct('<xBBxHH'),
      #(page), x, x, cadence, period(2byte), accumulatd power(2byte)
      0x12:struct.Struct('<xxxBHH'),
      #(page), x, torque effectiveness(left, right), pedal smoothness(left, right), x, x
      0x13:struct.Struct('<xxBBBBxx'),
    }
  
  def setNullValue(self):
    for page in self.elements:
      self.values[page] = {}
    for page in self.elements:
      for element in self.elements[page]:
        self.values[page][element] = self.config.G_ANT_NULLVALUE
  
  def resetValue(self):
    self.interval = self.ant_config['interval'][self.config.G_ANT['INTERVAL']]/self.ant_config['interval'][-1]
    self.values[0x10]['accumulated_power'] = 0.0
    self.values[0x11]['distance'] = 0.0
    self.values[0x11]['accumulated_power'] = 0.0
    self.values[0x12]['accumulated_power'] = 0.0
    for page in self.pre_values:
      self.pre_values[page] = [-1,-1,-1,-1]
      self.power_values[page] = [-1,-1,-1,-1]
      self.values[page]['on_data_timestamp'] = None

    for key in ['hw_ver','manu_id','manu_name','model_num','sw_ver', \
                'serial_num','battery_status','battery_voltage']:
      self.values[key] = self.config.G_ANT_NULLVALUE

  def on_data(self, data):
    #standard power-only main data page (0x10)
    if data[0] == 0x10:
      self.on_data_power_0x10(data, self.power_values[0x10], self.pre_values[0x10], self.values[0x10])
    #Standard Wheel Torque Main Data Page (0x11) #not verified (not own)
    elif data[0] == 0x11:
      self.on_data_power_0x11(data, self.power_values[0x11], self.pre_values[0x11], self.values[0x11])
    #standard crank power torque main data page (0x12)
    elif data[0] == 0x12:
      self.on_data_power_0x12(data, self.power_values[0x12], self.pre_values[0x12], self.values[0x12])
    #Torque Effectiveness and Pedal Smoothness Main Data Page (0x13)
    elif data[0] == 0x13:
      def setValue(data, key, i):
        self.values[0x13][key] = ""
        if data[i] == 0xFF:
          self.values[0x13][key] += "--%/"
        else:
          self.values[0x13][key] += "{0:02d}%/".format(int(data[i]/2))
        if data[i+1] == 0xFF:
          self.values[0x13][key] += "--%"
        else:
          self.values[0x13][key] += "{0:02d}%".format(int(data[i+1]/2))
      setValue(data, 'torque_eff', 2)
      setValue(data, 'pedal_sm', 4)
    #Common Data Page 80 (0x50): Manufacturer’s Information
    elif data[0] == 0x50 and not self.stored_page[0x50]:
      self.setCommonPage80(data, self.values)
      self.stored_page[0x50] = True
    #Common Data Page 81 (0x51): Product Information
    elif data[0] == 0x51 and not self.stored_page[0x51]:
      self.setCommonPage81(data, self.values)
      self.stored_page[0x51] = True
    #Common Data Page 82 (0x52): Battery Status 
    elif data[0] == 0x52:
      #self.setCommonPage82(data, self.values)
      self.setCommonPage82(data[6:8], self.values)

    #self.channel.send_acknowledged_data(array.array('B',[0x46,0xFF,0xFF,0xFF,0xFF,0x88,0x02,0x01]))

  def on_data_power_0x10(self, data, power_values, pre_values, values):
    #(page), evt_count, balance, cadence, accumlated power(2byte), instantaneous power(2byte)
    (power_values[0], lr_balance, cadence, power_values[1], power_16_simple) \
      = self.structPattern[self.name][0x10].unpack(data[0:8])
    t = datetime.datetime.now()

    if pre_values[0] == -1:
      pre_values[0:2] = power_values[0:2]
      values['on_data_timestamp'] = t
      values['power'] = 0
      return

    delta = [a - b for(a, b) in zip(power_values, pre_values)]
    if -255 <= delta[0] < 0: delta[0] += 256
    if -65535 <= delta[1] < 0: delta[1] += 65536
    delta_t = (t-values['on_data_timestamp']).total_seconds()
    #print("ANT+ Power(16) delta: ", datetime.datetime.now().strftime("%Y%m%d %H:%M:%S"), delta)

    if delta[0] > 0 and delta[1] >= 0 and delta_t < self.stop_cutoff: # delta[1] < 16384: #for spike
      pwr = delta[1] / delta[0]
      #max value in .fit file is 65536 [w]
      if pwr <= 65535 and (pwr - values['power']) < self.spike_threshold['power']:
        values['power'] = pwr
        values['power_16_simple'] = power_16_simple
        values['cadence'] = cadence
        if self.config.G_MANUAL_STATUS == "START" and values['on_data_timestamp'] != None:
          #unit: j
          values['accumulated_power'] += pwr*round((t-values['on_data_timestamp']).total_seconds())
        #lr_balance
        if lr_balance < 0xff and lr_balance >> 7 == 1:
          right_balance = lr_balance & 0b01111111
          values['power_r'] = pwr * right_balance / 100
          values['power_l'] = pwr - values['power_r']
          values['lr_balance'] = "{}:{}".format((100-right_balance),right_balance)
        #refresh timestamp called from sensor_core
        values['timestamp'] = t
      else:
        self.print_spike("Power(16)", pwr, values['power'], delta, delta_t)
    elif delta[0] == 0 and delta[1] == 0:
      #if values['on_data_timestamp'] != None and delta_t >= self.stop_cutoff:
      values['power'] = 0
      values['power_16_simple'] = 0
      values['cadence'] = 0
      values['power_r'] = 0
      values['power_l'] = 0
      values['lr_balance'] = ":"
    else:
      print("ANT+ Power(16) err: ", datetime.datetime.now().strftime("%Y%m%d %H:%M:%S"), delta)
    
    pre_values[0:2] = power_values[0:2]
    #on_data timestamp
    values['on_data_timestamp'] = t
    #store raw power
    self.config.set_config_pickle("ant+_power_values_16", power_values[1])

  def on_data_power_0x11(self, data, power_values, pre_values, values):
    #(page), evt_count, wheel_ticks, x, wheel period(2byte), accumulatd power(2byte)
    (power_values[2], power_values[3], power_values[0], power_values[1]) \
      = self.structPattern[self.name][0x11].unpack(data[0:8])
    t = datetime.datetime.now()

    if pre_values[0] == -1:
      pre_values = power_values
      values['on_data_timestamp'] = t
      values['power'] = 0
      
      pre_pwr_value = self.config.get_config_pickle("ant+_power_values_17", pre_values)
      pwr_diff = pre_values[1] - pre_pwr_value[1]
      spd_diff = pre_values[3] - pre_pwr_value[3]
      if -65535 <= pwr_diff < 0:
        pwr_diff += 65536
      if -255 <= spd_diff < 0:
        spd_diff += 256
      if pwr_diff > 0:
        values['accumulated_power'] += 128*MATH_PI*pwr_diff /2048
      if spd_diff > 0:
        values['distance'] += self.config.G_WHEEL_CIRCUMFERENCE*spd_diff
      return

    delta = [a - b for(a, b) in zip(power_values, pre_values)]
    if -65535 <= delta[0] < 0: delta[0] += 65536
    if -65535 <= delta[1] < 0: delta[1] += 65536
    if -255 <= delta[2] < 0: delta[2] += 256
    if -255 <= delta[3] < 0: delta[3] += 256
    delta_t = (t-values['on_data_timestamp']).total_seconds()

    if delta[0] > 0 and delta[1] >= 0 and delta[2] >= 0 and delta_t < self.stop_cutoff: # delta[1] < 16384 for spike
      
      pwr = 128*MATH_PI*delta[1] / delta[0]
      #max value in .fit file is 65536 [w]
      if pwr <= 65535 and (pwr - values['power']) < self.spike_threshold['power']: 
        values['power'] = pwr
        if self.config.G_MANUAL_STATUS == "START":
          #unit: j
          # values['power'] * delta[0] / 2048 #the unit of delta[0] is 1/2048s
          values['accumulated_power'] += 128*MATH_PI*delta[1] /2048
        #refresh timestamp called from sensor_core
        values['timestamp'] = t
      else:
        self.print_spike("Power(17)", pwr, values['power'], delta, delta_t)

      spd = 3.6*self.config.G_WHEEL_CIRCUMFERENCE*delta[2] / (delta[0]/2048)
      #max value in .fit file is 65.536 [m/s]
      if spd <= 65 and (spd - values['speed']) < self.spike_threshold['speed']:
        values['speed'] = spd
        if self.config.G_MANUAL_STATUS == "START":
          values['distance'] += self.config.G_WHEEL_CIRCUMFERENCE*delta[3]
        #refresh timestamp called from sensor_core
        values['timestamp'] = t
      else:
        self.print_spike("Speed(17)", spd, values['speed'], delta, delta_t)
    elif delta[0] == 0 and delta[1] == 0 and delta[2] == 0:
      #if values['on_data_timestamp'] != None and delta_t >= self.stop_cutoff:
      values['power'] = 0
      values['speed'] = 0
    else:
      print("ANT+ Power(17) err: ", datetime.datetime.now().strftime("%Y%m%d %H:%M:%S"), delta)
    
    pre_values = power_values
    #on_data timestamp
    values['on_data_timestamp'] = t

    #store raw power
    self.config.set_config_pickle("ant+_power_values_17", power_values)

  def on_data_power_0x12(self, data, power_values, pre_values, values):
    #(page), x, x, cadence, period(2byte), accumulatd power(2byte)
    (cadence, power_values[0], power_values[1]) = self.structPattern[self.name][0x12].unpack(data[0:8])
    t = datetime.datetime.now()
    if pre_values[0] == -1:
      pre_values[0:2] = power_values[0:2]
      values['on_data_timestamp'] = t
      values['power'] = 0
      
      pre_pwr_value = self.config.get_config_pickle("ant+_power_values_18", pre_values[1])
      diff = pre_values[1] - pre_pwr_value
      if -65535 <= diff < 0:
        diff += 65536
      if diff > 0:
        values['accumulated_power'] += 128*MATH_PI*diff /2048
        print("### resume pwr ", diff, pre_values[1], pre_pwr_value, "###")
        print("### resume pwr ", int(values['accumulated_power']), int(128*MATH_PI*diff /2048), "[j] ###")
      return

    delta = [a - b for(a, b) in zip(power_values, pre_values)]
    if -65535 <= delta[0] < 0: delta[0] += 65536
    if -65535 <= delta[1] < 0: delta[1] += 65536
    delta_t = (t-values['on_data_timestamp']).total_seconds()
    #print("ANT+ Power(18) delta: ", datetime.datetime.now().strftime("%Y%m%d %H:%M:%S"), delta)

    # delta[1] < 16384: #for spike
    if delta[0] > 0 and delta[1] >= 0 and delta_t < self.stop_cutoff:
      pwr = 128*MATH_PI*delta[1] / delta[0]
      #max value in .fit file is 65536 [w]
      if pwr <= 65535 and (pwr - values['power']) < self.spike_threshold['power']: 
        values['power'] = pwr
        values['cadence'] = cadence
        if self.config.G_MANUAL_STATUS == "START":
          #unit: j
          # values['power'] * delta[0] / 2048 #the unit of delta[0] is 1/2048s
          values['accumulated_power'] += 128*MATH_PI*delta[1] /2048
        #refresh timestamp called from sensor_core
        values['timestamp'] = t
      else:
        self.print_spike("Power(18)", pwr, values['power'], delta, delta_t)
    elif delta[0] == 0 and delta[1] == 0:
      #if delta_t >= self.stop_cutoff:
      values['power'] = 0
      values['cadence'] = 0
    else:
      if self.values['manu_id'] == 48 and self.values['model_num'] == 910:
        #Pioneer SGY-PM910Z powermeter mode fix (not pedaling monitor mode)
        # keep increasing accumulated_power at stopping, so it causes a spike at restart
        pass
      else:
        print("ANT+ Power(18) err: ", datetime.datetime.now().strftime("%Y%m%d %H:%M:%S"), delta)

    pre_values[0:2] = power_values[0:2]
    #on_data timestamp
    values['on_data_timestamp'] = t

    #store raw power
    self.config.set_config_pickle("ant+_power_values_18", power_values[1])


class ANT_Device_Light(ANT_Device):
  
  ant_config = {
    'interval':(4084, 16336, 4084), #4084/8168/16336/32672
    'type':0x23,
    'transmission_type':0x00,
    'channel_type':Channel.Type.BIDIRECTIONAL_RECEIVE,
    } 
  elements = (
    'lgt_state','pre_lgt_state',
    'lgt_state_display',
    'button_state', 'auto_state',
    'last_changed_timestamp')
  page_34_count = 0
  light_retry_timeout = 180
  light_state_bontrager_flare_rt = {
    0x00:"-",
    0x01:"OFF",
    0x16:"ON_MID",
    0x06:"ON_MAX",
    0x1E:"FLASH_H",
    0xFE:"FLASH_L",
  }

  def set_timeout(self):
    self.channel.set_search_timeout(self.timeout)

  def setup_channel_extra(self):
    self.channel.set_channel_tx_power(0)

  def resetValue(self):
    self.values['pre_lgt_state'] = 0
    self.values['lgt_state'] = 0
    self.values['lgt_state_display'] = "-"
    self.values['button_state'] = False
    self.values['auto_state'] = False
    self.values['last_changed_timestamp'] = datetime.datetime.now()

  def close_extra(self):
    if self.ant_state in ['quit', 'disconnectAntSensor']:
      self.send_disconnect_light()
      self.resetValue()
      time.sleep(0.5)

  def on_data(self, data):
    
    #open or close
    if self.values['pre_lgt_state'] == 0 and self.values['lgt_state'] == 0 and \
      self.ant_state in ['connectAntSensor']:
      self.send_connect_light()
      self.send_light_setting_light_off()
    
    #mode change
    if self.values['lgt_state'] > 0 and self.values['lgt_state'] != self.values['pre_lgt_state']:
      print(
        "ANT+ LGT mode change: ", 
        self.light_state_bontrager_flare_rt[self.values['pre_lgt_state']],
        "-> ", 
        self.light_state_bontrager_flare_rt[self.values['lgt_state']], 
        )
      self.values['pre_lgt_state'] = self.values['lgt_state']
      self.values['lgt_state_display'] = self.light_state_bontrager_flare_rt[self.values['lgt_state']]
      self.send_light_setting(self.values['lgt_state'])
      self.values['last_changed_timestamp'] = datetime.datetime.now()

    #self.values['timestamp'] = datetime.datetime.now()

    if data[0] == 0x01:
      mode = (data[6] & 0b11111100) | 0b10
      if mode == 0b00000010:
        mode = 0x01
      if mode != self.values['lgt_state'] and (self.values['last_changed_timestamp'] - datetime.datetime.now()).total_seconds() > self.light_retry_timeout:
        self.send_light_setting(self.values['lgt_state'])
      
    elif data[0] == 0x02:
      pass
    #Common Data Page 80 (0x50): Manufacturer’s Information
    elif data[0] == 0x50 and not self.stored_page[0x50]:
      self.setCommonPage80(data, self.values)
      self.stored_page[0x50] = True
    #Common Data Page 81 (0x51): Product Information
    elif data[0] == 0x51 and not self.stored_page[0x51]:
      self.setCommonPage81(data, self.values)
      self.stored_page[0x51] = True

  def send_acknowledged_data(self, data):
    try:
      self.channel.send_acknowledged_data(data)
    except:
      print("send_acknowledged_data failed: ", data)

  def send_connect_light(self):
    self.send_acknowledged_data(
      #OFF: 0b01001000, ON: 0b01010000,0b01011000
      array.array('B', struct.pack("<BBBBBHB",0x21,0x01,0xFF,0x5A,0x58,self.config.G_ANT['ID'][self.name],0x00))
    )

  def send_disconnect_light(self):
    self.send_acknowledged_data(
      array.array('B',[0x20,0x01,0x5A,0x02,0x00,0x00,0x00,0x00])
    )
  
  def send_light_setting(self, mode):
    self.send_acknowledged_data(
      array.array('B',[0x22,0x01,0x28,self.page_34_count,0x5A,0x10,mode,0x00])
    )
    self.page_34_count = (self.page_34_count+1)%256

  def send_light_setting_flash_low(self, auto=False):
    #mode 63
    self.send_light_setting_templete(0xFE, auto)

  def send_light_setting_flash_high(self, auto=False):
    #mode 7
    self.send_light_setting_templete(0x1E, auto)

  def send_light_setting_flash_mid(self, auto=False):
    #mode 8
    self.send_light_setting_templete(0x22, auto)

  def send_light_setting_steady_high(self, auto=False):
    #mode 1
    self.send_light_setting_templete(0x06, auto)

  def send_light_setting_steady_mid(self, auto=False):
    #mode 5
    self.send_light_setting_templete(0x16, auto)

  def send_light_setting_templete(self, mode, auto=False):
    if not auto:
      self.values['button_state'] = True
    else:
      self.values['auto_state'] = True

    if self.values['lgt_state'] != mode and (not auto or (auto and not self.values['button_state'])):
      self.values['lgt_state'] = mode
    #print("[ON] button:", self.values['button_state'], "lgt_state:", self.values['lgt_state'], "pre_lgt_state:", self.values['pre_lgt_state'])

  def send_light_setting_light_off(self, auto=False):
    if not auto and self.values['auto_state'] and self.values['lgt_state'] != 0x01 and self.values['button_state']:
      self.values['button_state'] = False
      #print("button OFF only")
      return

    if not auto:
      self.values['button_state'] = False
    else:
      self.values['auto_state'] = False

    if self.values['lgt_state'] != 0x01 and (not auto or (auto and not self.values['button_state'])):
      self.values['lgt_state'] = 0x01
    #print("[OFF] button:", self.values['button_state'], "lgt_state:", self.values['lgt_state'], "pre_lgt_state:", self.values['pre_lgt_state'])

  #button on/off only
  def send_light_setting_light_off_flash_low(self, auto=False):
    if not auto and not self.values['button_state']:
      self.send_light_setting_flash_low()
    elif not auto and self.values['button_state']:
      self.send_light_setting_light_off()


class ANT_Device_CTRL(ANT_Device):
  
  ant_config = {
    'interval':(8192, 16384, 16384), #8192, 16384, 32768
    'type':0x10,
    'transmission_type':0x05,
    'channel_type':Channel.Type.BIDIRECTIONAL_TRANSMIT,
    'master_id': 123,
    }
  elements = ('ctrl_cmd','slave_id')
  send_data = False
  data_page_02 = array.array("B", [0x02,0x00,0x00,0x00,0x00,0x00,0x00,0x10])

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
    if self.values['ctrl_cmd'] == 0x0024:
      #print("lap")
      self.config.gui.scroll_next()
    elif self.values['ctrl_cmd'] == 0x0001:
      #print("menu up")
      self.config.gui.scroll_prev()
    elif self.values['ctrl_cmd'] == 0x0000:
      #print("menu down")
      pass
    elif self.values['ctrl_cmd'] == 0x8000:
      #print("custom1")
      self.config.logger.sensor.sensor_ant.set_light_mode("ON_OFF_FLASH_LOW")
    elif self.values['ctrl_cmd'] == 0x8001:
      #print("custom2")
      pass
    #self.values['timestamp'] = datetime.datetime.now()


class ANT_Device_MultiScan(ANT_Device):

  name = 'SCAN'
  ant_config = {
    'interval':(), #Not use
    'type':0, #ANY
    'transmission_type':0x00,
    'channel_type':Channel.Type.UNIDIRECTIONAL_RECEIVE_ONLY,
    }
  isUse = False
  mainAntDevice = None
  power_values = {}
  power_meter_value = {}
  pre_power_meter_value = {}

  def __init__(self, node, config):
    self.node = node
    self.config = config
    self.resetValue()
    self.makeChannel(self.ant_config['channel_type'])
    self.readyScan()
    self.dummyPowerDevice = ANT_Device_Power(node=None, config=config, values={}, name='PWR')

  def setNullValue(self):
    pass
  
  def resetValue(self):
    self.values = {}
    self.power_values = {}
    self.power_meter_value = {}
    self.pre_power_meter_value = {}
  
  def readyScan(self):
    if _SENSOR_ANT:
      self.channel.set_rf_freq(57)
      self.channel.set_id(0, self.ant_config['type'], self.ant_config['transmission_type'])
  
  def scan(self):
    if _SENSOR_ANT:
      self.channel.enable_extended_messages(1)
      try:
        self.channel.open_rx_scan_mode() 
        self.isUse = True
      except:
        pass

  def stopScan(self):
    self.disconnect(0.5)
    
  def stop(self):
    return self.disconnect(0)

  def disconnect(self, wait):
    if not _SENSOR_ANT: return False
    if not self.isUse: return False
    if self.stateCheck("CLOSE"):
      self.isUse = False
      return True
    try:
      self.channel.close()
      time.sleep(wait)
      self.setNullValue() 
      self.isUse = False
      self.channel.enable_extended_messages(0)
      return True
    except:
      return False

  def setMainAntDevice(self, device):
    self.mainAntDevice = device

  def on_data(self, data):
    #get type and ID
    antType = antID = antIDType = 0
    if len(data) == 13:
      (antID, antType) = self.structPattern['ID'].unpack(data[9:12])
      antIDType = struct.pack('<HB', antID, antType)
    else:
      return

    #HR
    if antType in self.config.G_ANT['TYPES']['HR']:
      if antIDType == self.config.G_ANT['ID_TYPE']['HR']:
        self.mainAntDevice[antIDType].on_data(data)
      else:
        if antIDType not in self.values:
          self.values[antIDType] = {}
        self.values[antIDType]['timestamp'] = datetime.datetime.now()
        self.values[antIDType]['hr'] = data[7]
    #Power
    elif antType in self.config.G_ANT['TYPES']['PWR']:
      if antIDType == self.config.G_ANT['ID_TYPE']['PWR']:
        self.mainAntDevice[antIDType].on_data(data)
      else:
        if antIDType not in self.values:
          self.values[antIDType] = {}
          self.power_values[antIDType] = {
            0x10: {'power':0, 'accumulated_power':0, 'on_data_timestamp':None},
            0x11: {'power':0, 'accumulated_power':0, 'distance':0, 'on_data_timestamp':None},
            0x12: {'power':0, 'accumulated_power':0, 'on_data_timestamp':None},
            0x50: {'manu_name':''},
          }
          self.power_meter_value[antIDType] = {
            0x10: [-1,-1,-1,-1],
            0x11: [-1,-1,-1,-1],
            0x12: [-1,-1,-1,-1],
          }
          self.pre_power_meter_value[antIDType] = {
            0x10: [-1,-1,-1,-1],
            0x11: [-1,-1,-1,-1],
            0x12: [-1,-1,-1,-1],
          }
        self.values[antIDType]['timestamp'] = datetime.datetime.now()
        if data[0] == 0x10:
          self.dummyPowerDevice.on_data_power_0x10(
            data, 
            self.power_meter_value[antIDType][0x10], 
            self.pre_power_meter_value[antIDType][0x10], 
            self.power_values[antIDType][0x10]
          )
          self.values[antIDType]['power'] = self.power_values[antIDType][0x10]['power']
        elif data[0] == 0x11:
          self.dummyPowerDevice.on_data_power_0x11(
            data, 
            self.power_meter_value[antIDType][0x11], 
            self.pre_power_meter_value[antIDType][0x11],
            self.power_values[antIDType][0x11]
          )
          self.values[antIDType]['power'] = self.power_values[antIDType][0x11]['power']
        elif data[0] == 0x12:
          self.dummyPowerDevice.on_data_power_0x12(
            data, 
            self.power_meter_value[antIDType][0x12], 
            self.pre_power_meter_value[antIDType][0x12], 
            self.power_values[antIDType][0x12]
          )
          self.values[antIDType]['power'] = self.power_values[antIDType][0x12]['power']
        elif data[0] == 0x50:
          self.setCommonPage80(data, self.power_values[antIDType][0x50])
          self.values[antIDType]['manu_name'] = self.power_values[antIDType][0x50]['manu_name']
    #Speed
    elif antType in self.config.G_ANT['TYPES']['SPD']:
      if antIDType == self.config.G_ANT['ID_TYPE']['SPD']:
        self.mainAntDevice[antIDType].on_data(data)
    #Cadence
    elif antType in self.config.G_ANT['TYPES']['CDC']:
      if antIDType == self.config.G_ANT['ID_TYPE']['CDC']:
        self.mainAntDevice[antIDType].on_data(data)


class ANT_Device_Search(ANT_Device):

  name = 'SEARCH'
  ant_config = {
    'interval':(), #Not use
    'type':0, #ANY
    'channel_type':Channel.Type.BIDIRECTIONAL_RECEIVE,
    }
  isUse = False
  searchList = None
  searchState = False

  def __init__(self, node, config, values=None):
    self.node = node
    self.config = config
    #special use of makeChannel(c_type, search=False)
    self.makeChannel(self.ant_config['channel_type'], ext_assign=0x01)

  def on_data(self, data):
    if not self.searchState: return
    if len(data) == 13:
      (antID, antType) = self.structPattern['ID'].unpack(data[9:12])
      if antType in self.config.G_ANT['TYPES'][self.antName]:
        #new ANT+ sensor
        self.searchList[antID] = (antType, False)

  def on_data_ctrl(self, data):
    if not self.searchState: return
    if len(data) == 8:
      (antID,) = struct.Struct('<H').unpack(data[1:3])
      antType = 0x10
      if antType in self.config.G_ANT['TYPES'][self.antName]:
        #new ANT+ sensor
        self.searchList[antID] = (antType, False)
 
  def search(self, antName):
    self.searchList = {}
    for k,v in self.config.G_ANT['USE'].items():
      if k == antName: continue
      if v and k in self.config.G_ANT['ID_TYPE']:
        (antID, antType) = struct.unpack('<HB', self.config.G_ANT['ID_TYPE'][k])
        if antType in self.config.G_ANT['TYPES'][antName]:
          #already connected
          self.searchList[antID] = (antType, True)

    if _SENSOR_ANT and not self.searchState:
      self.antName = antName
      
      if self.antName not in ['CTRL']:
        self.set_wait_quick_mode()
        self.channel.set_search_timeout(0)
        self.channel.set_rf_freq(57)
        self.channel.set_id(0, 0, 0)

        self.channel.enable_extended_messages(1)
        self.channel.set_low_priority_search_timeout(0xFF)
        self.node.set_lib_config(0x80)   

        self.connect(isCheck=False, isChange=False) #USE: False -> True

      elif self.antName == 'CTRL':
        self.ctrl_searcher = ANT_Device_CTRL(self.node, self.config, {}, antName)
        self.ctrl_searcher.channel.on_acknowledge_data = self.on_data_ctrl
        self.ctrl_searcher.send_data = True
        self.ctrl_searcher.connect(isCheck=False, isChange=False)
        
      self.searchState = True
      
  def stopSearch(self, resetWait=True):
    if _SENSOR_ANT and self.searchState:
      if self.antName not in ['CTRL']:
        self.disconnect(isCheck=False, isChange=False, wait=0.5) #USE: True -> False
        
        #for background scan
        self.channel.enable_extended_messages(0)
        self.node.set_lib_config(0x00)
        self.channel.set_low_priority_search_timeout(0x00)
      
        if resetWait:
          self.set_wait_normal_mode()

      elif self.antName == 'CTRL':
        self.ctrl_searcher.disconnect(isCheck=False, isChange=False, wait=0.5)
        self.ctrl_searcher.delete()
        del self.ctrl_searcher

      self.searchState = False

  def getSearchList(self):
    if _SENSOR_ANT:
      return self.searchList
    else:
      #dummy
      timestamp = datetime.datetime.now()
      if 0 < timestamp.second%30 < 15:
        return {
          12345:(0x79, False), 
          23456:(0x7A, False),
          6789:(0x78, False),
        }
      elif 15 < timestamp.second%30 < 30:
        return {
          12345:(0x79, False), 
          23456:(0x7A, False),
          34567:(0x7B, False),
          45678:(0x0B, False),
          45679:(0x0B, True),
          56789:(0x78, False),
          6789:(0x78, False),
        }
      else:
        return {}
 


