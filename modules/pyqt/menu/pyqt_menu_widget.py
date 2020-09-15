import time

import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtGui as QtGui

#################################
# Menu
#################################

class MenuWidget(QtWidgets.QWidget):

  config = None
  title = None
  back_index_key = None

  def __init__(self, parent, title, config):
    QtWidgets.QWidget.__init__(self, parent=parent)
    self.parent = parent
    self.config = config
    self.title = title
    self.icon_dir = ""
    if self.config.G_IS_RASPI:
      self.icon_dir = self.config.G_INSTALL_PATH
    self.icon = QtGui.QIcon(self.icon_dir+'img/backarrow_white.png')
    self.icon_x = 50
    self.icon_y = 32
    self.ant = self.config.logger.sensor.sensor_ant
    
    self.setup_ui()

  def setup_ui(self):
    self.setContentsMargins(0,0,0,0)
    
    #top bar
    self.top_bar = QtWidgets.QWidget(self)
    self.top_bar.setStyleSheet("background-color: #006600")
    self.back_button = QtWidgets.QPushButton(self.icon,"")
    self.back_button.setStyleSheet(self.config.gui.style.G_GUI_PYQT_buttonStyle_navi)
    self.back_button.setFixedSize(self.icon_x, self.icon_y)
    self.title_label = QtWidgets.QLabel(self.title)
    self.title_label.setAlignment(QtCore.Qt.AlignCenter)
    self.title_label.setStyleSheet("color: #FFFFFF;")
    spacer = QtWidgets.QWidget()
    spacer.setFixedSize(self.icon_x, self.icon_y)
    
    top_bar_layout = QtWidgets.QHBoxLayout(self.top_bar)
    top_bar_layout.setContentsMargins(5,5,5,5)
    top_bar_layout.setSpacing(0)
    top_bar_layout.addWidget(self.back_button)
    top_bar_layout.addWidget(self.title_label)
    top_bar_layout.addWidget(spacer)

    self.top_bar.setLayout(top_bar_layout)
    
    #main
    self.menu = None
    self.setup_menu()
    layout = QtWidgets.QVBoxLayout()
    layout.setContentsMargins(0,0,0,0)
    layout.setSpacing(0)
    layout.addWidget(self.top_bar)
    layout.addWidget(self.menu)
    self.setLayout(layout)
    self.connect_back_button()
    self.connect_buttons()

  def setup_menu(self):
    self.menu = QtWidgets.QWidget(self)
  
  def resizeEvent(self, event):
    #w = self.size().width()
    h = self.size().height()
    self.top_bar.setFixedHeight(int(h/5))

    q = self.title_label.font()
    q.setPixelSize(int(h/12))
    self.title_label.setFont(q)

  def connect_buttons(self):
    pass
  
  def connect_back_button(self):
    self.back_button.clicked.connect(self.back)
  
  def back(self):
    index = 0
    if self.back_index_key != None and self.back_index_key in self.config.gui.gui_config.G_GUI_INDEX:
      index = self.config.gui.gui_config.G_GUI_INDEX[self.back_index_key]
    self.on_back_menu()
    self.config.gui.change_menu_page(index)
  
  def on_back_menu(self):
    pass

  class MenuButton(QtWidgets.QPushButton):
    config = None

    def __init__(self, text, config):
      super().__init__(text=text)
      self.config = config
      self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
      self.setStyleSheet(self.config.gui.style.G_GUI_PYQT_buttonStyle_menu)

    def resizeEvent(self, event):
      #w = self.size().width()
      h = self.size().height()
      
      q = self.font()
      q.setPixelSize(int(h/2.5))
      self.setFont(q)
    
    def setToggle(self):
      self.setCheckable(True)
      self.toggled.connect(self.slot_button_toggled)
    
    def slot_button_toggled(self, checked):
      if checked:
        self.setText('Checked')
        self.setStyleSheet(self.config.gui.style.G_GUI_PYQT_buttonStyle_menu_toggle)
      else:
        self.setText('Not Checked')
        self.setStyleSheet(self.config.gui.style.G_GUI_PYQT_buttonStyle_menu)
    
    def onOff(self):
      pass
    
    def setValue(self):
      pass


