import numpy as np

try:
  import PyQt6.QtCore as QtCore
  import PyQt6.QtWidgets as QtWidgets
  import PyQt6.QtGui as QtGui
except:
  import PyQt5.QtCore as QtCore
  import PyQt5.QtWidgets as QtWidgets
  import PyQt5.QtGui as QtGui

import pyqtgraph as pg
from qasync import asyncSlot

from modules.pyqt.pyqt_screen_widget import ScreenWidget

pg.setConfigOptions(antialias=True)
pg.setConfigOption('background', 'w')
pg.setConfigOption('foreground', 'k')


class BaseMapWidget(ScreenWidget):

  #map button
  button = {}
  button_name = ['lock','zoomup','zoomdown','left','right','up','down','go']
  lock_status = True
  button_press_count = {}

  #show range from zoom
  zoom = 2000 #[m] #for CourseProfileGraphWidget
  zoomlevel = 13 #for MapWidget

  #load course
  course_loaded = False

  #course points
  course_points_label = []

  #signal for physical button
  signal_move_x_plus = QtCore.pyqtSignal()
  signal_move_x_minus = QtCore.pyqtSignal()
  signal_move_y_plus = QtCore.pyqtSignal()
  signal_move_y_minus = QtCore.pyqtSignal()
  signal_zoom_plus = QtCore.pyqtSignal()
  signal_zoom_minus = QtCore.pyqtSignal()
  signal_change_move = QtCore.pyqtSignal()

  #for change_move
  move_adjust_mode = False
  move_factor = 1.0

  def init_extra(self):
    self.gps_values = self.config.logger.sensor.values['GPS']
    self.gps_sensor = self.config.logger.sensor.sensor_gps
    
    self.signal_move_x_plus.connect(self.move_x_plus)
    self.signal_move_x_minus.connect(self.move_x_minus)
    self.signal_move_y_plus.connect(self.move_y_plus)
    self.signal_move_y_minus.connect(self.move_y_minus)
    self.signal_zoom_plus.connect(self.zoom_plus)
    self.signal_zoom_minus.connect(self.zoom_minus)
    self.signal_change_move.connect(self.change_move)
  
  def setup_ui_extra(self):
    #main graph from pyqtgraph 
    self.plot = pg.PlotWidget()
    self.plot.setBackground(None)
    self.plot.hideAxis('left')
    self.plot.hideAxis('bottom')
    
    #current point
    self.current_point = pg.ScatterPlotItem(pxMode=True)
    self.point_color = {
      #'fix':pg.mkBrush(color=(0,0,160,128)), 
      'fix':pg.mkBrush(color=(0,0,255)),
      #'lost':pg.mkBrush(color=(96,96,96,128))
      'lost':pg.mkBrush(color=(170,170,170))
      }
    self.point = {
      'pos': [np.nan, np.nan],
      'size': 20,
      'pen': {'color': 'w', 'width': 2},
      'brush':self.point_color['lost']
      }
    
    #self.plot.setMouseEnabled(x=False, y=False)
    #pg.setConfigOptions(antialias=True)

    #make buttons
    self.button['lock'] = QtWidgets.QPushButton("L")
    self.button['zoomup'] = QtWidgets.QPushButton("+")
    self.button['zoomdown'] = QtWidgets.QPushButton("-")
    self.button['left'] = QtWidgets.QPushButton("←")
    self.button['right'] = QtWidgets.QPushButton("→")
    self.button['up'] = QtWidgets.QPushButton("↑")
    self.button['down'] = QtWidgets.QPushButton("↓")
    self.button['go'] = QtWidgets.QPushButton("Go")
    for b in self.button_name:
      self.button[b].setStyleSheet(self.config.gui.style.G_GUI_PYQT_buttonStyle_map)

    self.button['lock'].clicked.connect(self.switch_lock)
    self.button['right'].clicked.connect(self.move_x_plus)
    self.button['left'].clicked.connect(self.move_x_minus)
    self.button['up'].clicked.connect(self.move_y_plus)
    self.button['down'].clicked.connect(self.move_y_minus)
    self.button['zoomdown'].clicked.connect(self.zoom_minus)
    self.button['zoomup'].clicked.connect(self.zoom_plus)

    #long press 
    for key in ['lock']:
      self.button[key].setAutoRepeat(True)
      self.button[key].setAutoRepeatDelay(1000)
      self.button[key].setAutoRepeatInterval(1000)
      self.button[key]._state = 0
      self.button_press_count[key] = 0

    self.get_max_zoom()
  
  def make_item_layout(self):
    self.item_layout = {}

  def add_extra(self):
    pass

  #override disable
  def set_minimum_size(self):
    pass

  #for expanding row
  def resize_extra(self):
    n = self.layout.rowCount()
    h = int(self.size().height()/n)
    for i in range(n):
      self.layout.setRowMinimumHeight(i, h)

  def set_border(self):
    self.max_height = 1
    self.max_width = 3

  #def set_font_size(self):
  #  self.font_size = int(length / 8)

  def lock_off(self):
    self.lock_status = False

  def lock_on(self):
    self.lock_status = True

  def switch_lock(self):
    if self.lock_status:
      self.lock_off()
    else:
      self.lock_on()

  def change_move(self):
    if not self.move_adjust_mode:
      self.move_factor = 32
      self.move_adjust_mode = True
    else:
      self.move_factor = 1.0
      self.move_adjust_mode = False

  @asyncSlot()
  async def move_x_plus(self):
    await self.move_x(+self.zoom/2)

  @asyncSlot()
  async def move_x_minus(self):
    await self.move_x(-self.zoom/2)

  @asyncSlot()
  async def move_y_plus(self):
    await self.move_y(+self.zoom/2)

  @asyncSlot()
  async def move_y_minus(self):
    await self.move_y(-self.zoom/2)

  async def move_x(self, delta):
    self.move_pos['x'] += delta
    await self.update_extra()

  async def move_y(self, delta):
    self.move_pos['y'] += delta
    await self.update_extra()

  @asyncSlot()
  async def zoom_plus(self):
    self.zoom /= 2
    self.zoomlevel += 1
    await self.update_extra()
    
  @asyncSlot()
  async def zoom_minus(self):
    self.zoom *= 2
    self.zoomlevel -= 1
    await self.update_extra()

  def get_max_zoom(self):

    if len(self.config.logger.course.distance) == 0:
      return
    
    if self.config.G_MAX_ZOOM != 0:
      return
    z = self.zoom
    dist = self.config.logger.course.distance[-1]
    if(z/1000 < dist):
      while(z/1000 < dist):
        z *= 2
      z *= 2
    else:
      while(z/1000 > dist):
        z /= 2
    self.config.G_MAX_ZOOM = z
    #print("MAX_ZOOM", self.config.G_MAX_ZOOM, dist)
  
  def load_course(self):
    pass
  
  async def update_extra(self):
    pass
