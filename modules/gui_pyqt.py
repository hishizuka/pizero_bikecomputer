import sys
import os
from datetime import datetime
import signal
import numpy as np

USE_PYQT6 = False
try:
  import PyQt6.QtCore as QtCore
  import PyQt6.QtWidgets as QtWidgets
  import PyQt6.QtGui as QtGui
  USE_PYQT6 = True
except:
  import PyQt5.QtCore as QtCore
  import PyQt5.QtWidgets as QtWidgets
  import PyQt5.QtGui as QtGui

from modules.gui_config import GUI_Config
from modules.pyqt.pyqt_style import PyQtStyle
import modules.pyqt.pyqt_graph as pyqt_graph
import modules.pyqt.pyqt_graph_debug as pyqt_graph_debug
import modules.pyqt.pyqt_multiscan_widget as pyqt_multiscan
from modules.pyqt.pyqt_values_widget import ValuesWidget
from modules.pyqt.menu.pyqt_menu_widget import TopMenuWidget, ANTMenuWidget, ANTDetailWidget
from modules.pyqt.menu.pyqt_adjust_widget import AdjustAltitudeWidget, AdjustWheelCircumferenceWidget
from modules.pyqt.menu.pyqt_debug_widget import DebugLogViewerWidget
from modules.pyqt.pyqt_cuesheet_widget import CueSheetWidget

class MyWindow(QtWidgets.QMainWindow):
  config = None
  gui = None

  def __init__(self, parent=None):
    #super(QtWidgets.QMainWindow, self).__init__(parent, flags=QtCore.Qt.FramelessWindowHint)
    super(QtWidgets.QMainWindow, self).__init__(parent)
    print("Qt version:", QtCore.QT_VERSION_STR)
  
  def set_config(self, config):
    self.config = config
  
  def set_gui(self, gui):
    self.gui = gui

  #override from QtWidget
  def closeEvent(self, event):
    self.config.quit()

  #override from QtWidget
  def paintEvent(self, event):
    if self.gui != None:
      self.gui.draw_display()


