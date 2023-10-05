from modules._pyqt import QtWidgets


class MapButton(QtWidgets.QPushButton):
    STYLES = """
      QPushButton {
        border-radius: 15px;
        border-style: outset;
        border-width: 1px;
        font-size: 25px;
        color: rgba(0, 0, 0, 192);
        background: rgba(255, 255, 255, 128);
      }

      QPushButton:pressed {
        background-color: rgba(0, 0, 0, 128);
      }
    """

    def __init__(self, *__args):
        super().__init__(*__args)
        self.setStyleSheet(self.STYLES)
