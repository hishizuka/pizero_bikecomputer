import os

try:
  import PyQt6.QtCore as QtCore
  import PyQt6.QtWidgets as QtWidgets
  import PyQt6.QtGui as QtGui
except:
  import PyQt5.QtCore as QtCore
  import PyQt5.QtWidgets as QtWidgets
  import PyQt5.QtGui as QtGui

from qasync import asyncSlot

from .pyqt_menu_widget import MenuWidget, ListWidget


class SystemMenuWidget(MenuWidget):
  
  def setup_menu(self):
    self.button = {}

    button_conf = (
      #Name(page_name), button_attribute, connected functions, layout
      ('Network', 'submenu', self.wifi_bt),
      ('Brightness', None, None),
      ('Language', None, None),
      ('Update', 'dialog', lambda: self.config.gui.show_dialog(self.config.update_application, 'Update')),
      ('Power Off', 'dialog', lambda: self.config.gui.show_dialog(self.config.poweroff, 'Power Off')),
      ('Debug Log', 'submenu', self.debug_log),
    )
    self.add_buttons(button_conf)
  
  def wifi_bt(self):
    self.change_page('Network', preprocess=True)

  def debug_log(self):
    self.change_page('Debug Log', preprocess=True)
  

class NetworkMenuWidget(MenuWidget):
  
  def setup_menu(self):
    self.button = {}
    wifi_bt_button_func_wifi = None
    wifi_bt_button_func_bt = None
    if self.config.G_IS_RASPI:
      wifi_bt_button_func_wifi = lambda: self.onoff_wifi_bt(True, 'Wifi')
      wifi_bt_button_func_bt = lambda: self.onoff_wifi_bt(True, 'Bluetooth')
    button_conf = (
      #Name(page_name), button_attribute, connected functions, layout
      ('Wifi', 'toggle', wifi_bt_button_func_wifi),
      ('Bluetooth', 'toggle', wifi_bt_button_func_bt),
      ('BT Tethering', 'submenu', self.bt_tething),
      ('IP Address', 'dialog', self.show_ip_address),
      ('Phone Msg', 'toggle', lambda: self.onoff_msg_server(True)),
    )
    self.add_buttons(button_conf)

    if not self.config.G_IS_RASPI or len(self.config.G_BT_ADDRESS) == 0:
      self.button['BT Tethering'].setEnabled(False)
      self.button['BT Tethering'].setProperty("style", "unavailable")

  def preprocess(self):
    #initialize toggle button status
    if self.config.G_IS_RASPI:
      self.onoff_wifi_bt(change=False, key='Wifi')
      self.onoff_wifi_bt(change=False, key='Bluetooth')
    self.onoff_msg_server(change=False)
    
  def onoff_wifi_bt(self, change=True, key=None):
    if change:
      self.config.onoff_wifi_bt(key)
    status = {}
    status['Wifi'], status['Bluetooth'] = self.config.get_wifi_bt_status()
    self.button[key].change_toggle(status[key])

  def bt_tething(self):
    self.change_page('BT Tethering')

  def show_ip_address(self):
    self.config.detect_network()
    #Button is OK only
    self.config.gui.show_dialog_ok_only(None, self.config.G_IP_ADDRESS)
  
  @asyncSlot()
  async def onoff_msg_server(self, change=True):
    if change:
      await self.config.network.server.on_off_server()
    self.button['Phone Msg'].change_toggle(self.config.network.server.status)


class BluetoothTetheringListWidget(ListWidget):

  def __init__(self, parent, page_name, config):
    #keys are used for item label
    self.settings = config.G_BT_ADDRESS
    super().__init__(parent=parent, page_name=page_name, config=config)
    
  def get_default_value(self):
    return self.config.G_BT_USE_ADDRESS
  
  async def button_func_extra(self):
    self.config.G_BT_USE_ADDRESS = self.selected_item.title_label.text()
    #reset map
    self.config.bluetooth_tethering()


class DebugLogViewerWidget(MenuWidget):

  def setup_menu(self):
    self.make_menu_layout(QtWidgets.QVBoxLayout)
    
    #self.scroll_area = QtWidgets.QScrollArea()
    #self.scroll_area.setWidgetResizable(True)
    try:
      self.debug_log_screen = QtWidgets.QTextEdit()
    except:
      #for old Qt (5.11.3 buster PyQt5 Package)
      QtGui.QTextEdit()
    self.debug_log_screen.setReadOnly(True)
    self.debug_log_screen.setLineWrapMode(self.config.gui.gui_config.qtextedit_nowrap)
    self.debug_log_screen.setHorizontalScrollBarPolicy(self.config.gui.gui_config.scrollbar_alwaysoff)
    #self.debug_log_screen.setVerticalScrollBarPolicy(self.config.gui.gui_config.scrollbar_alwaysoff)
    #QtWidgets.QScroller.grabGesture(self, QtWidgets.QScroller.LeftMouseButtonGesture)
    #self.scroll_area.setWidget(self.debug_log_screen) if USE_PYQT6 else self.menu_layout.addWidget(self.debug_log_screen)
    #self.menu_layout.addWidget(self.scroll_area)
    self.menu_layout.addWidget(self.debug_log_screen)

    self.menu.setLayout(self.menu_layout)

  def preprocess(self):
    debug_log = 'log/debug.txt'
    if not os.path.exists(debug_log):
      return
    f = open(debug_log)
    self.debug_log_screen.setText(f.read())
    f.close()
