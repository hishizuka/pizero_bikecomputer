try:
  import PyQt6.QtCore as QtCore
  import PyQt6.QtWidgets as QtWidgets
  import PyQt6.QtGui as QtGui
except:
  import PyQt5.QtCore as QtCore
  import PyQt5.QtWidgets as QtWidgets
  import PyQt5.QtGui as QtGui

from .pyqt_menu_widget import MenuWidget, ListWidget, ListItemWidget
import modules.pyqt.pyqt_multiscan_widget as pyqt_multiscan


class SensorMenuWidget(MenuWidget):

  def setup_menu(self):
    self.button = {}
    button_conf = (
      #Name(page_name), button_attribute, connected functions, layout
      ('ANT+ Sensors', 'submenu', self.ant_sensors_menu),
      ('ANT+ MultiScan', 'submenu', self.ant_multiscan_menu),
      ('Wheel Size', 'submenu', self.adjust_wheel_circumference),
      ('Auto Stop', None, None),
      ('Gross Ave Speed', None, None),
      ('Adjust Altitude', 'submenu', self.adjust_altitude),
      )
    self.add_buttons(button_conf)

  def ant_sensors_menu(self):
    if self.config.logger.sensor.sensor_ant.scanner.isUse:
      #output message dialog "cannot go in multiscan mode"
      return
    self.change_page('ANT+ Sensors')
  
  def ant_multiscan_menu(self):
    self.change_page('ANT+ MultiScan', preprocess=True)
  
  def adjust_wheel_circumference(self):
    self.change_page('Wheel Size', preprocess=True)

  def adjust_altitude(self):
    self.change_page('Adjust Altitude')
    #temporary
    self.config.logger.sensor.sensor_i2c.recalibrate_position()


class ANTMenuWidget(MenuWidget):

  def setup_menu(self):
    self.button = {}
    button_conf = []
    for antName in self.config.G_ANT['ORDER']:
      #Name(page_name), button_attribute, connected functions, layout
      button_conf.append((antName, 'submenu', eval("self.setting_ant_"+antName)))
    self.add_buttons(button_conf, back_connect=False)

    #modify label from antName to self.get_button_state()
    for antName in self.config.G_ANT['ORDER']:
      self.button[antName].setText(self.get_button_state(antName))

    if not self.config.display.has_touch():
      self.focus_widget = self.button[self.config.G_ANT['ORDER'][0]]
    #self.button[self.config.G_ANT['ORDER'][0]].first_button = True
    #self.button[self.config.G_ANT['ORDER'][-1]].last_button = True

    #set back_index of child widget
    self.child_page_name = "ANT+ Detail"
    self.child_index = self.config.gui.gui_config.G_GUI_INDEX[self.child_page_name]
    self.parentWidget().widget(self.child_index).back_index_key = self.page_name

  def get_button_state(self, antName):
    status = "OFF"
    if antName in self.config.G_ANT['USE'] and self.config.G_ANT['USE'][antName]:
      status = '{0:05d}'.format(self.config.G_ANT['ID'][antName])
    return self.config.G_ANT['NAME'][antName] + ": " + status

  def setting_ant_HR(self):
    self.setting_ant('HR')
  
  def setting_ant_SPD(self):
    self.setting_ant('SPD')
  
  def setting_ant_CDC(self):
    self.setting_ant('CDC')
  
  def setting_ant_PWR(self):
    self.setting_ant('PWR')
  
  def setting_ant_LGT(self):
    self.setting_ant('LGT')
  
  def setting_ant_CTRL(self):
    self.setting_ant('CTRL')

  def setting_ant_TEMP(self):
    self.setting_ant('TEMP')
  
  def setting_ant(self, ant_name):
    if self.config.G_ANT['USE'][ant_name]:
      #disable ANT+ sensor
      self.config.logger.sensor.sensor_ant.disconnect_ant_sensor(ant_name)
    else:
      #search ANT+ sensor
      self.change_page(self.child_page_name, preprocess=True, reset=True, list_type=ant_name)
      
    self.update_button_label()

  def update_button_label(self):
    for ant_name in self.button.keys():
      self.button[ant_name].setText(self.get_button_state(ant_name))


class ANTListWidget(ListWidget):

  ant_sensor_types = {}

  def setup_menu_extra(self):
    # update panel for every 1 seconds
    self.timer = QtCore.QTimer(parent=self)
    self.timer.timeout.connect(self.update_display)

  async def button_func_extra(self):
    print('connect {}: {}'.format(self.list_type, self.selected_item.list_info['id']))
    if self.selected_item == None: return
    ant_id = int(self.selected_item.list_info['id'])
    self.config.logger.sensor.sensor_ant.connect_ant_sensor(\
      self.list_type, #sensor type
      ant_id, #ID
      self.ant_sensor_types[ant_id][0], #id_type
      self.ant_sensor_types[ant_id][1], #connection status
    )
    self.config.setting.write_config()

  def on_back_menu(self):
    self.timer.stop()
    self.config.logger.sensor.sensor_ant.searcher.stop_search()
    #button update
    index = self.config.gui.gui_config.G_GUI_INDEX[self.back_index_key]
    self.parentWidget().widget(index).update_button_label()

  def preprocess_extra(self):
    self.ant_sensor_types.clear()
    self.config.logger.sensor.sensor_ant.searcher.search(self.list_type)
    self.timer.start(self.config.G_DRAW_INTERVAL)

  def update_display(self):
    detected_sensors = self.config.logger.sensor.sensor_ant.searcher.getSearchList()
    
    for ant_id, ant_type_array in detected_sensors.items():
      ant_id_str = '{0:05d}'.format(ant_id)
      add = True
      for i in range(self.list.count()):
        if ant_id_str == self.list.itemWidget(self.list.item(i)).list_info['id']:
          add = False
      if add: 
        self.ant_sensor_types[ant_id] = ant_type_array
        ant_item = ANTListItemWidget(self, self.config)
        status = False
        if ant_type_array[1]: status = True
        ant_item.set_info(
          id = ant_id_str, 
          type = self.config.G_ANT['TYPE_NAME'][ant_type_array[0]],
          status = status,
        )
        self.add_list_item(ant_item)
        #ant_item.set_icon('img/ant.png')


class ANTListItemWidget(ListItemWidget):
  
  def add_extra(self):
    self.dummy_px = QtGui.QPixmap(20,20)
    self.dummy_px.fill(QtGui.QColor("#008000"))
    self.icon = QtWidgets.QLabel()
    self.icon.setPixmap(self.dummy_px)
    self.icon.setContentsMargins(5,0,10,0)

    #outer layout (custom)
    self.outer_layout.addWidget(self.icon)
    self.outer_layout.addLayout(self.inner_layout, self.config.gui.gui_config.align_left)
    
    #self.enter_signal.connect(self.parentWidget().connect_ant_sensor)
    self.enter_signal.connect(self.parentWidget().button_func)

  def set_info(self, **kargs):#ant_id, ant_type):
    self.list_info = kargs.copy()
    self.detail_label.setText('   ID: '+self.list_info['id'])
    status_str = ''
    if self.list_info['status']:
      status_str = ' (connected)'
    self.title_label.setText(self.list_info['type']+status_str)


class ANTMultiScanScreenWidget(MenuWidget):

  def setup_menu(self):
    self.make_menu_layout(QtWidgets.QHBoxLayout)
    self.multiscan_widget = pyqt_multiscan.MultiScanWidget(self, self.config)
    self.menu_layout.addWidget(self.multiscan_widget)
  
  def preprocess(self):
    self.multiscan_widget.start()
  
  def on_back_menu(self):
    self.multiscan_widget.stop()

