#!/usr/bin/python3

import datetime

from logger import app_logger


def main():
    app_logger.info("########## INITIALIZE START ##########")

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
    total_time = sum(time_profile)

    app_logger.info("Initialize modules:")
    app_logger.info(f"config import : {time_profile[0]:.3f} sec")
    app_logger.info(f"config init   : {time_profile[1]:.3f} sec")
    app_logger.info(f"display import: {time_profile[2]:.3f} sec")
    app_logger.info(f"display init  : {time_profile[3]:.3f} sec")
    app_logger.info(f"import gui    : {time_profile[4]:.3f} sec")
    app_logger.info(f"import logger : {time_profile[5]:.3f} sec")
    app_logger.info(f"total         : {total_time:.3f} sec")
    app_logger.info("########## INITIALIZE END ##########")
    config.boot_time += total_time

    if config.G_GUI_MODE == "PyQt":
        gui_pyqt.GUI_PyQt(config)


if __name__ == "__main__":
    main()