class GUI_PyQt(QtCore.QObject):

  config = None
  gui_config = None
  logger = None
  app = None
  style = None

  stack_widget = None
  main_page = None
  main_page_index = 0
  altitude_graph_widget = None
  acc_graph_widget = None
  performance_graph_widget  = None
  course_profile_graph_widget = None
  simple_map_widget = None
  cuesheet_widget = None
  multi_scan_widget = None

  #for long press
  lap_button_count = 0
  start_button_count = 0

  #signal
  signal_next_button = QtCore.pyqtSignal(int)
  signal_prev_button = QtCore.pyqtSignal(int)
  signal_menu_button = QtCore.pyqtSignal(int)
  signal_menu_back_button = QtCore.pyqtSignal()
  signal_get_screenshot = QtCore.pyqtSignal()

  screen_shape = None
  screen_image = None
  remove_bytes = 0
  old_pyqt = False
  bufsize = 0

  def __init__(self, config):
    super().__init__()
    self.config = config
    self.config.gui = self
    self.gui_config = GUI_Config(config)
    self.gui_config.set_qt5_or_qt6_constants(USE_PYQT6)
    #from other program, call self.config.gui.style
    self.style = PyQtStyle()
    self.logger = self.config.logger
    try:
      signal.signal(signal.SIGTERM, self.quit_by_ctrl_c)
      signal.signal(signal.SIGINT, self.quit_by_ctrl_c)
      signal.signal(signal.SIGQUIT, self.quit_by_ctrl_c)
      signal.signal(signal.SIGHUP, self.quit_by_ctrl_c)
    except:
      pass

    self.init_window()
  
  def quit_by_ctrl_c(self, signal, frame):
    self.quit()

  def quit(self):
    self.app.quit()
    if not USE_PYQT6:
      self.config.quit()

  def init_window(self):
    self.app = QtWidgets.QApplication(sys.argv)

    self.icon_dir = ""
    if self.config.G_IS_RASPI:
      self.icon_dir = self.config.G_INSTALL_PATH 

    #self.main_window
    #  stack_widget
    #    splash_widget
    #    main_widget
    #      main_layout
    #        main_page
    #        button_box_widget
    #    menu_widget

    time_profile = [datetime.now(),] #for time profile
    self.main_window = MyWindow()
    self.main_window.set_config(self.config)
    self.main_window.set_gui(self)
    self.main_window.setWindowTitle(self.config.G_PRODUCT)
    self.main_window.setMinimumSize(self.config.G_WIDTH, self.config.G_HEIGHT)
    self.main_window.show()
    self.set_color()

    #base stack_widget
    self.stack_widget = QtWidgets.QStackedWidget(self.main_window)
    self.main_window.setCentralWidget(self.stack_widget)
    self.stack_widget.setContentsMargins(0,0,0,0)

    #default font
    res = QtGui.QFontDatabase.addApplicationFont('fonts/Yantramanav/Yantramanav-Black.ttf')
    if res != -1:
      font_name = QtGui.QFontDatabase.applicationFontFamilies(res)[0]
      self.stack_widget.setStyleSheet("font-family: {}".format(font_name))
      print("add font:", font_name)

    #Additional font from setting.conf
    if self.config.G_FONT_FULLPATH != "":
      res = QtGui.QFontDatabase.addApplicationFont(self.config.G_FONT_FULLPATH)
      if res != -1:
        self.config.G_FONT_NAME = QtGui.QFontDatabase.applicationFontFamilies(res)[0]
        #self.stack_widget.setStyleSheet("font-family: {}".format(self.config.G_FONT_NAME))
        print("add font:", self.config.G_FONT_NAME)

    #self.stack_widget.setWindowFlags(QtCore.Qt.FramelessWindowHint)

    #elements
    #splash
    self.splash_widget = QtWidgets.QWidget(self.stack_widget)
    self.splash_widget.setContentsMargins(0,0,0,0)
    #main
    self.main_widget = QtWidgets.QWidget(self.stack_widget)
    self.main_widget.setContentsMargins(0,0,0,0)
    #menu top
    self.menu_widget = TopMenuWidget(self.stack_widget, "Settings", self.config)
    self.menu_widget.setContentsMargins(0,0,0,0)
    #ANT+ menu
    self.ant_menu_widget = ANTMenuWidget(self.stack_widget, "ANT+ Sensors", self.config)
    self.ant_menu_widget.setContentsMargins(0,0,0,0)
    #ANT+ detail
    self.ant_detail_widget = ANTDetailWidget(self.stack_widget, "ANT+ Detail", self.config)
    self.ant_detail_widget.setContentsMargins(0,0,0,0)
    #adjust altitude
    self.adjust_wheel_circumference_widget = AdjustWheelCircumferenceWidget(self.stack_widget, "Wheel Size (Circumference)", self.config)
    self.adjust_wheel_circumference_widget.setContentsMargins(0,0,0,0)
    #adjust altitude
    self.adjust_atitude_widget = AdjustAltitudeWidget(self.stack_widget, "Adjust Altitude", self.config)
    self.adjust_atitude_widget.setContentsMargins(0,0,0,0)
    #Debug log viewer
    self.debug_log_viewer_widget = DebugLogViewerWidget(self.stack_widget, "Debug Log Viewer", self.config)
    self.debug_log_viewer_widget.setContentsMargins(0,0,0,0)
    #integrate
    self.stack_widget.addWidget(self.splash_widget)
    self.stack_widget.addWidget(self.main_widget)
    self.stack_widget.addWidget(self.menu_widget)
    self.stack_widget.addWidget(self.ant_menu_widget)
    self.stack_widget.addWidget(self.ant_detail_widget)
    self.stack_widget.addWidget(self.adjust_wheel_circumference_widget)
    self.stack_widget.addWidget(self.adjust_atitude_widget)
    self.stack_widget.addWidget(self.debug_log_viewer_widget)
    self.stack_widget.setCurrentIndex(1)
 
    #main layout
    self.main_layout = QtWidgets.QVBoxLayout(self.main_widget)
    self.main_layout.setContentsMargins(0,0,0,0)
    self.main_layout.setSpacing(0)
    self.main_widget.setLayout(self.main_layout)
 
    #main Widget
    self.main_page = QtWidgets.QStackedWidget(self.main_widget)
    self.main_page.setContentsMargins(0,0,0,0)

    time_profile.append(datetime.now())
    
    for k in self.gui_config.G_LAYOUT:
      if not self.gui_config.G_LAYOUT[k]["STATUS"]:
        continue
      if "LAYOUT" in self.gui_config.G_LAYOUT[k]:
        self.main_page.addWidget(
          ValuesWidget(self.main_page, self.config, self.gui_config.G_LAYOUT[k]["LAYOUT"])
          )
      else:
        if k == "ALTITUDE_GRAPH" and 'i2c_baro_temp' in self.config.logger.sensor.sensor_i2c.sensor:
          self.altitude_graph_widget = pyqt_graph_debug.AltitudeGraphWidget(self.main_page, self.config)
          self.main_page.addWidget(self.altitude_graph_widget)
        elif k == "ACC_GRAPH" and self.config.logger.sensor.sensor_i2c.motion_sensor['ACC']:
          self.acc_graph_widget = pyqt_graph_debug.AccelerationGraphWidget(self.main_page, self.config)
          self.main_page.addWidget(self.acc_graph_widget)
        elif k == "PERFORMANCE_GRAPH" and self.config.G_ANT['STATUS']:
          self.performance_graph_widget = pyqt_graph.PerformanceGraphWidget(self.main_page, self.config)
          self.main_page.addWidget(self.performance_graph_widget)
        elif k == "COURSE_PROFILE_GRAPH" and os.path.exists(self.config.G_COURSE_FILE) and self.config.G_COURSE_INDEXING:
          self.course_profile_graph_widget = pyqt_graph.CourseProfileGraphWidget(self.main_page, self.config)
          self.main_page.addWidget(self.course_profile_graph_widget)
        elif k == "SIMPLE_MAP":
          self.simple_map_widget = pyqt_graph.SimpleMapWidget(self.main_page, self.config)
          self.main_page.addWidget(self.simple_map_widget)
        elif k == "CUESHEET" and len(self.config.logger.course.point_name) > 0 and self.config.G_COURSE_INDEXING and \
          self.config.G_CUESHEET_DISPLAY_NUM > 0:
          self.cuesheet_widget = pyqt_graph.CueSheetWidget(self.main_page, self.config)
          self.main_page.addWidget(self.cuesheet_widget)
        elif k == "MULTI_SCAN" and self.config.G_ANT['STATUS']:
          self.multi_scan_widget = pyqt_multiscan.MultiScanWidget(self.main_page, self.config)
          self.main_page.addWidget(self.multi_scan_widget)

    time_profile.append(datetime.now())

    #button
    self.button_box_widget = ButtonBoxWidget(self.main_widget, self.config)
    self.button_box_widget.start_button.clicked.connect(self.gui_start_and_stop_quit)
    self.button_box_widget.lap_button.clicked.connect(self.gui_lap_reset)
    self.button_box_widget.menu_button.clicked.connect(self.goto_menu)
    self.button_box_widget.scrollnext_button.clicked.connect(self.scroll_next)
    self.button_box_widget.scrollprev_button.clicked.connect(self.scroll_prev)

    #physical button
    self.signal_next_button.connect(self.scroll)
    self.signal_prev_button.connect(self.scroll)
    self.signal_menu_button.connect(self.change_menu_page)
    self.signal_menu_back_button.connect(self.change_menu_back)
    #other
    self.signal_get_screenshot.connect(self.screenshot)
   
    #integrate main_layout
    self.main_layout.addWidget(self.main_page)
    if not self.config.G_AVAILABLE_DISPLAY[self.config.G_DISPLAY]['touch']:
      self.button_box_widget.setVisible(False)
    else:
      self.main_layout.addWidget(self.button_box_widget)

    time_profile.append(datetime.now()) #for time profile
    
    #self.main_window.show()

    #fullscreen
    if self.config.G_FULLSCREEN:
      self.main_window.showFullScreen()

    self.on_change_main_page(self.main_page_index)
    
    diff_label = ["base","widget","button"]
    print("  gui_pyqt:")
    for i in range(len(time_profile)):
      if i == 0: continue
      t = "{0:.4f}".format((time_profile[i]-time_profile[i-1]).total_seconds())
      print("   ",'{:<13}'.format(diff_label[i-1]), ":", t)

    #for draw_display
    p = self.stack_widget.grab().toImage().convertToFormat(self.gui_config.format)
    #PyQt 5.11(Buster) or 5.15(Bullseye)
    qt_version = (QtCore.QT_VERSION_STR).split(".")
    if(qt_version[0] == '5' and qt_version[1] == '11'):
      self.bufsize = p.bytesPerLine()*p.height() #PyQt 5.11(Buster)
    else:  
      self.bufsize = p.sizeInBytes() #PyQt 5.15 or lator (Bullseye)
    
    self.screen_shape, self.remove_bytes = self.gui_config.get_screen_shape(p)
 
    self.app.exec()  
  
  #for stack_widget page transition
  def on_change_main_page(self,index):
    self.main_page.widget(self.main_page_index).stop()
    self.main_page.widget(index).start()
    self.main_page_index = index
  
  def start_and_stop_manual(self):
    self.logger.start_and_stop_manual()

  def count_laps(self):
    self.logger.count_laps()
  
  def reset_count(self):
    self.logger.reset_count()
 
  def press_key(self, key):
    e_press = QtGui.QKeyEvent(self.gui_config.key_press, key, self.gui_config.no_modifier, None)
    e_release = QtGui.QKeyEvent(self.gui_config.key_release, key, self.gui_config.no_modifier, None)
    QtCore.QCoreApplication.postEvent(QtWidgets.QApplication.focusWidget(), e_press)
    QtCore.QCoreApplication.postEvent(QtWidgets.QApplication.focusWidget(), e_release)

  def press_tab(self):
    #self.press_key(QtCore.Qt.Key_Tab)
    self.main_page.widget(self.main_page_index).focusPreviousChild()

  def press_down(self):
    #self.press_key(QtCore.Qt.Key_Down)
    self.main_page.widget(self.main_page_index).focusNextChild()

  def press_space(self):
    self.press_key(self.gui_config.key_space)
  
  def scroll_next(self):
    self.signal_next_button.emit(1)

  def scroll_prev(self):
    self.signal_next_button.emit(-1)
  
  def enter_menu(self):
    i = self.stack_widget.currentIndex()
    if i == 1:
      #goto_menu:
      self.signal_menu_button.emit(2)
    elif i >= 2:
      #back
      self.back_menu()
  
  def back_menu(self):
    self.signal_menu_back_button.emit()
  
  def change_mode(self):
    #check MAIN
    if self.stack_widget.currentIndex() != 1:
      return
    self.config.change_mode()

  def map_move_x_plus(self):
    self.map_method("move_x_plus")

  def map_move_x_minus(self):
    self.map_method("move_x_minus")

  def map_move_y_plus(self):
    self.map_method("move_y_plus")

  def map_move_y_minus(self):
    self.map_method("move_y_minus")

  def map_change_move(self):
    self.map_method("change_move")
  
  def map_zoom_plus(self):
    self.map_method("zoom_plus")

  def map_zoom_minus(self):
    self.map_method("zoom_minus")
  
  def map_search_route(self):
    self.map_method("search_route")

  def map_method(self, mode):
    w = self.main_page.widget(self.main_page.currentIndex())
    widget_name = w.__class__.__name__
    if widget_name == 'SimpleMapWidget':
      eval('w.signal_'+mode+'.emit()')

  def dummy(self):
    pass

  def scroll(self, delta):
    mod_index = (self.main_page.currentIndex() + delta + self.main_page.count()) % self.main_page.count()
    self.on_change_main_page(mod_index)
    self.main_page.setCurrentIndex(mod_index)

  def get_screenshot(self):
    self.signal_get_screenshot.emit()

  def screenshot(self):
    date = datetime.now()
    filename = date.strftime('%Y-%m-%d_%H-%M-%S.png')
    print("screenshot:", filename)
    p = self.stack_widget.grab()
    p.save(self.config.G_SCREENSHOT_DIR+filename, 'png')
 
  def draw_display(self):
    if not self.config.logger.sensor.sensor_spi.send_display or self.stack_widget == None:
      return

    #self.config.check_time("draw_display start")
    p = self.stack_widget.grab().toImage().convertToFormat(self.gui_config.format)
    
    #self.config.check_time("grab")
    ptr = p.constBits()
    if(ptr == None):
      return
  
    if(self.screen_image != None and p == self.screen_image):
      return
    self.screen_image = p

    ptr.setsize(self.bufsize)
  
    if(self.remove_bytes > 0):
      buf = np.frombuffer(ptr, dtype=np.uint8).reshape((p.height(), self.remove_bytes+int(p.width()/8)))
      buf = buf[:, :-self.remove_bytes]
    else:
      buf = np.frombuffer(ptr, dtype=np.uint8).reshape(self.screen_shape)

    self.config.logger.sensor.sensor_spi.update(buf)
    #self.config.check_time("draw_display end")
  
  def gui_lap_reset(self):
    if self.button_box_widget.lap_button.isDown():
      if self.button_box_widget.lap_button._state == 0:
        self.button_box_widget.lap_button._state = 1
      else:
        self.lap_button_count += 1
        print('lap button pressing : ', self.lap_button_count)
        if self.lap_button_count == self.config.button_config.G_BUTTON_LONG_PRESS:
          print('reset')
          self.logger.reset_count()
          self.simple_map_widget.reset_track()
          self.lap_button_count = 0
    elif self.button_box_widget.lap_button._state == 1:
      self.button_box_widget.lap_button._state = 0
      self.lap_button_count = 0
    else:
      self.logger.count_laps()

  def gui_start_and_stop_quit(self):
    if self.button_box_widget.start_button.isDown():
      if self.button_box_widget.start_button._state == 0:
        self.button_box_widget.start_button._state = 1
      else:
        self.start_button_count += 1
        print('start button pressing : ', self.start_button_count)
        if self.start_button_count == self.config.button_config.G_BUTTON_LONG_PRESS:
          print('quit or poweroff')
          self.quit()
    elif self.button_box_widget.start_button._state == 1:
      self.button_box_widget.start_button._state = 0
      self.start_button_count = 0
    else:
      self.logger.start_and_stop_manual()

  def change_start_stop_button(self, status):
    icon = QtGui.QIcon(self.icon_dir+'img/pause_white.png')
    if status == "START":
      icon = QtGui.QIcon(self.icon_dir+'img/next_white.png')
    self.button_box_widget.start_button.setIcon(icon)

  def brightness_control(self):
    self.config.logger.sensor.sensor_spi.brightness_control()

  def turn_on_off_light(self):
    self.config.logger.sensor.sensor_ant.set_light_mode("ON_OFF_FLASH_LOW")

  def change_menu_page(self, page):
    self.stack_widget.setCurrentIndex(page)
    
  def change_menu_back(self):
    self.stack_widget.currentWidget().back()

  def goto_menu(self):
    self.change_menu_page(self.gui_config.G_GUI_INDEX['menu'])

  def set_color(self, daylight=True):
    if daylight:
      self.main_window.setStyleSheet("color: black; background-color: white")
    else:
      self.main_window.setStyleSheet("color: white; background-color: #222222")


