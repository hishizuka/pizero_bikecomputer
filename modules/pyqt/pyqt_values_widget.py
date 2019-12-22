from .pyqt_screen_widget import ScreenWidget

#################################
# values only widget 
#################################

class ValuesWidget(ScreenWidget):
  def __init__(self, parent, config, item_layout, onoff=True):
    self.onoff = onoff
    self.item_layout = item_layout
    super().__init__(parent, config)

  def set_minimum_size(self):
    for i in range(self.max_width+1):
      self.layout.setColumnMinimumWidth(i, int(self.config.G_WIDTH/(self.max_width+1)))
    for i in range(self.max_height+1):
      self.layout.setRowMinimumHeight(i, int(self.config.G_HEIGHT/(self.max_height+1)))