class TopMenuWidget(MenuWidget):

  wifi_bt_on = True

  def setup_menu(self):
    self.menu = QtWidgets.QWidget(self)
    self.back_index_key = 'main'
    
    button_names = [
      'ANT+ Sensors',
      'Wifi BT',
      'Update',
      'Strava Upload',
      'Wheel Size',
      'Adjust Altitude',
      'Power Off',
      'Debug Log',
    ]
    self.menu_layout = QtWidgets.QGridLayout(self.menu)
    self.menu_layout.setContentsMargins(0,0,0,0)
    self.menu_layout.setSpacing(0)
    self.button = {}
    for label in button_names:
      self.button[label] = self.MenuButton(label, self.config)
    self.update_wifi_bt_label()

    #layout buttons
    self.menu_layout.addWidget(self.button['ANT+ Sensors'],0,0)
    self.menu_layout.addWidget(self.button['Wifi BT'],0,1)
    self.menu_layout.addWidget(self.button['Update'],1,0)
    self.menu_layout.addWidget(self.button['Strava Upload'],1,1)
    self.menu_layout.addWidget(self.button['Wheel Size'],2,0)
    self.menu_layout.addWidget(self.button['Adjust Altitude'],2,1)
    self.menu_layout.addWidget(self.button['Power Off'],3,0)
    self.menu_layout.addWidget(self.button['Debug Log'],3,1)
    self.menu.setLayout(self.menu_layout)

  def connect_buttons(self):
    self.button['ANT+ Sensors'].clicked.connect(self.ant_sensors_menu)
    self.button['Wifi BT'].clicked.connect(self.wifi_bt_onoff)
    self.button['Update'].clicked.connect(self.config.update_application)
    self.button['Strava Upload'].clicked.connect(self.config.strava_upload)
    self.button['Wheel Size'].clicked.connect(self.adjust_wheel_circumference)
    self.button['Adjust Altitude'].clicked.connect(self.adjust_altitude)
    self.button['Power Off'].clicked.connect(self.config.poweroff)
    self.button['Debug Log'].clicked.connect(self.debug_log)

  def ant_sensors_menu(self):
    if self.ant.scanner.isUse:
      #output message dialog "cannot go in multiscan mode"
      return
    self.config.gui.change_menu_page(self.config.gui.gui_config.G_GUI_INDEX['ANT+Top'])
  
  def wifi_bt_onoff(self):
    self.config.wifi_bt_onoff()
    self.update_wifi_bt_label()
   
  def update_wifi_bt_label(self): 
    status = "OFF"
    wifi_status, bt_status = self.config.get_wifi_bt_status()
    if wifi_status:
      status = "ON"
    self.button['Wifi BT'].setText('Wifi BT' + '(' + status + ')')

  def adjust_wheel_circumference(self):
    index = self.config.gui.gui_config.G_GUI_INDEX['Wheel Size']
    self.parent.widget(index).update_display()
    self.config.gui.change_menu_page(self.config.gui.gui_config.G_GUI_INDEX['Wheel Size'])

  def adjust_altitude(self):
    self.config.gui.change_menu_page(self.config.gui.gui_config.G_GUI_INDEX['Adjust Altitude'])
    #temporary
    self.config.logger.sensor.sensor_i2c.recalibrate_position()

  def debug_log(self):
    index = self.config.gui.gui_config.G_GUI_INDEX['Debug Log Viewer']
    self.parent.widget(index).update_display()
    self.config.gui.change_menu_page(self.config.gui.gui_config.G_GUI_INDEX['Debug Log Viewer'])


