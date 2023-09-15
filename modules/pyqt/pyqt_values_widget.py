from .pyqt_screen_widget import ScreenWidget

#################################
# values only widget
#################################


class ValuesWidget(ScreenWidget):
    def __init__(self, parent, config, item_layout):
        self.item_layout = item_layout
        super().__init__(parent, config)

    def set_minimum_size(self):
        super().set_minimum_size()
        h = int(self.height() / (self.max_height + 1))
        for i in range(self.max_height + 1):
            self.layout.setRowMinimumHeight(i, h)
