from modules._qt_qtwidgets import QtWidgets


class NaviButton(QtWidgets.QPushButton):
    STYLES = """
      QPushButton {
        color: none;
        border: 0px solid #FFFFFF;
        border-radius: 15px;
        outline: 0;
      }

      QPushButton:pressed {
        background-color: white;
      }

      QPushButton[style='menu']:focus {
        border-color: white; border-width: 3px;
      }
    """

    def __init__(self, *__args):
        super().__init__(*__args)
        self.setStyleSheet(self.STYLES)
