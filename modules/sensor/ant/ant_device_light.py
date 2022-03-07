import struct
import datetime
import time
import array

from . import ant_device


class ANT_Device_Light(ant_device.ANT_Device):
  
  ant_config = {
    'interval':(4084, 8168, 16336), #4084/8168/16336/32672
    'type':0x23,
    'transmission_type':0x00,
    'channel_type':0x00, #Channel.Type.BIDIRECTIONAL_RECEIVE,
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
  pickle_key = "ant+_lgt_values"

  def set_timeout(self):
    self.channel.set_search_timeout(self.timeout)

  def setup_channel_extra(self):
    #0:-18 dBm, 1:-12 dBm, 2:-6 dBm, 3:0 dBm, 4:N/A
    self.channel.set_channel_tx_power(2)

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

    if data[0] == 0x01:
      mode = (data[6] & 0b11111100) | 0b10
      if mode == 0b00000010:
        mode = 0x01
      if mode != self.values['lgt_state'] and (self.values['last_changed_timestamp'] - datetime.datetime.now()).total_seconds() > self.light_retry_timeout:
        self.send_light_setting(self.values['lgt_state'])
    elif data[0] == 0x02:
      pass
    #Common Data Page 80 (0x50): Manufacturer’s Information
    elif data[0] == 0x50 and not self.values["stored_page"][0x50]:
      self.setCommonPage80(data, self.values)
    #Common Data Page 81 (0x51): Product Information
    elif data[0] == 0x51 and not self.values["stored_page"][0x51]:
      self.setCommonPage81(data, self.values)

  def send_acknowledged_data(self, data):
    try:
      self.channel.send_acknowledged_data(data)
    except:
      print("send_acknowledged_data failed: ", data)

  def send_connect_light(self):
    self.send_acknowledged_data(
      #ON: 0b01010000,0b01011000
      #array.array('B', struct.pack("<BBBBBHB",0x21,0x01,0xFF,0x5A,0x58,self.config.G_ANT['ID'][self.name],0x00))
      #OFF: 0b01001000
      array.array('B', struct.pack("<BBBBBHB",0x21,0x01,0xFF,0x5A,0x48,self.config.G_ANT['ID'][self.name],0x00))
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
    #mode 63, 15 hours
    self.send_light_setting_templete(0xFE, auto)

  def send_light_setting_flash_high(self, auto=False):
    #mode 7, 6 hours
    self.send_light_setting_templete(0x1E, auto)

  def send_light_setting_flash_mid(self, auto=False):
    #mode 8, 12 hours
    self.send_light_setting_templete(0x22, auto)

  def send_light_setting_steady_high(self, auto=False):
    #mode 1, 4.5 hours
    self.send_light_setting_templete(0x06, auto)

  def send_light_setting_steady_mid(self, auto=False):
    #mode 5, 13.5 hours
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