#################################
# Button
#################################

class ButtonBoxWidget(QtWidgets.QWidget):

  config = None

  def __init__(self, parent, config):
    self.config = config
    QtWidgets.QWidget.__init__(self, parent=parent)
    self.setup_ui()

  def setup_ui(self):
    
    self.setContentsMargins(0,0,0,0)
    self.setStyleSheet("background-color: #CCCCCC")
    self.show()
    self.setAutoFillBackground(True)

    self.icon_dir = ""
    if self.config.G_IS_RASPI:
      self.icon_dir = self.config.G_INSTALL_PATH 
    
    #self.start_button = QtWidgets.QPushButton(QtGui.QIcon(self.icon_dir+'img/next_white.png'),"")
    self.start_button = QtWidgets.QPushButton(QtGui.QIcon(self.icon_dir+'img/pause_white.png'),"")
    self.lap_button = QtWidgets.QPushButton(QtGui.QIcon(self.icon_dir+'img/lap_white.png'),"")
    self.menu_button = QtWidgets.QPushButton(QtGui.QIcon(self.icon_dir+'img/menu.png'),"")
    self.scrollnext_button = QtWidgets.QPushButton(QtGui.QIcon(self.icon_dir+'img/nextarrow_black.png'),"")
    self.scrollprev_button = QtWidgets.QPushButton(QtGui.QIcon(self.icon_dir+'img/backarrow_black.png'),"")

    self.scrollprev_button.setFixedSize(60,30)
    self.lap_button.setFixedSize(50,30)
    self.menu_button.setFixedSize(50,30)
    self.start_button.setFixedSize(50,30)
    self.scrollnext_button.setFixedSize(60,30)

    #long press 
    for button in [self.start_button, self.lap_button]:
      button.setAutoRepeat(True)
      button.setAutoRepeatDelay(1000)
      button.setAutoRepeatInterval(1000)
      button._state = 0
    
    self.start_button.setStyleSheet(self.config.gui.style.G_GUI_PYQT_buttonStyle_timer)
    self.lap_button.setStyleSheet(self.config.gui.style.G_GUI_PYQT_buttonStyle_timer)
    self.menu_button.setStyleSheet(self.config.gui.style.G_GUI_PYQT_buttonStyle_gotoMenu)
    self.scrollnext_button.setStyleSheet(self.config.gui.style.G_GUI_PYQT_buttonStyle_navi)
    self.scrollprev_button.setStyleSheet(self.config.gui.style.G_GUI_PYQT_buttonStyle_navi)

    button_layout = QtWidgets.QHBoxLayout()
    button_layout.setContentsMargins(0,5,0,5)
    button_layout.setSpacing(0)
    button_layout.addWidget(self.scrollprev_button)
    button_layout.addWidget(self.lap_button)
    button_layout.addWidget(self.menu_button)
    button_layout.addWidget(self.start_button)
    button_layout.addWidget(self.scrollnext_button)
    
    self.setLayout(button_layout)

