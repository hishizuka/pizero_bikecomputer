import os

USE_PYQT6 = False
try:
  import PyQt6.QtCore as QtCore
  import PyQt6.QtWidgets as QtWidgets
  USE_PYQT6 = True
except:
  import PyQt5.QtCore as QtCore
  import PyQt5.QtWidgets as QtWidgets
  import PyQt5.QtGui as QtGui

from .pyqt_menu_widget import MenuWidget 

##################################
# debug widgets
##################################

class DebugLogViewerWidget(MenuWidget):

  def setup_menu(self):
    self.menu = QtWidgets.QWidget()
    self.back_index_key = 'menu'
    
    self.menu_layout = QtWidgets.QVBoxLayout()
    self.menu_layout.setContentsMargins(0,0,0,0)
    self.menu_layout.setSpacing(0)

    #self.scroll_area = QtWidgets.QScrollArea()
    #self.scroll_area.setWidgetResizable(True)
    try:
      self.editor = QtWidgets.QTextEdit()
    except:
      #for old Qt (5.11.3 buster PyQt5 Package)
      QtGui.QTextEdit()
    self.editor.setReadOnly(True)
    self.editor.setLineWrapMode(QtWidgets.QTextEdit.LineWrapMode.NoWrap) if USE_PYQT6 else self.editor.setLineWrapMode(0)
    #self.editor.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
    #self.editor.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
    #QtWidgets.QScroller.grabGesture(self, QtWidgets.QScroller.LeftMouseButtonGesture)
    #self.scroll_area.setWidget(self.editor) if USE_PYQT6 else self.menu_layout.addWidget(self.editor)
    #self.menu_layout.addWidget(self.scroll_area)
    self.menu_layout.addWidget(self.editor)

    self.menu.setLayout(self.menu_layout)

  def update_display(self):
    debug_log = 'log/debug.txt'
    if not os.path.exists(debug_log): return
    f = open(debug_log)
    self.editor.setText(f.read())
    f.close()


