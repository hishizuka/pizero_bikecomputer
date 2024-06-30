#!/usr/bin/python3

from logger import app_logger
from modules.utils.timer import Timer, log_timers


def main():
    app_logger.info("########## INITIALIZE START ##########")

    # ensure visually alignment for log
    timers = [
        Timer(auto_start=False, text="  config import : {0:.3f} sec"),
        Timer(auto_start=False, text="  config init   : {0:.3f} sec"),
        Timer(auto_start=False, text="  display import: {0:.3f} sec"),
        Timer(auto_start=False, text="  display init  : {0:.3f} sec"),
        Timer(auto_start=False, text="  import gui    : {0:.3f} sec"),
        Timer(auto_start=False, text="  import logger : {0:.3f} sec"),
    ]

    with timers[0]:
        from modules import config

    with timers[1]:
        config = config.Config()

    # display
    with timers[2]:
        from modules.display.display_core import init_display

    with timers[3]:
        config.set_display(init_display(config))

    # minimal gui
    with timers[4]:
        if config.G_GUI_MODE == "PyQt":
            from modules import gui_pyqt
        else:
            raise ValueError(f"{config.G_GUI_MODE} mode not supported")

    with timers[5]:
        from modules import logger_core

        logger = logger_core.LoggerCore(config)
        config.set_logger(logger)

    app_logger.info("Initialize modules:")
    total_time = log_timers(timers, text_total="  total         : {0:.3f} sec")
    app_logger.info("########## INITIALIZE END ##########")
    config.boot_time += total_time

    if config.G_GUI_MODE == "PyQt":
        gui_pyqt.GUI_PyQt(config)


if __name__ == "__main__":
    main()
