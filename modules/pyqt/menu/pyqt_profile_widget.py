try:
    import PyQt6.QtCore as QtCore
    import PyQt6.QtWidgets as QtWidgets
    import PyQt6.QtGui as QtGui
except:
    import PyQt5.QtCore as QtCore
    import PyQt5.QtWidgets as QtWidgets
    import PyQt5.QtGui as QtGui

from .pyqt_menu_widget import MenuWidget


class ProfileWidget(MenuWidget):
    def setup_menu(self):
        self.button = {}

        button_conf = (
            # Name(page_name), button_attribute, connected functions, layout
            ("CP", "submenu", self.adjust_cp),
            ("W Prime Balance", "submenu", self.adjust_w_prime_balance),
        )
        self.add_buttons(button_conf)

    def adjust_cp(self):
        self.change_page("CP", preprocess=True)

    def adjust_w_prime_balance(self):
        self.change_page("W Prime Balance", preprocess=True)
