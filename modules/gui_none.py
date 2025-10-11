import asyncio

class GUI_None():
    config = None
    gui_config = None

    def __init__(self, config):
        super().__init__()

        self.config = config
        self.config.gui = self

        try:
            asyncio.run(self.config.start_coroutine())
        except KeyboardInterrupt:
            asyncio.run(self.config.quit())

    async def set_boot_status(self, text):
        print(text)

    def delay_init(self):
        pass

    def scroll_next(self):
        pass

    def scroll_prev(self):
        pass

