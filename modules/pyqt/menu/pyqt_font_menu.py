from modules.qt._qt_qtwidgets import qasync

from .pyqt_menu_widget import ListWidget


class FontListWidget(ListWidget):
    def __init__(self, parent, page_name, config):
        self.settings = {}
        self.kind = "file" if page_name == "Font" else "weight"
        self.manager = config.gui.font_manager
        super().__init__(parent, page_name, config)
        self.manager.changed.connect(self._update_enabled)
        if self.kind == "file":
            self.manager.files_loaded.connect(self._update_files)

    def preprocess(self, **kwargs):
        if self.kind == "file":
            self.settings = {}
            self.manager.preprocess()
        else:
            self.settings = self.manager.weight_options(self.config.G_FONT_FILE)
        super().preprocess(reset=True)

    def _update_files(self):
        self.settings = {item["title"]: item["value"] for item in self.manager.files}
        super().preprocess(reset=True)
        if self.manager.state["error"]:
            self.config.gui.show_popup(self.manager.state["error"])

    def _update_enabled(self):
        self.setEnabled(not self.manager.state["busy"])

    def preprocess_extra(self):
        self.update_list()
        super().preprocess_extra()

    def get_default_value(self):
        return self.setting_label(self.manager.state[self.kind])

    def back(self):
        if not self.manager.state["busy"]:
            super().back()

    def on_back_menu(self):
        self.manager.cancel_loading()

    @qasync.asyncSlot()
    async def button_func(self):
        if self.manager.state["busy"] or self.selected_item is None:
            return
        value = self.settings[self.selected_item.title]
        if await self.manager.choose(self.kind, value):
            if self.kind == "file":
                self.change_page("Font Weight", preprocess=True, reset=True)
            else:
                self.config.gui.change_menu_page(
                    self.config.gui.gui_config.G_GUI_INDEX["Display"]
                )
        else:
            self.config.gui.show_popup(self.manager.state["error"])
