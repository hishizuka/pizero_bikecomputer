#!/usr/bin/python3

import datetime


def main():
    print()
    print("########## INITIALIZE START ##########")
    print()
    time_profile = []

    t1 = datetime.datetime.now()
    from modules import config

    t2 = datetime.datetime.now()
    time_profile.append((t2 - t1).total_seconds())

    t1 = t2
    config = config.Config()
    t2 = datetime.datetime.now()
    time_profile.append((t2 - t1).total_seconds())

    # display
    t1 = t2
    from modules.display.display_core import Display

    t2 = datetime.datetime.now()
    time_profile.append((t2 - t1).total_seconds())

    t1 = t2
    config.set_display(Display(config, {}))
    t2 = datetime.datetime.now()
    time_profile.append((t2 - t1).total_seconds())

    # minimal gui
    t1 = t2
    if config.G_GUI_MODE == "PyQt":
        from modules import gui_pyqt
    else:
        raise ValueError(f"{config.G_GUI_MODE} mode not supported")

    t2 = datetime.datetime.now()
    time_profile.append((t2 - t1).total_seconds())

    t1 = t2
    from modules import logger_core

    logger = logger_core.LoggerCore(config)
    config.set_logger(logger)
    t2 = datetime.datetime.now()
    time_profile.append((t2 - t1).total_seconds())

    print()
    print("Initialize modules:")
    print("  config import : {:.3f} sec".format(time_profile[0]))
    print("  config init   : {:.3f} sec".format(time_profile[1]))
    print("  display import: {:.3f} sec".format(time_profile[2]))
    print("  display init  : {:.3f} sec".format(time_profile[3]))
    print("  import gui    : {:.3f} sec".format(time_profile[4]))
    print("  import logger : {:.3f} sec".format(time_profile[5]))
    print("  total         : {:.3f} sec".format(sum(time_profile)))
    print()
    print("########## INITIALIZE END ##########")
    config.boot_time += sum(time_profile)

    if config.G_GUI_MODE == "PyQt":
        gui_pyqt.GUI_PyQt(config)


if __name__ == "__main__":
    main()