class ANTMenuWidget(MenuWidget):
  
  def setup_menu(self):
    self.menu = QtWidgets.QWidget()
    self.back_index_key = 'menu'
    
    self.menu_layout = QtWidgets.QVBoxLayout()
    self.menu_layout.setContentsMargins(0,0,0,0)
    self.menu_layout.setSpacing(0)
    self.button = {}
    #for order,antName in sorted(self.config.G_ANT['ORDER'].items()):
    for antName in self.config.G_ANT['ORDER']:
      self.button[antName] = self.MenuButton(self.getButtonState(antName), self.config)
      self.menu_layout.addWidget(self.button[antName])

    self.menu.setLayout(self.menu_layout)

  def getButtonState(self, antName):
    status = "OFF"
    if self.config.G_ANT['USE'][antName]:
      status = "ON ("+'{0:05d}'.format(self.config.G_ANT['ID'][antName])+")"
    return self.config.G_ANT['NAME'][antName] + ": " + status

  def connect_buttons(self):
    self.button['HR'].clicked.connect(self.settingAntHR)
    self.button['SPD'].clicked.connect(self.settingAntSpeed)
    self.button['CDC'].clicked.connect(self.settingAntCadence)
    self.button['PWR'].clicked.connect(self.settingAntPower)
  def settingAntHR(self):
    self.settingAnt('HR')
  def settingAntSpeed(self):
    self.settingAnt('SPD')
  def settingAntCadence(self):
    self.settingAnt('CDC')
  def settingAntPower(self):
    self.settingAnt('PWR')
  def settingAnt(self, antName):
    if self.config.G_ANT['USE'][antName]:
      #disable ANT+ sensor
      self.ant.disconnectAntSensor(antName)
    else:
      #search ANT+ sensor
      index = self.config.gui.gui_config.G_GUI_INDEX['ANT+Detail']
      self.parent.widget(index).display(antName)
      self.config.gui.change_menu_page(index)
    self.update_button_label()

  def update_button_label(self):
    for ant_name in self.button.keys():
      self.button[ant_name].setText(self.getButtonState(ant_name))


class ANTDetailWidget(MenuWidget):

  selected_ant_id = None
  ant_name = None

  def setup_menu(self):
    self.menu = QtWidgets.QWidget()
    self.back_index_key = 'ANT+Top'
    
    self.menu_layout = QtWidgets.QVBoxLayout()
    self.menu_layout.setContentsMargins(0,0,0,0)
    self.menu_layout.setSpacing(0)

    self.items = QtWidgets.QListWidget()
    self.type = {}
    #self.items.setSortingEnabled(True)
    #self.items.setStyleSheet(self.config.gui.style.G_GUI_PYQT_list)
    #self.items.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
    self.items.setStyleSheet("background-color: transparent;")
    self.connect_button = self.MenuButton("Connect", self.config)

    self.menu_layout.addWidget(self.items)
    self.menu_layout.addWidget(self.connect_button)

    self.menu.setLayout(self.menu_layout)
    
    # update panel for every 1 seconds
    self.timer = QtCore.QTimer(parent=self)
    self.timer.timeout.connect(self.update_display)

  def connect_buttons(self):
    self.items.itemSelectionChanged.connect(self.changed_item)
    self.connect_button.clicked.connect(self.connect_ant_sensor)

  def changed_item(self):
    #item is QListWidgetItem
    item = self.items.selectedItems()
    if len(item) > 0:
      self.selected_ant_id = int(self.items.itemWidget(item[0]).ant_id)

  def resizeEvent(self, event):
    super().resizeEvent(event)
    h = self.size().height()
    self.connect_button.setFixedHeight(int(h/6))
    #for i in range(self.items.count()):
    #  self.items.itemWidget(self.items.item(i)).setFixedHeight(int(h/3))

  def connect_ant_sensor(self):
    print('connect', self.selected_ant_id)
    if self.selected_ant_id == None: return
    self.ant.connectAntSensor(\
      self.ant_name, #name
      int(self.selected_ant_id), #ID
      self.type[int(self.selected_ant_id)][0], #type
      self.type[int(self.selected_ant_id)][1], #connection status
    )
    self.timer.stop()

    index = self.config.gui.gui_config.G_GUI_INDEX['ANT+Top']
    self.parent.widget(index).update_button_label()
    self.config.gui.change_menu_page(index)

  def on_back_menu(self):
    self.timer.stop()
    self.ant.searcher.stopSearch()
    #button update
    index = self.config.gui.gui_config.G_GUI_INDEX['ANT+Top']
    self.parent.widget(index).update_button_label()

  def display(self, ant_name):
    self.selected_ant_id = None
    self.items.clear()
    self.type.clear()
    self.ant_name = ant_name
    self.ant.searcher.search(self.ant_name)
    self.timer.start(self.config.G_DRAW_INTERVAL)

  def update_display(self):
    self.itemLabel = self.ant.searcher.getSearchList()
    for ant_id, ant_type_array in self.itemLabel.items():
      ant_id_str = '{0:05d}'.format(ant_id)
      add = True
      for i in range(self.items.count()):
        if ant_id_str == self.items.itemWidget(self.items.item(i)).ant_id:
          add = False
      if add: 
        self.type[ant_id] = ant_type_array
        ant_item = ANTListItemWidget(self)
        status = ''
        if ant_type_array[1]: status = ' (connected)'
        ant_item.set_ant_id(ant_id_str, self.config.G_ANT['TYPE_NAME'][ant_type_array[0]]+status)

        list_item = QtWidgets.QListWidgetItem(self.items)
        list_item.setSizeHint(ant_item.sizeHint())
        self.items.addItem(list_item)
        self.items.setItemWidget(list_item, ant_item)
        #ant_item.set_icon('img/ant.png')


