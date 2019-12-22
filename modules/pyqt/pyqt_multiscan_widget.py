import datetime
import struct

from .pyqt_screen_widget import ScreenWidget

#################################
# multi scan widget 
#################################

class MultiScanWidget(ScreenWidget):

  values = {
    'HR': [],
    'HR_ID': [],
    'PWR': [],
    'PWR_ID': [],
    'PWR_NAME': [],
  }
  struct_pattern = {
    'ID':struct.Struct('<HB'),
  }
  
  def reset_values(self):
    self.values = {
      'HR': [0,0,0],
      'HR_ID': [0,0,0],
      'PWR': [0,0,0],
      'PWR_ID': [0,0,0],
      'PWR_NAME': ['','',''],
    }
  
  #if make make_item_layout by hard cording
  def make_item_layout(self):
    self.item_layout = {
      'Power':(0, 0), 'HR':(0, 1), 'Time':(0, 2),
      'HR1':(1, 0), 'HR2':(1, 1), 'HR3':(1, 2),
      'PWR1':(2, 0), 'PWR2':(2, 1), 'PWR3':(2, 2),
    }

  #call from on_change_main_page in gui_pyqt.py
  def start(self):
    if not self.sensor.sensor_ant.scanner.isUse:
      self.sensor.sensor_ant.continuousScan()
    self.timer.start(self.config.G_DRAW_INTERVAL)
  
  #call from on_change_main_page in gui_pyqt.py
  def stop(self):
    if self.sensor.sensor_ant.scanner.isUse:
      self.sensor.sensor_ant.stopContinuousScan()
    self.timer.stop()

  def update_display(self):
    #update multi device value
    now_time = datetime.datetime.now()
    self.reset_values()
    count = {'HR':0, 'PWR':0}
    for ant_id_type,values in self.sensor.sensor_ant.scanner.values.items():
      (ant_id, ant_type) = self.struct_pattern['ID'].unpack(ant_id_type)
      #only HR and PWR
      if ant_type not in self.config.G_ANT['TYPES']['HR'] and\
        ant_type not in self.config.G_ANT['TYPES']['PWR']:
        continue
      #check timestamp
      if 'timestamp' not in values: continue
      timedelta = (now_time - values['timestamp']).total_seconds()
      if timedelta >= 5: continue
      
      if ant_type in self.config.G_ANT['TYPES']['HR'] and count['HR'] < 3:
        if 'hr' in values:
          self.values['HR'][count['HR']] = values['hr']
          self.values['HR_ID'][count['HR']] = ant_id_type
          count['HR'] +=1
      elif ant_type in self.config.G_ANT['TYPES']['PWR'] and count['PWR'] < 3:
        if 'power' in values:
          self.values['PWR'][count['PWR']] = values['power']
          self.values['PWR_ID'][count['PWR']] = ant_id_type
          count['PWR'] +=1

    for item in self.items:
      if item.name in ['HR', 'Power', 'Time']:
        item.update_value(eval(self.config.gui.gui_config.G_ITEM_DEF[item.name][1]))
      else:
        item.label.setText(item.name)
        key = item.name[0:-1]
        i = int(item.name[-1:]) - 1
        ant_id_type = self.values[key+'_ID'][i]
        if ant_id_type != 0:
          (ant_id, ant_type) = self.struct_pattern['ID'].unpack(ant_id_type)
          item.update_value(self.values[key][i])
          if key == 'PWR' and 'manu_name' in self.sensor.sensor_ant.scanner.values[ant_id_type]:
            item.label.setText(self.sensor.sensor_ant.scanner.values[ant_id_type]['manu_name'])
        else: item.update_value(None)


