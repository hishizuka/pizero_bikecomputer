import sys
from datetime import datetime
import signal
import io

import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtGui as QtGui

from modules.gui_config import GUI_Config
from modules.pyqt.pyqt_style import PyQtStyle
import modules.pyqt.pyqt_graph as pyqt_graph
import modules.pyqt.pyqt_multiscan_widget as pyqt_multiscan
from modules.pyqt.pyqt_values_widget import ValuesWidget
from modules.pyqt.menu.pyqt_menu_widget import TopMenuWidget, ANTMenuWidget, ANTDetailWidget
from modules.pyqt.menu.pyqt_adjust_widget import AdjustAltitudeWidget, AdjustWheelCircumferenceWidget
from modules.pyqt.menu.pyqt_debug_widget import DebugLogViewerWidget

class MyWindow(QtWidgets.QMainWindow):
  config = None
  gui = None

  def __init__(self, parent=None):
    #super(QtWidgets.QMainWindow, self).__init__(parent, flags=QtCore.Qt.FramelessWindowHint)
    super(QtWidgets.QMainWindow, self).__init__(parent)
    print("Qt version:", QtCore.QT_VERSION_STR)
    #self.grabGesture(QtCore.Qt.SwipeGesture)
  
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
  
  #override from QtWidget
  #def keyPressEvent(self, e):
  #  if self.gui != None:
  #    self.gui.send_key(e)


