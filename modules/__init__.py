import datetime

t1 = datetime.datetime.now()
from . import config
t2 = datetime.datetime.now()
print("\tconfig :", (t2-t1).total_seconds(),"sec")
t1 = t2

from . import logger_core
t2 = datetime.datetime.now()
print("\tlogger_core :", (t2-t1).total_seconds(),"sec")
t1 = t2

from . import gui_pyqt
t2 = datetime.datetime.now()
print("\tgui_pyqt :", (t2-t1).total_seconds(),"sec")
t1 = t2

#from . import gui_qml
#t2 = datetime.datetime.now()
#print("\tgui_qml :", (t2-t1).total_seconds(),"sec")
#t1 = t2

#from . import gui_kivy
#t2 = datetime.datetime.now()
#print("\tgui_kivy :", (t2-t1).total_seconds(),"sec")
#t1 = t2

