import numpy as np
import pyqtgraph as pg

from .pyqt_screen_widget import ScreenWidget

pg.setConfigOptions(antialias=True)
pg.setConfigOption('background', 'w')
pg.setConfigOption('foreground', 'k')


class AccelerationGraphWidget(ScreenWidget):

  def init_extra(self):
    pass

  def setup_ui_extra(self): 
    self.plot = pg.PlotWidget()
    self.plot.setBackground(None)
    self.p1 = self.plot.plotItem
    self.p1.showGrid(y=True)
    #self.p1.setLabels(left='HR')
    
    self.p2 = pg.ViewBox()
    self.p1.scene().addItem(self.p2)
    self.p2.setXLink(self.p1)
    self.p3 = pg.ViewBox()
    self.p1.scene().addItem(self.p3)
    self.p3.setXLink(self.p1)

    self.plot.setXRange(0, self.config.G_GUI_REALTIME_GRAPH_RANGE)
    self.plot.setMouseEnabled(x=False, y=False)
    #pg.setConfigOptions(antialias=True)
  
    #for acc
    self.pen1 = pg.mkPen(color=(0,0,255), width=3)
    self.pen2 = pg.mkPen(color=(255,0,0), width=3)
    self.pen3 = pg.mkPen(color=(0,0,0), width=2)
    
    self.g_range = 0.6
  
  def start(self):
    self.timer.start(self.config.G_REALTIME_GRAPH_INTERVAL)

  def make_item_layout(self):
    self.item_layout = {"ACC_Y":(0, 0), "ACC_Z":(0, 1), "Motion":(0, 2), "M_Stat":(0, 3)}

  def add_extra(self):
    self.layout.addWidget(self.plot, 1, 0, 2, 4)

  def set_border(self):
    self.max_height = 1
    self.max_width = 3

  def set_font_size(self, length):
    self.font_size = int(length / 7)
    self.set_minimum_size()

  def update_extra(self):

    X = 0
    Y = 1
    Z = 2
    
    v = self.config.logger.sensor.sensor_i2c.graph_values['g_acc']
    all_nan = {X: True, Y: True, Z: True}
    for key in all_nan.keys():
      chk = np.isnan(v[key])
      if False in chk:
        all_nan[key] = False
    m = [x for x in v[0] if not np.isnan(x)]
    median = None
    if len(m) > 0:
      median = m[-1]
   
    if not all_nan[X]:
      self.p1.clear()
      if median != None:
        self.p1.setYRange(-self.g_range, self.g_range)

      self.p1.addItem(
        pg.PlotCurveItem(
          v[X], 
          pen=self.pen1,
          connect="finite"
        )
      )

    if not all_nan[Y]:
      self.p2.clear()
      
      if median != None:
        self.p2.setYRange(-self.g_range, self.g_range)
      
      self.p2.setGeometry(self.p1.vb.sceneBoundingRect())
      self.p2.linkedViewChanged(self.p1.vb, self.p2.XAxis)
      p = pg.PlotCurveItem(
        v[Y], 
        pen=self.pen2,
        connect="finite"
        )
      self.p2.addItem(p)

    if not all_nan[Z]:
      self.p3.clear()
      
      if median != None:
        self.p3.setYRange(-self.g_range, self.g_range)
      
      self.p3.setGeometry(self.p1.vb.sceneBoundingRect())
      self.p3.linkedViewChanged(self.p1.vb, self.p3.XAxis)
      p = pg.PlotCurveItem(
        v[Z], 
        pen=self.pen3,
        connect="finite"
        )
      self.p3.addItem(p)


class AltitudeGraphWidget(ScreenWidget):

  def init_extra(self):
    pass
    #self.plot_data_x1 = []
    #for i in range(self.config.G_GUI_HR_POWER_DISPLAY_RANGE):
    #  self.plot_data_x1.append(i)

  def setup_ui_extra(self): 
    self.plot = pg.PlotWidget()
    self.plot.setBackground(None)
    self.p1 = self.plot.plotItem
    self.p1.showGrid(y=True)
    
    self.p2 = pg.ViewBox()
    self.p1.scene().addItem(self.p2)
    self.p2.setXLink(self.p1)

    self.plot.setXRange(0, self.config.G_GUI_HR_POWER_DISPLAY_RANGE)
    self.plot.setMouseEnabled(x=False, y=False)
    #pg.setConfigOptions(antialias=True)
  
    #for altitude_raw
    self.pen1 = pg.mkPen(color=(0,0,0), width=2)
    self.pen2 = pg.mkPen(color=(255,0,0), width=3)

    self.y_range = 5
    self.y_shift = self.y_range * 0.25

  def make_item_layout(self):
    self.item_layout = {"Grade":(0, 0), "Grade(spd)":(0, 1), "GlideRatio":(0, 2), "Ascent":(0, 3)}

  def add_extra(self):
    self.layout.addWidget(self.plot, 1, 0, 2, 4)

  def set_border(self):
    self.max_height = 1
    self.max_width = 3

  def set_font_size(self, length):
    self.font_size = int(length / 7)
    self.set_minimum_size()

  def update_extra(self):
   
    v = self.config.logger.sensor.values['integrated']
    all_nan = {'altitude_graph': True, 'altitude_kf_graph': True}
    for key in all_nan.keys():
      chk = np.isnan(v[key])
      if False in chk:
        all_nan[key] = False
    m = [x for x in v['altitude_graph'] if not np.isnan(x)]
    median = None
    if len(m) > 0:
      median = m[-1]
   
    if not all_nan['altitude_graph']:
      self.p1.clear()
      if median != None:
        self.p1.setYRange(median-self.y_range, median+self.y_range)

      self.p1.addItem(
        pg.PlotCurveItem(
          v['altitude_graph'], 
          pen=self.pen1,
          connect="finite"
        )
      )

    if not all_nan['altitude_kf_graph']:
      self.p2.clear()
      
      if median != None:
        self.p2.setYRange(median-self.y_range+self.y_shift, median+self.y_range+self.y_shift)
      
      self.p2.setGeometry(self.p1.vb.sceneBoundingRect())
      self.p2.linkedViewChanged(self.p1.vb, self.p2.XAxis)
      p = pg.PlotCurveItem(
        v['altitude_kf_graph'], 
        pen=self.pen2,
        connect="finite"
        )
      self.p2.addItem(p)

