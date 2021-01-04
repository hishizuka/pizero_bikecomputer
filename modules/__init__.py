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

