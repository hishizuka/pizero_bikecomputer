class ButtonRegistry(dict):
    def disable_if_exists(self, key):
        button = self.get(key)
        if button:
            button.disable()

    def change_toggle_if_exists(self, key, value):
        button = self.get(key)
        if button and hasattr(button, "change_toggle"):
            button.change_toggle(value)

    def onoff_button_if_exists(self, key, value):
        button = self.get(key)
        if button and hasattr(button, "onoff_button"):
            button.onoff_button(value)

    def set_text_if_exists(self, key, text):
        button = self.get(key)
        if button and hasattr(button, "setText"):
            button.setText(text)

    async def run_if_exists(self, key, *args, **kwargs):
        button = self.get(key)
        if button and hasattr(button, "run"):
            await button.run(*args, **kwargs)