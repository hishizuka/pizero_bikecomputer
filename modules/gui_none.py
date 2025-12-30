import asyncio

class GUI_None():
    config = None
    gui_config = None

    def __init__(self, config):
        super().__init__()

        self.config = config
        self.config.gui = self

        asyncio.run(self._run())

    async def _run(self):
        try:
            await self.config.start_coroutine()
        except asyncio.CancelledError:
            # Allow graceful shutdown when Ctrl+C cancels the main task.
            pass
        finally:
            if self.config.app_close_event is not None and not self.config.app_close_event.is_set():
                try:
                    await self.config.quit()
                except asyncio.CancelledError:
                    pass

    async def set_boot_status(self, text):
        print(text)

    def delay_init(self):
        pass

    def scroll_next(self):
        pass

    def scroll_prev(self):
        pass
