import random
import numpy as np
import datetime

import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtGui as QtGui
import pyqtgraph as pg

from .pyqt_screen_widget import ScreenWidget

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
  button_name = ['lock','zoomup','zoomdown','left','right','up','down']
  lock_status = True

  #map position
  map_pos = {'x':np.nan, 'y':np.nan}
  map_width = {'x':np.nan, 'y':np.nan}
  move_pos = {'x':0, 'y':0}

  #current point
  location = []
  point_color = {'fix':None, 'lost':None}

  #show range from zoom
  zoom = 2000 #[m]

  #load course
  course_loaded = False

  def init_extra(self):
    self.gps_values = self.config.logger.sensor.values['GPS']
    self.gps_sensor = self.config.logger.sensor.sensor_gps
  
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
    for b in self.button_name:
      self.button[b].setStyleSheet(self.config.gui.style.G_GUI_PYQT_buttonStyle_map)

    self.button['lock'].clicked.connect(self.switch_lock)
    self.button['right'].clicked.connect(self.move_x_plus)
    self.button['left'].clicked.connect(self.move_x_minux)
    self.button['up'].clicked.connect(self.move_y_plus)
    self.button['down'].clicked.connect(self.move_y_minus)
    self.button['zoomdown'].clicked.connect(self.zoom_minus)
    self.button['zoomup'].clicked.connect(self.zoom_plus)

    self.get_max_zoom()
  
  def make_item_layout(self):
    self.item_layout = {}

  def add_extra(self):
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

  def switch_lock(self):
    if self.lock_status:
      self.lock_status = False
    else:
      self.lock_status = True
  def move_x_plus(self):
    self.move_x(+self.zoom/2)
  def move_x_minux(self):
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
    self.update_extra()
  def zoom_minus(self):
    self.zoom *= 2
    self.update_extra()

  def get_max_zoom(self):

    if len(self.config.logger.course_distance) == 0:
      return
    
    if self.config.G_MAX_ZOOM != 0:
      return
    z = self.zoom
    dist = self.config.logger.course_distance[-1]
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

    if len(self.config.logger.course_distance) == 0:
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
      x=self.config.logger.course_distance,
      y=self.config.logger.course_altitude,
      brushes=self.config.logger.colored_altitude, 
      pen=pg.mkPen(color=(255,255,255,0), width=0.01)) #transparent(alpha=0) and thin line
    self.plot.addItem(bg)

    print("\tpyqt_graph : plot course profile : ", (datetime.datetime.utcnow()-t).total_seconds(), "sec")

  def update_extra(self):

    if len(self.config.logger.course_distance) == 0:
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
    dist_end = self.config.logger.course_distance[-1]
    if np.isnan(self.gps_values['lon']) or np.isnan(self.gps_values['lat']):
      self.graph_index = 0
    else:
      self.graph_index = self.gps_values['course_index']
    
    #get x,y from current position or start(temporary) without GPS
    if not np.isnan(self.gps_values['lon']) and not np.isnan(self.gps_values['lat']):
      self.point['brush'] = self.point_color['fix']
      x_start = self.config.logger.course_distance[self.graph_index]
    else:
      self.point['brush'] = self.point_color['lost']
      x_start = 0
    
    #move x,y
    if self.lock_status:
      self.map_pos['x'] = x_start - x_width/10
      if self.map_pos['x'] < 0:
        self.map_pos['x'] = 0
      self.map_pos['x_index'] = self.graph_index
    else: #no lock (scroll is available)
      self.map_pos['x'] += self.move_pos['x']/1000
      if self.map_pos['x'] <= 0:
        self.map_pos['x_index'] = 0
      elif self.map_pos['x'] >= dist_end:
        self.map_pos['x_index'] = len(self.config.logger.course_distance)-1
      else:
        self.map_pos['x_index'] = self.gps_sensor.get_index_with_distance_cutoff(
          self.map_pos['x_index'], 
          self.move_pos['x']/1000
          )

    x_end = self.map_pos['x'] + x_width
    x_end_index = 0
    if x_end >= dist_end:
      x_end_index = len(self.config.logger.course_distance)-1
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
   
    if 0 <= self.graph_index < len(self.config.logger.course_distance):
      self.point['pos'][0] = self.config.logger.course_distance[self.graph_index]
      self.point['pos'][1] = self.config.logger.course_altitude[self.graph_index]
      self.location.append(self.point)
      self.current_point.setData(self.location)
      self.plot.addItem(self.current_point)

    #positioning
    self.plot.setXRange(min=self.map_pos['x'], max=x_end, padding=0)
    y_min = float('inf')
    y_max = -float('inf')
    if 0 <= self.map_pos['x_index'] < x_end_index:
      y_min = np.min(self.config.logger.course_altitude[self.map_pos['x_index']:x_end_index])
      y_max = np.max(self.config.logger.course_altitude[self.map_pos['x_index']:x_end_index])
    
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
  tracks_timestamp = None

  #course
  course_plots = []
  course_data = []
  drawed_course = False

  #misc
  zoomlevel = 17
  const_pixel = 85.05112878 #not need?
  y_mod = 1.22 #31/25 at Tokyo(N35)
  aspect = 320/200 #width/height

  def setup_ui_extra(self):
    super().setup_ui_extra()
    
    #self.plot.showGrid(x=True, y=True, alpha=1)
    self.track_plot = self.plot.plot(self.tracks_lon, self.tracks_lat)
    #self.track_plot.setPen(pg.mkPen(color=(0,192,255,128), width=7))
    self.track_plot.setPen(pg.mkPen(color=(0,128,255), width=7))

    self.scale_plot = self.plot.plot()
    self.scale_plot.setPen(pg.mkPen(color=(0,0,0), width=2))
    self.scale_text = pg.TextItem(
      text = "",
      anchor = (0.5, 1), 
      angle = 0, 
      border = (255, 255, 255, 0),
      fill = (255, 255, 255, 0),
      color = (0, 0, 0),
      )
    self.plot.addItem(self.scale_text)

    #self.load_course()
    t = datetime.datetime.utcnow()
    self.get_track() #heavy when resume
    print("\tpyqt_graph : get_track(init) : ", (datetime.datetime.utcnow()-t).total_seconds(), "sec")


  def add_extra(self):

    #map
    self.layout.addWidget(self.plot, 0, 0, 4, 3)

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

    #for expanding column
    self.layout.setColumnMinimumWidth(0, 40)
    self.layout.setColumnStretch(1, 1)
    self.layout.setColumnMinimumWidth(2, 40)

    #cue sheet
    #self.cuesheet_widget = QtWidgets.QWidget(self)
    #self.cuesheet_widget.setFixedWidth(int(self.config.G_WIDTH*0.4))
    #self.cuesheet = [
    #  QtWidgets.QLabel(),
    #  QtWidgets.QLabel(),
    #  QtWidgets.QLabel(),
    #  ]
    #self.cuesheet_layout = QtWidgets.QVBoxLayout(self.cuesheet_widget)
    #font = QtGui.QFont("源ノ角ゴシック JP")
    #for c in self.cuesheet:
    #  c.setFont(font)
    #  c.setWordWrap(True)
    #  self.cuesheet_layout.addWidget(c)
    #self.layout.addWidget(self.cuesheet_widget, 0, 4, 4, 5)

  def load_course(self):
    self.course_plots = []
    if len(self.config.logger.lat_by_slope) == 0:
      return

    t = datetime.datetime.utcnow()
    
    for i in range(len(self.config.G_SLOPE_CUTOFF)):
      t1 = datetime.datetime.utcnow()
      
      if np.sum(np.isnan(self.config.logger.lat_by_slope[i])) == len(self.config.logger.lat_by_slope[i]):
        continue
      
      pen_map = pg.mkPen(color=(
          self.config.G_SLOPE_COLOR[i][0],
          self.config.G_SLOPE_COLOR[i][1],
          self.config.G_SLOPE_COLOR[i][2]
        ),\
        width=3\
      )
      curve = self.plot.plot(np.array([]),np.array([]))
      curve.setPen(pen_map)
      #conversion coordinate
      self.course_data.append([
        np.array(self.config.logger.lon_by_slope[i]),
        np.array(list(map(lambda x: x * self.y_mod, self.config.logger.lat_by_slope[i]))),
        ])
      self.course_plots.append(curve)
      
    print("\tpyqt_graph : course_plots : ", (datetime.datetime.utcnow()-t).total_seconds(), "sec")
    t = datetime.datetime.utcnow()

    #course point
    self.course_points_plot = pg.ScatterPlotItem(pxMode=True, symbol="t")
    self.course_points = []

    #font = QtGui.QFont("源ノ角ゴシック JP")
    for i in range(len(self.config.logger.course_point_longitude)):
      if self.config.logger.course_point_point_type[i] == "Straight":
        continue
      cp = {
        'pos': [
          self.config.logger.course_point_longitude[i],
          self.y_mod * self.config.logger.course_point_latitude[i]
          ],
        'size': 10,
        'pen': {'color': 'r', 'width': 1},
        'brush': pg.mkBrush(color=(255,0,0))
      }
      self.course_points.append(cp)
    self.course_points_plot.setData(self.course_points)
    self.plot.addItem(self.course_points_plot)

    print("\tpyqt_graph : load course_points_plot : ", (datetime.datetime.utcnow()-t).total_seconds(), "sec")
    t = datetime.datetime.utcnow()

    for i in range(len(self.config.logger.course_point_longitude)):
      if self.config.logger.course_point_point_type[i] == "Straight":
        continue    

      #CoursePointType from TCX schema
      # https://www8.garmin.com/xmlschemas/TrainingCenterDatabasev2.xsd
      #  Generic, Summit, Valley, Water, Food, Danger,
      #  Left, Right, Straight, First Aid,
      #  4th Category, 3rd Category, 2nd Category, 1st Category,
      #  Hors Category, Sprint,
      arrow = ""
      if self.config.logger.course_point_point_type[i] == "Left":
        arrow ="backarrow_black.png"
      elif self.config.logger.course_point_point_type[i] == "Right":
        arrow ="nextarrow_black.png"
      else:
        continue
      # Create text object, use HTML tags to specify color/size
      #  http://www.pyqtgraph.org/documentation/graphicsItems/textitem.html
      text = pg.TextItem(
        html = '<div style="text-align: center">' + \
          '<img src="img/' + arrow + '" /></div>',
        #  self.config.logger.course_point_notes[i] + '</div>',
        #  #'<br><span style="color: #FF0; font-size: 16pt;">'PEAK</span></div>', 
        #text = self.config.logger.course_point_name[i] #instead of arrow
        anchor = (-0.1, 1.2), 
        angle = 0, 
        border = (255, 0, 0),
        fill = (255, 255, 255),
        color = (0, 0, 0),
        )
      #text.setFont(font)
      #text.setTextWidth(int(self.config.G_WIDTH/2.5))
      self.plot.addItem(text)
      text.setPos(
        self.config.logger.course_point_longitude[i], 
        self.y_mod * self.config.logger.course_point_latitude[i]
        )
    
    print("\tpyqt_graph : display course_points_plot : ", (datetime.datetime.utcnow()-t).total_seconds(), "sec")

  def update_extra(self):

    #t = datetime.datetime.utcnow()

    if not self.course_loaded:
      self.load_course()
      self.course_loaded = True

    #update aspect
    self.aspect = self.height()/self.width()

    #display position
    if len(self.location) > 0 :
      self.plot.removeItem(self.current_point)
      self.location.pop()
    
    #centering and zoom

    #position #with conversion coordinate
    self.point['pos'] = [self.gps_values['lon'], self.gps_values['lat']*self.y_mod]

    #dummy position
    if np.isnan(self.gps_values['lon']) and np.isnan(self.gps_values['lat']):
      #recent point(from log or pre_point) / course start / fix(TOKYO station)
      if len(self.tracks_lon) > 0 and len(self.tracks_lat) > 0:
        self.point['pos'] = [self.tracks_lon[-1], self.tracks_lat[-1]]
      elif len(self.config.logger.course_longitude) > 0 and len(self.config.logger.course_latitude) > 0:
        self.point['pos'] = [
          self.config.logger.course_longitude[0],
          self.config.logger.course_latitude[0] * self.y_mod
        ]
      else:
        self.point['pos'] = [self.config.G_DUMMY_POS_X, self.config.G_DUMMY_POS_Y * self.y_mod]
    
    #add position circle to map
    if not np.isnan(self.point['pos'][0]) and not np.isnan(self.point['pos'][1]):
      if self.gps_values['mode'] == 3:
        self.point['brush'] = self.point_color['fix']
      else:
        self.point['brush'] = self.point_color['lost']
    else:
      #set dummy
      self.point['brush'] = self.point_color['lost']
    self.location.append(self.point)
    self.current_point.setData(self.location)
    self.plot.addItem(self.current_point)

    #center position
    if self.lock_status:
      self.map_pos['x'] = self.point['pos'][0]
      self.map_pos['y'] = self.point['pos'][1]
      
    #zoom to width
    dist1s = {
      'x':self.getLonDist1s(self.map_pos['y']/self.y_mod),
      'y':self.getLatDist1s()
      }
    #[m] -> sec -> longitude or latitude
    self.map_width['x'] = self.zoom/dist1s['x'] / 3600 
    self.map_width['y'] = self.zoom/dist1s['y'] * self.y_mod * self.aspect / 3600

    #move
    x_move = y_move = 0
    if self.lock_status:
      if not np.isnan(self.gps_values['lon']) and not np.isnan(self.gps_values['lat']):
        graph_index = self.gps_values['course_index']
        ahead_point = self.zoom*2/1000
        if 0 <= graph_index <= len(self.config.logger.course_distance):
          index = self.gps_sensor.get_index_with_distance_cutoff(
            graph_index, 
            ahead_point
            )
          x2 = self.config.logger.course_longitude[index]
          y2 = self.config.logger.course_latitude[index]
          x_delta = x2 - self.gps_values['lon']
          y_delta = y2 - self.gps_values['lat']
          x_move = 0.5 * self.map_width['x']
          y_move = 0.5 * self.map_width['y']
          if x_delta > x_move:
            self.map_pos['x'] += x_move
          elif x_delta < -x_move:
            self.map_pos['x'] -= x_move
          if y_delta > y_move:
            self.map_pos['y'] += y_move
          elif y_delta < -y_move:
            self.map_pos['y'] -= y_move
    else:
      x_move = self.move_pos['x']*2/dist1s['x'] / 3600
      y_move = self.move_pos['y']*2/dist1s['y'] * self.y_mod * self.aspect / 3600
      self.map_pos['x'] += x_move
      self.map_pos['y'] += y_move

    x_start = x_end = y_start = y_end = np.nan
    x_start = self.map_pos['x'] - self.map_width['x']
    x_end = self.map_pos['x'] + self.map_width['x']
    y_start = self.map_pos['y'] - self.map_width['y']
    y_end = self.map_pos['y'] + self.map_width['y']

    if not np.isnan(x_start) and not np.isnan(x_end):
      self.plot.setXRange(x_start, x_end)
    if not np.isnan(y_start) and not np.isnan(y_end):
      self.plot.setYRange(y_start, y_end)

    self.move_pos['x'] = self.move_pos['y'] = 0

    #draw course
    for i in range(len(self.course_plots)):
      if not self.drawed_course:
        self.course_plots[i].setData(
          x = self.course_data[i][0],
          y = self.course_data[i][1],
          connect="finite")
    self.drawed_course = True
    
    #print("\tpyqt_graph : update_extra init : ", (datetime.datetime.utcnow()-t).total_seconds(), "sec")
    #t = datetime.datetime.utcnow() 
    
    #draw track
    self.get_track()
    self.track_plot.setData(self.tracks_lon, self.tracks_lat)

    #print("\tpyqt_graph : update_extra track : ", (datetime.datetime.utcnow()-t).total_seconds(), "sec")
    #t = datetime.datetime.utcnow()

    #draw scale
    scale_x1 = x_start + (x_end - x_start)/100
    scale_dist = 2*self.zoom/8 #[m]
    num = scale_dist/(10**int(np.log10(scale_dist)))
    mod_factor = 1
    if 1 < num < 2:
      mod_factor = 2 / num
    elif 2 < num < 5:
      mod_factor = 5 / num
    elif 5 < num < 10:
      mod_factor = 10 / num
    scale_x2 = scale_x1 + (x_end - x_start)/8*mod_factor
    scale_y1 = y_start + (y_end - y_start)/100
    y1_delta = scale_y1 + (y_end - y_start)/30
    self.scale_plot.setData(
      [scale_x1, scale_x1, scale_x2, scale_x2], 
      [y1_delta, scale_y1, scale_y1, y1_delta],
      )
    
    scale_unit = "m"
    scale_label = int(scale_dist*mod_factor)
    if scale_label >= 1000:
      scale_label = int(scale_label/1000)
      scale_unit = "km"
    self.scale_text.setPlainText("{0}{1}".format(scale_label, scale_unit))
    self.scale_text.setPos(
        (scale_x1+scale_x2)/2,
        y1_delta
      )
    
  def get_track(self):
    #get track from SQL
    lon = []
    lat = []
    #not good (input & output)    #conversion coordinate
    (self.tracks_timestamp, lon, lat) = \
      self.config.logger.update_track(self.tracks_timestamp)
    if len(lon) > 0 and len(lat) > 0:
      lat = list(map(lambda x: x * self.y_mod, lat))
      self.tracks_lon = np.append(self.tracks_lon, np.array(lon))
      self.tracks_lat = np.append(self.tracks_lat, np.array(lat))

  def reset_track(self):
    self.tracks_lon = []
    self.tracks_lat = []

  def calc_y_mod(self, lat):
    if np.isnan(lat):
      return
    return self.getLatDist1s() / self.getLonDist1s(lat)
  
  def getLatDist1s(self):
    return 6356752 * 2*np.pi/360/60/60 #[m]
  
  def getLonDist1s(self, lat):
    return 6378137 * 2*np.pi*np.cos(lat/180*np.pi)/360/60/60 #m

  
