from .pyqt_menu_widget import MenuWidget


class ProfileWidget(MenuWidget):
    def setup_menu(self):
        button_conf = (
            # MenuConfig Key, Name(page_name), button_attribute, connected functions, layout
            ("CP", "CP", "submenu", self.adjust_cp),
            ("W_PRIME_BALANCE", "W Prime Balance", "submenu", self.adjust_w_prime_balance),
        )
        self.add_buttons(button_conf)

    def adjust_cp(self):
        self.change_page("CP", preprocess=True)

    def adjust_w_prime_balance(self):
        self.change_page("W Prime Balance", preprocess=True)
