import os
import numpy as np
import datetime

try:
  import PyQt6.QtCore as QtCore
  import PyQt6.QtWidgets as QtWidgets
  import PyQt6.QtGui as QtGui
except:
  import PyQt5.QtCore as QtCore
  import PyQt5.QtWidgets as QtWidgets
  import PyQt5.QtGui as QtGui

import pyqtgraph as pg

from PIL import Image
import math

from .pyqt_screen_widget import ScreenWidget
from .pyqt_cuesheet_widget import CueSheetWidget

pg.setConfigOptions(antialias=True)
pg.setConfigOption('background', 'w')
pg.setConfigOption('foreground', 'k')


class PerformanceGraphWidget(ScreenWidget):

  def init_extra(self):
    self.plot_data_x1 = []
    for i in range(self.config.G_GUI_HR_POWER_DISPLAY_RANGE):
      self.plot_data_x1.append(i)

  def setup_ui_extra(self): 
    self.plot = pg.PlotWidget()
    self.plot.setBackground(None)
    #self.plot.setBackground((0,0,0)) #for debug
    self.p1 = self.plot.plotItem
    #self.p1.setLabels(left='HR')
    #2nd graph
    self.p2 = pg.ViewBox()
    self.p1.showAxis('right')
    self.p1.scene().addItem(self.p2)
    self.p1.getAxis('right').linkToView(self.p2)
    self.p2.setXLink(self.p1)
    #self.p1.getAxis('right').setLabel('power', color='#FFFF00')

    self.plot.setXRange(0, self.config.G_GUI_HR_POWER_DISPLAY_RANGE)
    self.p1.setYRange(self.config.G_GUI_MIN_HR, self.config.G_GUI_MAX_HR)
    self.p2.setYRange(self.config.G_GUI_MIN_POWER, self.config.G_GUI_MAX_POWER)
    self.plot.setMouseEnabled(x=False, y=False)
    #pg.setConfigOptions(antialias=True)
  
    #for HR
    self.pen1 = pg.mkPen(color=(255,0,0), width=2)
    #for Power
    #self.brush = pg.mkBrush(color=(0,160,255,64))
    self.brush = pg.mkBrush(color=(0,255,255))
    #self.pen2 = pg.mkPen(color=(255,255,255,0), width=0.01) #transparent and thin line
    self.pen2 = pg.mkPen(color=(255,255,255), width=0.01) #transparent and thin line

  def make_item_layout(self):
    self.item_layout = {"Power":(0, 0), "HR":(0, 1), "Lap PWR":(0, 2), "LapTime":(0, 3)}

  def add_extra(self):
    self.layout.addWidget(self.plot, 1, 0, 2, 4)

  def set_border(self):
    self.max_height = 1
    self.max_width = 3

  def set_font_size(self, length):
    self.font_size = int(length / 7)
    self.set_minimum_size()

  def update_extra(self):
    all_nan = {'hr_graph': True, 'power_graph': True}
    for key in all_nan.keys():
      chk = np.isnan(self.config.logger.sensor.values['integrated'][key])
      if False in chk:
        all_nan[key] = False
   
    if not all_nan['hr_graph']:
      self.p1.clear()
      #for HR
      self.p1.addItem(
        pg.PlotCurveItem(
          self.config.logger.sensor.values['integrated']['hr_graph'], 
          pen=self.pen1
        )
      )

    #for Power
    if not all_nan['power_graph']:
      self.p2.clear()
      self.p2.setGeometry(self.p1.vb.sceneBoundingRect())
      self.p2.linkedViewChanged(self.p1.vb, self.p2.XAxis)
      bg = pg.BarGraphItem(
        x0 = self.plot_data_x1[:-1],
        x1 = self.plot_data_x1[1:],
        height = self.config.logger.sensor.values['integrated']['power_graph'],
        brush = self.brush,
        pen = self.pen2
      )
      self.p2.addItem(bg)


