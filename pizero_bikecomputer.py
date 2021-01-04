#!/usr/bin/python3

import datetime
print("Loading original modules...")
t = datetime.datetime.now()

import modules
print("Loading modules... done :", (datetime.datetime.now()-t).total_seconds(),"sec")

#import logging
#logging.basicConfig(level=logging.DEBUG)
#logging.basicConfig(filename='example.log', level=logging.DEBUG)


def main():

  time_profile = [datetime.datetime.now(),] #for time profile
  config = modules.config.Config()
  time_profile.append(datetime.datetime.now()) #for time profile
  logger = modules.logger_core.LoggerCore(config)
  config.set_logger(logger)
  time_profile.append(datetime.datetime.now()) #for time profile

  sec_diff = [] #for time profile
  for i in range(len(time_profile)):
    if i == 0:
      continue
    sec_diff.append("{0:.6f}".format((time_profile[i]-time_profile[i-1]).total_seconds()))
  print("\tconfig/logger:", sec_diff)

  gui = None
  if config.G_HEADLESS:
    pass
  elif config.G_GUI_MODE == "PyQt":
    print("running in PyQt...")
    t1 = datetime.datetime.now()
    from modules import gui_pyqt
    print("\tgui_pyqt :", (datetime.datetime.now()-t1).total_seconds(),"sec")
    gui = gui_pyqt.GUI_PyQt(config)
  #elif config.G_GUI_MODE == "QML":
  #  print("running in QML...")
  #  gui = modules.gui_qml.GUI_QML(config)
  #elif config.G_GUI_MODE == "kivy":
  #  print("running in kivy...")
  #  gui = modules.gui_kivy.GUI_Kivy(config)


if __name__ == "__main__":
  main()


