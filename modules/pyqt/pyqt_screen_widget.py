import traceback

import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets

from .pyqt_item import Item

#################################
# values only widget 
#################################

class ScreenWidget(QtWidgets.QWidget):

  config = None
  logger = None
  sensor = None
  onoff = True
  items = None
  item_layout = None
  max_width = max_height = 0
  font_size = 12

  def __init__(self, parent, config):
    self.config = config
    self.logger = self.config.logger
    self.sensor = self.logger.sensor

    QtWidgets.QWidget.__init__(self, parent=parent)
    self.init_extra() 
    self.setup_ui()
  
  def resizeEvent(self, event):
    #w = self.size().width()
    h = self.size().height()
    self.set_font_size(h)
    for i in self.items:
      i.update_font_size(self.font_size)
    self.resize_extra()

  def resize_extra(self):
    pass

  def init_extra(self):
    pass

  def setup_ui(self):
    self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

    # update panel setting
    self.timer = QtCore.QTimer(parent=self)
    self.timer.timeout.connect(self.update_display)

    #layout
    self.layout = QtWidgets.QGridLayout()
    self.layout.setContentsMargins(0,0,0,0)
    self.layout.setSpacing(0)

    self.setup_ui_extra()
       
    self.make_item_layout() 
    self.set_border()
    self.set_font_size(self.config.G_HEIGHT)
    self.add_items()
    self.add_extra()
    self.setLayout(self.layout)

  #call from on_change_main_page in gui_pyqt.py
  def start(self):
    self.timer.start(self.config.G_DRAW_INTERVAL)
  
  #call from on_change_main_page in gui_pyqt.py
  def stop(self):
    self.timer.stop()

  def setup_ui_extra(self):
    pass
 
  #if make make_item_layout by hard cording
  def make_item_layout(self):
    pass
 
  def set_border(self):
    for key, pos in self.item_layout.items():
      if pos[0] > self.max_height:
        self.max_height = pos[0]
      if pos[1] > self.max_width:
        self.max_width = pos[1]
      if len(pos) == 4:
        if pos[2] - 1 > self.max_height:
          self.max_height = pos[2]
        if pos[3] - 1 > self.max_width:
          self.max_width = pos[3]

  def set_font_size(self, length): 
    #need to modify for automation and scaling 
    self.font_size = int(length / 6)  # 2 rows (100px)
    if self.max_height == 2: # 3 rows (66px)
      self.font_size = int(length / 7)
    elif self.max_height == 3: # 4 rows (50px)
      self.font_size = int(length / 10)
    elif self.max_height >= 4: # 5 rows~ (40px)
      self.font_size = int(length / 15)
  
    self.set_minimum_size()
    
  def set_minimum_size(self):
    pass

  def add_items(self):
    self.items = []
    for key,pos in self.item_layout.items():
      bottom_flag = False
      right_flag = False
      if pos[0] == self.max_height:
        bottom_flag = True
      if pos[1] == self.max_width:
        right_flag = True
      if len(pos) == 4:
        if pos[2] - 1 == self.max_height:
          bottom_flag = True
        if pos[3] - 1 == self.max_width:
          right_flag = True

      item = Item()
      item.set_init_value(
        config = self.config,
        name = key,
        font_size = self.font_size,
        bottom_flag = bottom_flag,
        right_flag = right_flag
      )
      self.items.append(item)
      
      if len(pos) == 4 :
        self.layout.addLayout(item, pos[0], pos[1], pos[2], pos[3])
      else:
        self.layout.addLayout(item, pos[0], pos[1])

  def add_extra(self):
    pass

  def update_display(self):
    for item in self.items:
      #item.update_value(eval(self.config.gui.gui_config.[item.name][1]))
      try:
        item.update_value(eval(self.config.gui.gui_config.G_ITEM_DEF[item.name][1]))
      except KeyError:
        pass
        #item.update_value(None)
        #print("KeyError :", self.config.gui.gui_config.G_ITEM_DEF[item.name][1])
        #traceback.print_exc()
      except:
        item.update_value(None)
        print("###update_display### : ", item.name, eval(self.config.gui.gui_config.G_ITEM_DEF[item.name][1]))
        traceback.print_exc()
    self.update_extra()

  def update_extra(self):
    pass



