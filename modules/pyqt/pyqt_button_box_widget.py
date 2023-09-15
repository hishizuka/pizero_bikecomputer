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


class ButtonBoxWidget(QtWidgets.QWidget):

  config = None

  #for long press
  lap_button_count = 0
  start_button_count = 0

  def __init__(self, parent, config):
    self.config = config
    QtWidgets.QWidget.__init__(self, parent=parent)
    self.setup_ui()

    self.start_button.clicked.connect(self.gui_start_and_stop_quit)
    self.lap_button.clicked.connect(self.gui_lap_reset)
    self.menu_button.clicked.connect(self.config.gui.goto_menu)
    self.scrollnext_button.clicked.connect(self.config.gui.scroll_next)
    self.scrollprev_button.clicked.connect(self.config.gui.scroll_prev)

  def setup_ui(self):
    
    self.setContentsMargins(0,0,0,0)
    self.setStyleSheet(self.config.gui.style.G_GUI_PYQT_button_box)
    self.show()
    self.setAutoFillBackground(True)
    
    self.start_button = QtWidgets.QPushButton(QtGui.QIcon(self.config.gui.gui_config.icon_dir+'img/next_white.png'),"")
    self.lap_button = QtWidgets.QPushButton(QtGui.QIcon(self.config.gui.gui_config.icon_dir+'img/lap_white.png'),"")
    self.menu_button = QtWidgets.QPushButton(QtGui.QIcon(self.config.gui.gui_config.icon_dir+'img/menu.png'),"")
    self.scrollnext_button = QtWidgets.QPushButton(QtGui.QIcon(self.config.gui.gui_config.icon_dir+'img/forward_black.svg'),"")
    self.scrollprev_button = QtWidgets.QPushButton(QtGui.QIcon(self.config.gui.gui_config.icon_dir+'img/back_black.svg'),"")

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

  def gui_lap_reset(self):
    if self.lap_button.isDown():
      if self.lap_button._state == 0:
        self.lap_button._state = 1
      else:
        self.lap_button_count += 1
        print('lap button pressing : ', self.lap_button_count)
        if self.lap_button_count == self.config.button_config.G_BUTTON_LONG_PRESS:
          print('reset')
          self.config.logger.reset_count()
          self.config.gui.map_widget.reset_track()
          self.lap_button_count = 0
    elif self.lap_button._state == 1:
      self.lap_button._state = 0
      self.lap_button_count = 0
    else:
      self.config.logger.count_laps()

  def gui_start_and_stop_quit(self):
    if self.start_button.isDown():
      if self.start_button._state == 0:
        self.start_button._state = 1
      else:
        self.start_button_count += 1
        print('start button pressing : ', self.start_button_count)
        if self.start_button_count == self.config.button_config.G_BUTTON_LONG_PRESS:
          print('quit or poweroff')
          self.config.gui.quit()
    elif self.start_button._state == 1:
      self.start_button._state = 0
      self.start_button_count = 0
    else:
      self.config.logger.start_and_stop_manual()

  def change_start_stop_button(self, status):
    icon = QtGui.QIcon(self.config.gui.gui_config.icon_dir+'img/next_white.png')
    if status == "START":
      icon = QtGui.QIcon(self.config.gui.gui_config.icon_dir+'img/pause_white.png')
    self.start_button.setIcon(icon)