class ANTListItemWidget(QtWidgets.QWidget):
  
  def __init__ (self, parent):
    super(ANTListItemWidget, self).__init__(parent)
    self.parent = parent

    self.setContentsMargins(0,0,0,0)
    self.setFocusPolicy(QtCore.Qt.StrongFocus)

    self.dummy_px = QtGui.QPixmap(20,20)
    self.dummy_px.fill(QtGui.QColor("#006600"))
    self.icon = QtWidgets.QLabel()
    self.icon.setPixmap(self.dummy_px)

    self.ant_type_label = QtWidgets.QLabel()
    #self.ant_type_label.setStyleSheet("background-color: #99CCFF;")
    self.ant_type_label.setMargin(0)
    self.ant_type_label.setContentsMargins(0,0,0,0)
    self.ant_id_label = QtWidgets.QLabel()
    #self.ant_id_label.setStyleSheet("background-color: #99FFCC;")
    self.ant_id_label.setMargin(0)
    self.ant_id_label.setContentsMargins(0,0,0,0)

    self.inner_layout = QtWidgets.QVBoxLayout()
    #self.inner_layout.setContentsMargins(0,0,0,0)
    #self.inner_layout.setSpacing(0)
    self.inner_layout.addWidget(self.ant_type_label)
    self.inner_layout.addWidget(self.ant_id_label)

    self.outer_layout = QtWidgets.QHBoxLayout()
    #self.outer_layout.setContentsMargins(0,0,0,0)
    #self.outer_layout.setSpacing(0)
    self.outer_layout.addWidget(self.icon)
    self.outer_layout.addLayout(self.inner_layout, QtCore.Qt.AlignLeft)

    self.setLayout(self.outer_layout)

  def keyPressEvent(self, e):
    if e.key() == QtCore.Qt.Key_Space:
      self.parent.selected_ant_id = int(self.ant_id)
      self.parent.connect_ant_sensor()

  def set_ant_id(self, ant_id, ant_type):
    self.ant_id = ant_id
    self.ant_id_label.setText('   ID:'+self.ant_id)
    self.ant_type_label.setText(ant_type)
    
  def set_icon(self, image_path):
    self.icon.setPixmap(QtGui.QPixmap(image_path).scaled(30,30))

  def resizeEvent(self, event):
    h = self.size().height()
    for text, fsize in zip([self.ant_type_label, self.ant_id_label], [int(h*0.4), int(h*0.3)]):
      q = text.font()
      q.setPixelSize(fsize)
      text.setFont(q)

