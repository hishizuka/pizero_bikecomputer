import asyncio

class GUI_None():
    config = None
    gui_config = None

    def __init__(self, config):
        super().__init__()

        self.config = config
        self.config.gui = self

        asyncio.run(self.loop())

    async def loop(self):
        self.config.init_loop(call_from_gui=True)
        self.config.start_coroutine()
        while True:
            try:
                await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                break

    async def set_boot_status(self, text):
        print(text)

    def delay_init(self):
        pass

    def scroll_next(self):
        pass

    def scroll_prev(self):
        pass

