import board
import busio
from adafruit_mcp230xx.mcp23008 import MCP23008 as MCP

from .base.button_io_expander import ButtonIOExpander


# https://www.microchip.com/en-us/product/mcp23009
# https://ww1.microchip.com/downloads/en/DeviceDoc/20002121C.pdf

# NOTE: no need to set TEST and RESET address and value, due to adafruit_mcp230xx library handling it.
class MCP23009(ButtonIOExpander):

    # address
    SENSOR_ADDRESS = 0x27

    # The amount of available channels (8 for MCP23009)
    CHANNELS = 8

    def __init__(self, config):
        i2c = busio.I2C(board.SCL, board.SDA)
        self.mcp = MCP(i2c, address=self.SENSOR_ADDRESS)

        super().__init__(config, self.mcp)
