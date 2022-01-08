try:
  import PyQt6.QtCore as QtCore
  import PyQt6.QtWidgets as QtWidgets
  import PyQt6.QtGui as QtGui
except:
  import PyQt5.QtCore as QtCore
  import PyQt5.QtWidgets as QtWidgets
  import PyQt5.QtGui as QtGui

from .pyqt_screen_widget import ScreenWidget

#################################
# values only widget 
#################################

#https://stackoverflow.com/questions/46505130/creating-a-marquee-effect-in-pyside/
class MarqueeLabel(QtWidgets.QLabel):
  def __init__(self, config, parent=None):
    QtWidgets.QLabel.__init__(self, parent)
    self.config = config
    self.px = 0
    self.py = 18
    self.timer = QtCore.QTimer(self)
    self.timer.timeout.connect(self.update)
    self.timer_interval = 200 #[ms]
    self._speed = 5
    self.textLength = 0

  def setText(self, text):
    super().setText(text)
    self.textLength = self.fontMetrics().horizontalAdvance(text)
    if self.textLength > self.width() and self.config.G_CUESHEET_SCROLL:
      self.timer.start(self.timer_interval)

  def paintEvent(self, event):
    painter = QtGui.QPainter(self)
    self.py = int(self.height()*0.9)
    if self.textLength <= self.width() or not self.config.G_CUESHEET_SCROLL:
      painter.drawText(self.px+5, self.py, self.text())
      return
    
    if self.px <= -self.fontMetrics().horizontalAdvance(self.text()):
      self.px = self.width()
    painter.drawText(self.px, self.py, self.text())
    painter.translate(self.px, 0)
    self.px -= self._speed


class CueSheetItem(QtWidgets.QVBoxLayout):
  dist = None
  name = None
  
  def __init__(self, parent, config):
    self.config = config

    QtWidgets.QVBoxLayout.__init__(self)
    self.setContentsMargins(0,0,0,0)
    self.setSpacing(0)
    
    self.dist = QtWidgets.QLabel()
    self.dist.setWordWrap(False)
    #self.name = QtWidgets.QLabel()
    self.name = MarqueeLabel(self.config)
    self.name.setWordWrap(False)
    
    self.dist.setStyleSheet("QLabel {padding: 0px 0px 0px 0px;}")
    #self.name.setStyleSheet("QLabel {padding: 0px 0px 10px 10px;}")
    if self.config.G_FONT_NAME != "":
      self.name.setStyleSheet("QLabel {font-family:" + self.config.G_FONT_NAME + ";}")

    self.addWidget(self.dist)
    self.addWidget(self.name)

  def update_font_size(self, font_size):
    for text, fsize in zip([self.dist, self.name], [int(font_size*0.9), font_size]):
      q = text.font()
      q.setPixelSize(fsize)
      #q.setStyleStrategy(QtGui.QFont.NoSubpixelAntialias) #avoid subpixel antialiasing on the fonts if possible
      #q.setStyleStrategy(QtGui.QFont.NoAntialias) #don't antialias the fonts
      text.setFont(q)


class CueSheetWidget(ScreenWidget):

  def init_extra(self):
    self.gps_values = self.config.logger.sensor.values['GPS']

  def setup_ui(self):
    
    self.setSizePolicy(self.config.gui.gui_config.expanding, self.config.gui.gui_config.expanding)
    
    # update panel setting
    self.timer = QtCore.QTimer(parent=self)
    self.timer.timeout.connect(self.update_extra)

    self.cuesheet = []
    for i in range(self.config.G_CUESHEET_DISPLAY_NUM):
      cuesheet_point_layout = CueSheetItem(self, self.config)
      self.cuesheet.append(cuesheet_point_layout)

    self.cuesheet_layout = QtWidgets.QVBoxLayout(self)
    self.cuesheet_layout.setContentsMargins(0,0,0,0)
    self.cuesheet_layout.setSpacing(0)
    for c in self.cuesheet:
      self.cuesheet_layout.addLayout(c)

    self.setStyleSheet("\
        border-width: 0px 0px 0px 1px; \
        border-style: solid; \
        border-color: #000000;"
      )
    for i in range(len(self.cuesheet)-1):
      self.cuesheet[i].name.setStyleSheet(
        self.cuesheet[i].name.styleSheet() + " QLabel {border-bottom: 1px solid #CCCCCC;}"
        )
  
  def resizeEvent(self, event):
    #w = self.size().width()
    h = self.size().height()
    self.set_font_size(h)
    for i in self.cuesheet:
      #i.update_font_size(int(self.font_size*0.66))
      i.update_font_size(int(self.font_size)) #for 3 rows

  def set_font_size(self, length):
    self.font_size = int(length / 7)

  def update_extra(self):
    if len(self.config.logger.course.point_distance) == 0 or self.config.G_CUESHEET_DISPLAY_NUM == 0:
      return
    
    cp_i = self.gps_values['course_point_index']
    
    #cuesheet
    for j in range(len(self.cuesheet)):
      if cp_i+j > len(self.config.logger.course.point_distance)-1:
        self.cuesheet[j].dist.setText("")
        self.cuesheet[j].name.setText("")
        continue
      dist = self.config.logger.course.point_distance[cp_i+j]*1000 - self.gps_values['course_distance']
      if dist < 0:
        continue
      text = "{0:6.0f}m  ".format(dist)
      if dist > 1000:
        text = "{0:4.1f}km ".format(dist/1000)
      self.cuesheet[j].dist.setText(text)
      #text = self.config.logger.course.point_name[cp_i+j]
      text = self.config.logger.course.point_type[cp_i+j]
      self.cuesheet[j].name.setText(text)