class GUI_PyQt(QtCore.QObject):

  config = None
  gui_config = None
  logger = None
  app = None
  style = None

  stack_widget = None
  main_page = None
  main_page_index = 0
  performance_graph_widget  = None
  course_profile_graph_widget = None
  simple_map_widget = None
  multi_scan_widget = None

  display_buffer = None
  
  #for long press
  lap_button_count = 0
  start_button_count = 0
  signal_next_button = QtCore.pyqtSignal(int)
  signal_prev_button = QtCore.pyqtSignal(int)
  signal_menu_button = QtCore.pyqtSignal(int)
  signal_menu_back_button = QtCore.pyqtSignal()

  def __init__(self, config):
    super().__init__()
    self.config = config
    self.config.gui = self
    self.gui_config = GUI_Config(config)
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

    if self.config.G_DISPLAY in ['MIP', 'Papirus']:
      self.display_buffer = QtCore.QBuffer()

    self.init_window()

  def quit_by_ctrl_c(self, signal, frame):
    self.quit()
  
  def quit(self):
    self.config.quit()
    self.app.quit()

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

    QtGui.QFontDatabase.addApplicationFont('fonts/Yantramanav/Yantramanav-Black.ttf')
    self.stack_widget.setStyleSheet("font-family: Yantramanav")

    #QtGui.QFontDatabase.addApplicationFont('fonts/mplus-TESTFLIGHT-063/mplus-1p-black.ttf')
    #self.stack_widget.setStyleSheet("font-family: M+ 1p black")

    QtGui.QFontDatabase.addApplicationFont('fonts/source-han-sans/SourceHanSansJP-Bold.otf')
    #self.stack_widget.setStyleSheet("font-family: 源ノ角ゴシック JP")

    #http://pm85122.onamae.jp/851Gkktt.html
    #QtGui.QFontDatabase.addApplicationFont('fonts/851Gkktt_005.ttf')
    #self.stack_widget.setStyleSheet("font-family: 851Gkktt")

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
        if k == "PERFORMANCE_GRAPH":
          self.performance_graph_widget = pyqt_graph.PerformanceGraphWidget(self.main_page, self.config)
          self.main_page.addWidget(self.performance_graph_widget)
        elif k == "COURSE_PROFILE_GRAPH":
          self.course_profile_graph_widget = pyqt_graph.CourseProfileGraphWidget(self.main_page, self.config)
          self.main_page.addWidget(self.course_profile_graph_widget)
        elif k == "SIMPLE_MAP":
          self.simple_map_widget = pyqt_graph.SimpleMapWidget(self.main_page, self.config)
          self.main_page.addWidget(self.simple_map_widget)
        elif k == "MULTI_SCAN":
          self.multi_scan_widget = pyqt_multiscan.MultiScanWidget(self.main_page, self.config)
          self.main_page.addWidget(self.multi_scan_widget)

    time_profile.append(datetime.now())

    #button
    self.button_box_widget = ButtonBoxWidget(self.main_widget, self.config)
    self.button_box_widget.start_button.clicked.connect(self.start_and_stop_quit)
    self.button_box_widget.lap_button.clicked.connect(self.lap_reset)
    self.button_box_widget.menu_button.clicked.connect(self.goto_menu)
    self.button_box_widget.scrollnext_button.clicked.connect(self.scroll_next)
    self.button_box_widget.scrollprev_button.clicked.connect(self.scroll_prev)

    #physical button
    self.signal_next_button.connect(self.scroll)
    self.signal_prev_button.connect(self.scroll)
    self.signal_menu_button.connect(self.change_menu_page)
    self.signal_menu_back_button.connect(self.change_menu_back)
   
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

    self.app.exec()  
    #exit this line
    #sys.exit(self.app.exec_())

  #for stack_widget page transition
  def on_change_main_page(self,index):
    self.main_page.widget(self.main_page_index).stop()
    self.main_page.widget(index).start()
    self.main_page_index = index
  
  #def send_key(self, e):
  #  if e.key() == QtCore.Qt.Key_N:
  #    self.scroll_next()
 
  def press_key(self, key):
    e_press = QtGui.QKeyEvent(QtCore.QEvent.KeyPress, key, QtCore.Qt.NoModifier, None)
    e_release = QtGui.QKeyEvent(QtCore.QEvent.KeyRelease, key, QtCore.Qt.NoModifier, None)
    QtCore.QCoreApplication.postEvent(QtWidgets.QApplication.focusWidget(), e_press)
    QtCore.QCoreApplication.postEvent(QtWidgets.QApplication.focusWidget(), e_release)

  def press_tab(self):
    #self.press_key(QtCore.Qt.Key_Tab)
    self.main_page.widget(self.main_page_index).focusPreviousChild()

  def press_down(self):
    #self.press_key(QtCore.Qt.Key_Down)
    self.main_page.widget(self.main_page_index).focusNextChild()

  def press_space(self):
    self.press_key(QtCore.Qt.Key_Space)
  
  def scroll_next(self):
    self.signal_next_button.emit(1)

  def scroll_prev(self):
    self.signal_next_button.emit(-1)
  
  def scroll_menu(self):
    i = self.stack_widget.currentIndex()
    if i == 1:
      #goto_menu:
      self.signal_menu_button.emit(2)
    elif i >= 2:
      #back
      self.signal_menu_back_button.emit()
  
  def dummy(self):
    pass

  def scroll(self, delta):
    mod_index = self.main_page.currentIndex()
    while True:
      mod_index += delta
      if mod_index == self.main_page.count(): mod_index = 0
      elif mod_index == -1: mod_index = self.main_page.count() - 1
      if self.main_page.widget(mod_index).onoff == True: break
    self.on_change_main_page(mod_index)
    self.main_page.setCurrentIndex(mod_index)

  def get_screenshot(self):
    date = datetime.now()
    filename = date.strftime('%Y-%m-%d_%H-%M-%S.jpg')
    p = self.stack_widget.grab()
    p.save(self.config.G_SCREENSHOT_DIR+filename, 'jpg')
 
  def draw_display(self):
    if not self.config.logger.sensor.sensor_spi.send_display:
      return
    p = self.stack_widget.grab()
    self.display_buffer.open(QtCore.QBuffer.ReadWrite)
    p.save(self.display_buffer, 'BMP')
    self.config.logger.sensor.sensor_spi.update(io.BytesIO(self.display_buffer.data()))
    self.display_buffer.close()
  
  def lap_reset(self):
    if self.button_box_widget.lap_button.isDown():
      if self.button_box_widget.lap_button._state == 0:
        self.button_box_widget.lap_button._state = 1
      else:
        self.lap_button_count += 1
        print('lap button pressing : ', self.lap_button_count)
        if self.lap_button_count == self.config.G_BUTTON_LONG_PRESS:
          print('reset')
          self.logger.reset_count()
          self.simple_map_widget.reset_track()
    elif self.button_box_widget.lap_button._state == 1:
      self.button_box_widget.lap_button._state = 0
      self.lap_button_count = 0
    else:
      self.logger.count_laps()

  def start_and_stop_quit(self):
    if self.button_box_widget.start_button.isDown():
      if self.button_box_widget.start_button._state == 0:
        self.button_box_widget.start_button._state = 1
      else:
        self.start_button_count += 1
        print('start button pressing : ', self.start_button_count)
        if self.start_button_count == self.config.G_BUTTON_LONG_PRESS:
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
    #in mip display, setIcon seems not to occur paint event
    self.draw_display()

  def brightness_control(self):
    self.config.logger.sensor.sensor_spi.brightness_control()

  def change_menu_page(self, page):
    self.stack_widget.setCurrentIndex(page)
    
  def change_menu_back(self):
    w = self.stack_widget.currentWidget()
    w.back()

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

