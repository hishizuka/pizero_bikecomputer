import os

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

    self.scroll_area = QtWidgets.QScrollArea()
    self.scroll_area.setWidgetResizable(True)
    self.editor = QtGui.QTextEdit()
    self.editor.setReadOnly(True)
    self.editor.setLineWrapMode(0)
    #self.editor.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
    #self.editor.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
    QtWidgets.QScroller.grabGesture(self, QtWidgets.QScroller.LeftMouseButtonGesture)
    #self.menu_layout.addWidget(self.editor)
    self.scroll_area.setWidget(self.editor)
    self.menu_layout.addWidget(self.scroll_area)

    self.menu.setLayout(self.menu_layout)

  def update_display(self):
    debug_log = 'log/debug.txt'
    if not os.path.exists(debug_log): return
    f = open(debug_log)
    self.editor.setText(f.read())
    f.close()


