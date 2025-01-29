from modules.app_logger import app_logger
from modules._qt_qtwidgets import QtWidgets
from modules.pyqt.components import box_buttons, icons


class ButtonBoxWidget(QtWidgets.QWidget):
    STYLES = """
      background-color: #CCCCCC;
    """

    config = None

    # for long press
    lap_button_count = 0
    start_button_count = 0

    def __init__(self, parent, config):
        self.config = config
        super().__init__(parent=parent)
        self.setup_ui()

    def setup_ui(self):
        self.setContentsMargins(0, 0, 0, 0)
        self.setStyleSheet(self.STYLES)
        self.show()
        self.setAutoFillBackground(True)

        self.start_button = box_buttons.StartButton()
        self.lap_button = box_buttons.LapButton()
        menu_button = box_buttons.MenuButton()
        scrollnext_button = box_buttons.ScrollNextButton()
        scrollprev_button = box_buttons.ScrollPrevButton()

        self.start_button.clicked.connect(self.gui_start_and_stop_quit)
        self.lap_button.clicked.connect(self.gui_lap_reset)
        menu_button.clicked.connect(self.config.gui.goto_menu)
        scrollnext_button.clicked.connect(self.config.gui.scroll_next)
        scrollprev_button.clicked.connect(self.config.gui.scroll_prev)

        button_layout = QtWidgets.QHBoxLayout(self)
        button_layout.setContentsMargins(0, 5, 0, 5)
        button_layout.setSpacing(0)

        button_layout.addWidget(scrollprev_button)
        button_layout.addWidget(self.lap_button)
        button_layout.addWidget(menu_button)
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(scrollnext_button)

    def gui_lap_reset(self):
        if self.lap_button.isDown():
            if self.lap_button._state == 0:
                self.lap_button._state = 1
            else:
                self.lap_button_count += 1
                app_logger.info(f"lap button pressing: {self.lap_button_count}")
                if (
                    self.lap_button_count
                    == self.config.button_config.G_BUTTON_LONG_PRESS
                ):
                    app_logger.info("reset")
                    self.config.gui.reset_count()
                    self.lap_button_count = 0
        elif self.lap_button._state == 1:
            self.lap_button._state = 0
            self.lap_button_count = 0
        else:
            self.config.gui.count_laps()

    def gui_start_and_stop_quit(self):
        if self.start_button.isDown():
            if self.start_button._state == 0:
                self.start_button._state = 1
            else:
                self.start_button_count += 1
                app_logger.info(f"start button pressing: {self.start_button_count}")
                if (
                    self.start_button_count
                    == self.config.button_config.G_BUTTON_LONG_PRESS
                ):
                    app_logger.info("quit or poweroff")
                    self.config.gui.quit()
        elif self.start_button._state == 1:
            self.start_button._state = 0
            self.start_button_count = 0
        else:
            self.config.gui.start_and_stop_manual()

    def change_start_stop_button(self, status):
        icon = icons.PauseIcon() if status == "START" else icons.NextIcon()
        self.start_button.setIcon(icon)