class BaseMapWidget(ScreenWidget):

  #map button
  button = {}
  button_name = ['lock','zoomup','zoomdown','left','right','up','down','go']
  lock_status = True
  button_press_count = {}

  #map position
  map_pos = {'x':np.nan, 'y':np.nan} #center
  map_area = {'w':np.nan, 'h':np.nan} #witdh(longitude diff) and height(latitude diff)
  move_pos = {'x':0, 'y':0}

  #current point
  location = []
  point_color = {'fix':None, 'lost':None}

  #show range from zoom
  zoom = 2000 #[m] #for CourseProfileGraphWidget
  zoomlevel = 13 #for SimpleMapWidget

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
      'lost':pg.mkBrush(color=(128,128,128))
      }
    self.point = {
      'pos': [np.nan, np.nan],
      'size': 20,
      'pen': {'color': 'w', 'width': 3},
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
      self.move_factor = 16
      self.move_adjust_mode = True
    else:
      self.move_factor = 1.0
      self.move_adjust_mode = False

  def move_x_plus(self):
    self.move_x(+self.zoom/2)

  def move_x_minus(self):
    self.move_x(-self.zoom/2)

  def move_y_plus(self):
    self.move_y(+self.zoom/2)

  def move_y_minus(self):
    self.move_y(-self.zoom/2)

  def move_x(self, delta):
    self.move_pos['x'] += delta
    self.update_extra()

  def move_y(self, delta):
    self.move_pos['y'] += delta
    self.update_extra()

  def zoom_plus(self):
    self.zoom /= 2
    self.zoomlevel += 1
    self.update_extra()
    
  def zoom_minus(self):
    self.zoom *= 2
    self.zoomlevel -= 1
    self.update_extra()

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
    print("MAX_ZOOM", self.config.G_MAX_ZOOM, dist)
  
  def load_course(self):
    pass
  
  def update_extra(self):
    pass


class CourseProfileGraphWidget(BaseMapWidget):

  #remove button(up, down)
  def add_extra(self):
    #map
    self.layout.addWidget(self.plot, 0, 0, 3, 3)

    if self.config.G_AVAILABLE_DISPLAY[self.config.G_DISPLAY]['touch']:
      #zoom
      self.layout.addWidget(self.button['zoomdown'],0,0)
      self.layout.addWidget(self.button['lock'],1,0)
      self.layout.addWidget(self.button['zoomup'],2,0)
      #arrow
      self.layout.addWidget(self.button['left'],0,2)
      self.layout.addWidget(self.button['right'],1,2)

    #for expanding column
    self.layout.setColumnMinimumWidth(0, 40)
    self.layout.setColumnStretch(1, 1)
    self.layout.setColumnMinimumWidth(2, 40)

  #load course profile and display
  def load_course(self):

    if len(self.config.logger.course.distance) == 0 or len(self.config.logger.course.altitude) == 0:
      return
    
    t = datetime.datetime.utcnow()

    if not self.config.logger.sensor.sensor_gps.hasGPS():
      self.zoom = self.config.G_MAX_ZOOM
    
    self.plot.showGrid(x=True, y=True, alpha=1)
    self.plot.showAxis('left')
    self.plot.showAxis('bottom')
    font = QtGui.QFont()
    font.setPixelSize(16)
    font.setBold(True)
    self.plot.getAxis("bottom").tickFont = font
    #self.plot.getAxis("bottom").setStyle(tickTextOffset = 5)
    self.plot.getAxis("left").tickFont = font
    #self.plot.getAxis("left").setStyle(tickTextOffset = 5)
    #self.plot.setAutoPan()

    print("\tpyqt_graph : load course profile : ", (datetime.datetime.utcnow()-t).total_seconds(), "sec")
    t = datetime.datetime.utcnow()

    bg = pg.CourseProfileGraphItem(
      x=self.config.logger.course.distance,
      y=self.config.logger.course.altitude,
      brushes=self.config.logger.course.colored_altitude, 
      pen=pg.mkPen(color=(255,255,255,0), width=0.01)) #transparent(alpha=0) and thin line
    self.plot.addItem(bg)

    print("\tpyqt_graph : plot course profile : ", (datetime.datetime.utcnow()-t).total_seconds(), "sec")

  def update_extra(self):

    if len(self.config.logger.course.distance) == 0 or len(self.config.logger.course.altitude) == 0:
      return

    if not self.course_loaded:
      self.load_course()
      self.course_loaded = True
    
    if self.zoom == self.config.G_MAX_ZOOM:
      self.zoom_plus()
      return
    
    #remove current position for reloading
    if len(self.location) > 0 :
      self.plot.removeItem(self.current_point)
      self.location.pop()

    #initialize
    x_start = x_end = np.nan
    x_width = self.zoom/1000 * 0.8
    dist_end = self.config.logger.course.distance[-1]
    self.graph_index = self.gps_values['course_index']
    x_start = self.config.logger.course.distance[self.graph_index]
    
    #get x,y from current position or start(temporary) without GPS
    if self.gps_values['on_course_status']:
      self.point['brush'] = self.point_color['fix']
    else:
      self.point['brush'] = self.point_color['lost']
    
    #move x,y
    if self.lock_status:
      self.map_pos['x'] = x_start - x_width/10
      #print(self.map_pos)
      if self.map_pos['x'] < 0:
        self.map_pos['x'] = 0
      self.map_pos['x_index'] = self.graph_index
    else: #no lock (scroll is available)
      self.map_pos['x'] += self.move_pos['x']/1000
      if self.map_pos['x'] <= 0:
        self.map_pos['x_index'] = 0
      elif self.map_pos['x'] >= dist_end:
        self.map_pos['x_index'] = len(self.config.logger.course.distance)-1
      else:
        self.map_pos['x_index'] = self.gps_sensor.get_index_with_distance_cutoff(
          self.map_pos['x_index'], 
          self.move_pos['x']/1000
          )

    x_end = self.map_pos['x'] + x_width
    x_end_index = 0
    if x_end >= dist_end:
      x_end_index = len(self.config.logger.course.distance)-1
    else:
      x_end_index = self.gps_sensor.get_index_with_distance_cutoff(
        self.map_pos['x_index'], 
        x_width
        )
    
    #check borders
    #too short course or zoom out: display all
    if x_width > dist_end:
      self.map_pos['x'] = 0
      x_end = dist_end
    #over move: fix border
    else:
      if x_end > dist_end:
        x_end = dist_end
        self.map_pos['x'] = dist_end - x_width
      if self.map_pos['x'] < 0:
        self.map_pos['x'] = 0
        x_end = x_width
   
    if 0 <= self.graph_index < len(self.config.logger.course.distance):
      #self.point['pos'][0] = self.config.logger.course.distance[self.graph_index]
      self.point['pos'][0] = self.gps_values['course_distance']/1000
      self.point['pos'][1] = self.config.logger.course.altitude[self.graph_index]
      self.location.append(self.point)
      self.current_point.setData(self.location)
      self.plot.addItem(self.current_point)

    #positioning
    self.plot.setXRange(min=self.map_pos['x'], max=x_end, padding=0)
    y_min = float('inf')
    y_max = -float('inf')
    if 0 <= self.map_pos['x_index'] < x_end_index:
      y_min = np.min(self.config.logger.course.altitude[self.map_pos['x_index']:x_end_index])
      y_max = np.max(self.config.logger.course.altitude[self.map_pos['x_index']:x_end_index])
   
    if y_min != float('inf') and y_max != -float('inf'):
      y_max = (y_max - y_min) * 1.1 + y_min
      y_max = (int(y_max/100)+1) * 100
      y_min = int(y_min/100) * 100
      self.plot.setYRange(min=y_min, max=y_max, padding=0)
    
    #reset move_pos
    self.move_pos['x'] = self.move_pos['y'] = 0


class SimpleMapWidget(BaseMapWidget):
  
  #tracks
  tracks_lat = np.array([])
  tracks_lon = np.array([])
  tracks_lat_pos = None
  tracks_lon_pos = None
  tracks_timestamp = None

  course_plot = None
  plot_verification = None
  course_points_plot = None
  course_point_text = None

  cuesheet_widget = None

  #misc
  y_mod = 1.22 #31/25 at Tokyo(N35)
  pre_zoomlevel = np.nan

  drawn_tile = {}
  existing_tiless = {}
  map_cuesheet_ratio = 1 #map:cuesheet = 1:0

  font = ""

  #signal for physical button
  signal_search_route = QtCore.pyqtSignal()

  def setup_ui_extra(self):
    super().setup_ui_extra()
    
    #self.plot.showGrid(x=True, y=True, alpha=1)
    self.track_plot = self.plot.plot(pen=pg.mkPen(color=(0,128,255), width=8))
    #self.track_plot = self.plot.plot(pen=pg.mkPen(color=(0,192,255,128), width=8))

    self.scale_plot = self.plot.plot(pen=pg.mkPen(color=(0,0,0), width=3))
    self.scale_text = pg.TextItem(
      text = "",
      anchor = (0.5, 1), 
      angle = 0, 
      border = (255, 255, 255, 255),
      fill = (255, 255, 255, 255),
      color = (0, 0, 0),
      )
    self.scale_text.setZValue(100)
    self.plot.addItem(self.scale_text)
    
    self.map_attribution = pg.TextItem(
      #text = self.config.G_MAP_CONFIG[self.config.G_MAP]['attribution'],
      html = '<div style="text-align: right;"><span style="color: #000; font-size: 10px;">' + self.config.G_MAP_CONFIG[self.config.G_MAP]['attribution'] + '</span></div>',
      anchor = (1, 1), 
      angle = 0, 
      border = (255, 255, 255, 255),
      fill = (255, 255, 255, 255),
      color = (0, 0, 0),
      )
    self.map_attribution.setZValue(100)
    self.plot.addItem(self.map_attribution)

    #self.load_course()
    t = datetime.datetime.utcnow()
    self.get_track() #heavy when resume
    print("\tpyqt_graph : get_track(init) : ", (datetime.datetime.utcnow()-t).total_seconds(), "sec")

  def add_extra(self):

    #map
    self.layout.addWidget(self.plot, 0, 0, 4, 3)
    #print("### self.plot.width ###", self.plot.width())

    if self.config.G_AVAILABLE_DISPLAY[self.config.G_DISPLAY]['touch']:
      #zoom
      self.layout.addWidget(self.button['zoomdown'],0,0)
      self.layout.addWidget(self.button['lock'],1,0)
      self.layout.addWidget(self.button['zoomup'],2,0)
      #arrow
      self.layout.addWidget(self.button['left'],0,2)
      self.layout.addWidget(self.button['up'],1,2)
      self.layout.addWidget(self.button['down'],2,2)
      self.layout.addWidget(self.button['right'],3,2)
      
      if self.config.G_HAVE_GOOGLE_DIRECTION_API_TOKEN:
        self.layout.addWidget(self.button['go'],3,0)
        self.button['go'].clicked.connect(self.search_route)

    #for expanding column
    self.layout.setColumnMinimumWidth(0, 40)
    self.layout.setColumnStretch(1, 1)
    self.layout.setColumnMinimumWidth(2, 40)

    #cue sheet
    self.init_cuesheet()
    
    #center point (displays while moving the map)
    self.center_point = pg.ScatterPlotItem(pxMode=True, symbol="+")
    self.center_point_data = {
      'pos': [np.nan, np.nan],
      'size': 15,
      'pen': {'color':(0, 0, 0), 'width': 2},
      }
    self.center_point_location = []

    #connect signal
    self.signal_search_route.connect(self.search_route)

  def init_cuesheet(self):
    #if self.config.G_CUESHEET_DISPLAY_NUM > 0:
    if len(self.config.logger.course.point_name) > 0 and self.config.G_CUESHEET_DISPLAY_NUM > 0 and self.config.G_COURSE_INDEXING:
      self.cuesheet_widget = CueSheetWidget(self, self.config)
      self.map_cuesheet_ratio = 0.7
      self.layout.addWidget(self.cuesheet_widget, 0, 4, 4, 5)

  def resizeEvent(self, event):
    if len(self.config.logger.course.point_name) == 0 or self.config.G_CUESHEET_DISPLAY_NUM == 0 or not self.config.G_COURSE_INDEXING :
      self.map_cuesheet_ratio = 1.0
    #if self.config.G_CUESHEET_DISPLAY_NUM > 0:
    else:
      self.cuesheet_widget.setFixedWidth(int(self.width()*(1-self.map_cuesheet_ratio)))
      self.cuesheet_widget.setFixedHeight(self.height())
    self.plot.setFixedWidth(int(self.width()*(self.map_cuesheet_ratio)))
    self.plot.setFixedHeight(self.height())

  #override for long press
  def switch_lock(self):
    if self.button['lock'].isDown():
      if self.button['lock']._state == 0:
        self.button['lock']._state = 1
      else:
        self.button_press_count['lock'] += 1
        #long press
        if self.button_press_count['lock'] == self.config.G_BUTTON_LONG_PRESS:
          self.change_move()
    elif self.button['lock']._state == 1:
      self.button['lock']._state = 0
      self.button_press_count['lock'] = 0
    #short press
    else:
      super().switch_lock()

  def load_course(self):
    if len(self.config.logger.course.latitude) == 0:
      return

    t = datetime.datetime.utcnow()

    if self.course_plot != None:
      self.plot.removeItem(self.course_plot)
    self.course_plot = pg.CoursePlotItem(
      x=self.config.logger.course.longitude,
      y=self.get_mod_lat_np(self.config.logger.course.latitude),
      brushes=self.config.logger.course.colored_altitude, 
      width=6)
    self.plot.addItem(self.course_plot)

    #test
    if not self.config.G_IS_RASPI:
      if self.plot_verification != None:
        self.plot.removeItem(self.plot_verification)
      self.plot_verification = pg.ScatterPlotItem(pxMode=True)
      test_points = []
      for i in range(len(self.config.logger.course.longitude)):  
        p = {
          'pos': [self.config.logger.course.longitude[i], self.get_mod_lat(self.config.logger.course.latitude[i])],
          'size': 2,
          'pen': {'color': 'w', 'width': 1},
          'brush':pg.mkBrush(color=(255,0,0))
          }
        test_points.append(p)
      self.plot_verification.setData(test_points)
      self.plot.addItem(self.plot_verification)
    print("\tpyqt_graph : course plot : ", (datetime.datetime.utcnow()-t).total_seconds(), "sec")
      
    #course point
    if len(self.config.logger.course.point_longitude) == 0:
      return
    
    t = datetime.datetime.utcnow()

    if self.course_points_plot != None:
      self.plot.removeItem(self.course_points_plot)
    self.course_points_plot = pg.ScatterPlotItem(pxMode=True, symbol="t")
    self.course_points = []

    for i in reversed(range(len(self.config.logger.course.point_longitude))):
      #if self.config.logger.course.point_type[i] == "Straight":
      #  continue
      cp = {
        'pos': [
          self.config.logger.course.point_longitude[i],
          self.get_mod_lat(self.config.logger.course.point_latitude[i])
          ],
        'size': 10,
        'pen': {'color': 'r', 'width': 1},
        'brush': pg.mkBrush(color=(255,0,0))
      }
      self.course_points.append(cp)
    self.course_points_plot.setData(self.course_points)
    self.plot.addItem(self.course_points_plot)

    print("\tpyqt_graph : load course points plot : ", (datetime.datetime.utcnow()-t).total_seconds(), "sec")

  def update_extra(self):

    #t = datetime.datetime.utcnow()

    #display current position
    if len(self.location) > 0 :
      self.plot.removeItem(self.current_point)
      self.location.pop()
    #display center point
    if len(self.center_point_location) > 0 :
      self.plot.removeItem(self.center_point)
      self.center_point_location.pop()
    
    #current position
    self.point['pos'] = [self.gps_values['lon'], self.gps_values['lat']]
    #dummy position
    if np.isnan(self.gps_values['lon']) and np.isnan(self.gps_values['lat']):
      #recent point(from log or pre_point) / course start / fix(TOKYO station)
      if len(self.tracks_lon) > 0 and len(self.tracks_lat) > 0:
        self.point['pos'] = [self.tracks_lon_pos, self.tracks_lat_pos]
      elif len(self.config.logger.course.longitude) > 0 and len(self.config.logger.course.latitude) > 0:
        self.point['pos'] = [
          self.config.logger.course.longitude[0],
          self.config.logger.course.latitude[0]
        ]
      else:
        self.point['pos'] = [self.config.G_DUMMY_POS_X, self.config.G_DUMMY_POS_Y]
    #update y_mod (adjust for lat:lon=1:1)
    self.y_mod = self.calc_y_mod(self.point['pos'][1])
    #add position circle to map
    if not np.isnan(self.point['pos'][0]) and not np.isnan(self.point['pos'][1]):
      if self.gps_values['mode'] == 3:
        self.point['brush'] = self.point_color['fix']
      else:
        self.point['brush'] = self.point_color['lost']
    else:
      #set dummy
      self.point['brush'] = self.point_color['lost']

    #center position
    if self.lock_status:
      self.map_pos['x'] = self.point['pos'][0]
      self.map_pos['y'] = self.point['pos'][1]
      
    #set width and height
    self.map_area['w'], self.map_area['h'] = self.get_geo_area(self.map_pos['x'], self.map_pos['y'])

    #move
    x_move = y_move = 0
    if self.lock_status and len(self.config.logger.course.distance) > 0 and self.gps_values['on_course_status']:
      index = self.gps_sensor.get_index_with_distance_cutoff(
        self.gps_values['course_index'], 
        #get some distance [m]
        self.get_width_distance(self.map_pos['y'], self.map_area['w'])/1000,
        )
      x2 = self.config.logger.course.longitude[index]
      y2 = self.config.logger.course.latitude[index]
      x_delta = x2 - self.map_pos['x']
      y_delta = y2 - self.map_pos['y']
      #slide from center
      x_move = 0.25 * self.map_area['w']
      y_move = 0.25 * self.map_area['h']
      if x_delta > x_move:
        self.map_pos['x'] += x_move
      elif x_delta < -x_move:
        self.map_pos['x'] -= x_move
      if y_delta > y_move:
        self.map_pos['y'] += y_move
      elif y_delta < -y_move:
        self.map_pos['y'] -= y_move
    elif not self.lock_status:
      if self.move_pos['x'] > 0:
        x_move = self.map_area['w']/2
      elif self.move_pos['x'] < 0:
        x_move = -self.map_area['w']/2
      if self.move_pos['y'] > 0:
        y_move = self.map_area['h']/2
      elif self.move_pos['y'] < 0:
        y_move = -self.map_area['h']/2
      self.map_pos['x'] += x_move/self.move_factor
      self.map_pos['y'] += y_move/self.move_factor
    self.move_pos['x'] = self.move_pos['y'] = 0

    self.map_area['w'], self.map_area['h'] = self.get_geo_area(self.map_pos['x'], self.map_pos['y'])
    
    #experimental
    #self.config.logger.sensor.values['integrated']['dem_altitude'] = self.get_altitude_from_tile([self.point['pos'][0], self.point['pos'][1]])
    #print(self.config.logger.sensor.values['integrated']['dem_altitude'], self.map_pos) #################### bug

    ###########
    # drawing #
    ###########

    #current point
    #print(self.point['pos'])
    self.point['pos'][1] *= self.y_mod
    self.location.append(self.point)
    self.current_point.setData(self.location)
    self.plot.addItem(self.current_point)
    
    #center point
    if not self.lock_status:
      if self.move_adjust_mode:
        #self.center_point.setSymbol("d")
        self.center_point_data['size'] = 7.5
      else:
        #self.center_point.setSymbol("+")
        self.center_point_data['size'] = 15
      self.center_point_data['pos'][0] = self.map_pos['x']
      self.center_point_data['pos'][1] = self.get_mod_lat(self.map_pos['y'])
      self.center_point_location.append(self.center_point_data)
      self.center_point.setData(self.center_point_location)
      self.plot.addItem(self.center_point)

    #print("\tpyqt_graph : update_extra init : ", (datetime.datetime.utcnow()-t).total_seconds(), "sec")
    #t = datetime.datetime.utcnow()

    #set x and y ranges
    x_start = x_end = y_start = y_end = np.nan
    x_start = self.map_pos['x'] - self.map_area['w'] / 2
    x_end = x_start + self.map_area['w']
    y_start = self.map_pos['y'] - self.map_area['h'] / 2
    y_end = y_start + self.map_area['h']
    if not np.isnan(x_start) and not np.isnan(x_end):
      self.plot.setXRange(x_start, x_end, padding=0)
    if not np.isnan(y_start) and not np.isnan(y_end):
      self.plot.setYRange(self.get_mod_lat(y_start), self.get_mod_lat(y_end), padding=0)

    self.draw_map_tile(self.zoomlevel, x_start, x_end, y_start, y_end)
    #print("\tpyqt_graph : update_extra map : ", (datetime.datetime.utcnow()-t).total_seconds(), "sec")
    #t = datetime.datetime.utcnow()

    if not self.course_loaded:
      self.load_course()
      self.course_loaded = True
    
    #course_points and cuesheet
    self.draw_cuesheet()
    #print("\tpyqt_graph : update_extra cuesheet : ", (datetime.datetime.utcnow()-t).total_seconds(), "sec")
    #t = datetime.datetime.utcnow()

    #draw track
    self.get_track()
    self.track_plot.setData(self.tracks_lon, self.tracks_lat)
    #print("\tpyqt_graph : update_extra track : ", (datetime.datetime.utcnow()-t).total_seconds(), "sec")
    #t = datetime.datetime.utcnow()

    #draw scale
    self.draw_scale(x_start, y_start)
    #draw map attribution
    self.draw_map_attribution(x_start, y_start)
    #print("\tpyqt_graph : update_extra draw map : ", (datetime.datetime.utcnow()-t).total_seconds(), "sec")
    #t = datetime.datetime.utcnow()
    
  def get_track(self):
    #get track from SQL
    lon = []
    lat = []
    #not good (input & output)    #conversion coordinate
    (self.tracks_timestamp, lon, lat) = \
      self.config.logger.update_track(self.tracks_timestamp)
    if len(lon) > 0 and len(lat) > 0:
      self.tracks_lon_pos = lon[-1]
      self.tracks_lat_pos = lat[-1]
      self.tracks_lon = np.append(self.tracks_lon, np.array(lon))
      self.tracks_lat = np.append(self.tracks_lat, self.get_mod_lat_np(np.array(lat)))

  def reset_track(self):
    self.tracks_lon = []
    self.tracks_lat = []
  
  def search_route(self):
    if self.lock_status:
      return
    
    self.config.logger.course.search_route(
      self.point['pos'][0],
      self.point['pos'][1]/self.y_mod,
      self.map_pos['x'],
      self.map_pos['y'],
    )
    self.init_cuesheet()
    self.course_loaded = False
    self.resizeEvent(None)

  def draw_map_tile(self, pixel_z, x_start, x_end, y_start, y_end):
    
    #get tile coordinates of display border points
    p0 = {
      "x": min(x_start, x_end),
      "y": min(y_start, y_end)
    }
    p1 = {
      "x": max(x_start, x_end),
      "y": max(y_start, y_end)
    }
    #tile range
    t0 = self.config.get_tilexy_and_xy_in_tile(pixel_z, p0["x"], p0["y"], self.config.G_MAP_CONFIG[self.config.G_MAP]['tile_size'])
    t1 = self.config.get_tilexy_and_xy_in_tile(pixel_z, p1["x"], p1["y"], self.config.G_MAP_CONFIG[self.config.G_MAP]['tile_size'])
    tile_x = sorted([t0[0], t1[0]])
    tile_y = sorted([t0[1], t1[1]])

    #tile download check
    if self.zoomlevel not in self.existing_tiless:
      self.existing_tiless[self.zoomlevel] = {}
    
    tiles = []

    for i in range(tile_x[0], tile_x[1]+1):
      for j in range(tile_y[0], tile_y[1]+1):
        tiles.append((i,j))
    
    for i in [tile_x[0]-1, tile_x[1]+1]:
      for j in range(tile_y[0]-1, tile_y[1]+2):
        tiles.append((i,j))

    for i in range(tile_x[0], tile_x[1]+1):
      for j in [tile_y[0]-1, tile_y[1]+1]:
        tiles.append((i,j))

    for tile in tiles:
      filename = self.config.get_maptile_filename(self.config.G_MAP, pixel_z, *tile)
      key = "{0}-{1}".format(*tile)

      if os.path.exists(filename) and os.path.getsize(filename) > 0:
        self.existing_tiless[self.zoomlevel][key] = True
        continue
      
      #download is in progress
      if key in self.existing_tiless[self.zoomlevel]:
        continue

      #start downloading
      self.existing_tiless[self.zoomlevel][key] = False
      if not self.config.download_maptile(pixel_z, *tile):
        self.existing_tiless[self.zoomlevel].pop(key)

    draw_flag = False
    add_key = {}
    if self.zoomlevel not in self.drawn_tile or self.pre_zoomlevel != self.zoomlevel:
      self.drawn_tile[self.zoomlevel] = {}
    for i in range(tile_x[0], tile_x[1]+1):
      for j in range(tile_y[0], tile_y[1]+1):
        key = "{0}-{1}".format(i,j)
        if (key, True) in self.existing_tiless[self.zoomlevel].items() and key not in self.drawn_tile[self.zoomlevel]:
          self.drawn_tile[self.zoomlevel][key] = True
          add_key[(i,j)] = True
          draw_flag = True
    self.pre_zoomlevel = self.zoomlevel

    if not draw_flag:
      return
    
    #draw only the necessary tiles 
    for keys in add_key:
      imgarray = np.empty((self.config.G_MAP_CONFIG[self.config.G_MAP]['tile_size'],self.config.G_MAP_CONFIG[self.config.G_MAP]['tile_size'],3),dtype='uint8')
      filename = self.config.get_maptile_filename(self.config.G_MAP, pixel_z, keys[0], keys[1])
      if os.path.exists(filename) and os.path.getsize(filename) > 0:
        imgarray = np.rot90(np.asarray(Image.open(filename).convert('RGB')).astype('uint8'), -1)
      else:
        imgarray = 255
      
      imgitem = pg.ImageItem(imgarray)
      imgarray_min_x, imgarray_max_y = \
        self.config.get_lon_lat_from_tile_xy(pixel_z, keys[0], keys[1])
      imgarray_max_x, imgarray_min_y = \
        self.config.get_lon_lat_from_tile_xy(pixel_z, keys[0]+1, keys[1]+1)
      
      self.plot.addItem(imgitem)
      imgitem.setZValue(-100)
      imgitem.setRect(
        pg.QtCore.QRectF(
          imgarray_min_x,
          self.get_mod_lat(imgarray_min_y),
          imgarray_max_x-imgarray_min_x,
          self.get_mod_lat(imgarray_max_y)-self.get_mod_lat(imgarray_min_y),
          )
        )
  
  def draw_scale(self, x_start, y_start):
    #draw scale at left bottom
    scale_factor = 8
    scale_dist = self.get_width_distance(y_start, self.map_area['w'])/scale_factor
    num = scale_dist/(10**int(np.log10(scale_dist)))
    modify = 1
    if 1 < num < 2:
      modify = 2 / num
    elif 2 < num < 5:
      modify = 5 / num
    elif 5 < num < 10:
      modify = 10 / num
    scale_x1 = x_start + self.map_area['w']/25
    scale_x2 = scale_x1 + self.map_area['w']/scale_factor*modify
    scale_y1 = y_start + self.map_area['h']/25
    scale_y2 = scale_y1 + self.map_area['h']/30
    scale_y1 = self.get_mod_lat(scale_y1)
    scale_y2 = self.get_mod_lat(scale_y2)
    self.scale_plot.setData(
      [scale_x1, scale_x1, scale_x2, scale_x2], 
      [scale_y2, scale_y1, scale_y1, scale_y2],
      )
    
    scale_unit = "m"
    scale_label = round(scale_dist*modify)
    if scale_label >= 1000:
      scale_label = int(scale_label/1000)
      scale_unit = "km"
    self.scale_text.setPlainText("{0}{1}".format(scale_label, scale_unit))
    self.scale_text.setPos(
      (scale_x1+scale_x2)/2,
      scale_y2
      )

  def draw_map_attribution(self, x_start, y_start):
    #draw map attribution at right bottom
    self.map_attribution.setPos(
      x_start + self.map_area['w'],
      self.get_mod_lat(y_start)
      )

  def draw_cuesheet(self):
    if self.cuesheet_widget != None:
      self.cuesheet_widget.update_extra()

  def calc_y_mod(self, lat):
    if np.isnan(lat):
      return np.nan
    return self.config.GEO_R2 / (self.config.GEO_R1 * math.cos(lat/180*np.pi))
  
  def get_width_distance(self, lat, w):
    return w * self.config.GEO_R1*1000 * 2*np.pi*math.cos(lat/180*np.pi)/360

  def get_mod_lat(self, lat):
    return lat * self.calc_y_mod(lat)

  def get_mod_lat_np(self, lat):
    return lat * self.config.GEO_R2 / (self.config.GEO_R1 * np.cos(lat/180*np.pi))

  def get_geo_area(self, x, y):
    tile_x, tile_y, _, _ = self.config.get_tilexy_and_xy_in_tile(self.zoomlevel, x, y, self.config.G_MAP_CONFIG[self.config.G_MAP]['tile_size'])
    pos_x0, pos_y0 = self.config.get_lon_lat_from_tile_xy(self.zoomlevel, tile_x, tile_y)
    pos_x1, pos_y1 = self.config.get_lon_lat_from_tile_xy(self.zoomlevel, tile_x+1, tile_y+1)
    return abs(pos_x1-pos_x0)/self.config.G_MAP_CONFIG[self.config.G_MAP]['tile_size']*(self.width()*self.map_cuesheet_ratio), abs(pos_y1-pos_y0)/self.config.G_MAP_CONFIG[self.config.G_MAP]['tile_size']*self.height()
  

  
