import struct
from datetime import datetime

from . import ant_device
from . import ant_device_ctrl


class ANT_Device_Search(ant_device.ANT_Device):
    name = "SEARCH"
    ant_config = {
        "interval": (),  # Not use
        "type": 0,  # ANY
        "channel_type": 0x00,  # Channel.Type.BIDIRECTIONAL_RECEIVE,
    }
    isUse = False
    searchList = None
    searchState = False

    def __init__(self, node, config, values=None):
        self.node = node
        self.config = config
        if self.config.G_ANT["STATUS"]:
            # special use of make_channel(c_type, search=False)
            self.make_channel(self.ant_config["channel_type"], ext_assign=0x01)

    def on_data(self, data):
        if not self.searchState:
            return
        if len(data) == 13:
            (antID, antType) = self.structPattern["ID"].unpack(data[9:12])
            if antType in self.config.G_ANT["TYPES"][self.antName]:
                # new ANT+ sensor
                self.searchList[antID] = (antType, False)

    def on_data_ctrl(self, data):
        if not self.searchState:
            return
        if len(data) == 8:
            (antID,) = struct.Struct("<H").unpack(data[1:3])
            antType = 0x10
            if antType in self.config.G_ANT["TYPES"][self.antName]:
                # new ANT+ sensor
                self.searchList[antID] = (antType, False)

    def search(self, antName):
        self.searchList = {}
        for k, v in self.config.G_ANT["USE"].items():
            if k == antName:
                continue
            if v and k in self.config.G_ANT["ID_TYPE"]:
                (antID, antType) = struct.unpack("<HB", self.config.G_ANT["ID_TYPE"][k])
                if antType in self.config.G_ANT["TYPES"][antName]:
                    # already connected
                    self.searchList[antID] = (antType, True)

        if self.config.G_ANT["STATUS"] and not self.searchState:
            self.antName = antName

            if self.antName not in ["CTRL"]:
                self.set_wait_quick_mode()
                self.channel.set_search_timeout(0)
                self.channel.set_rf_freq(57)
                self.channel.set_id(0, 0, 0)

                self.channel.enable_extended_messages(1)
                self.channel.set_low_priority_search_timeout(0xFF)
                self.node.set_lib_config(0x80)

                self.connect(isCheck=False, isChange=False)  # USE: False -> True

            elif self.antName == "CTRL":
                self.ctrl_searcher = ant_device_ctrl.ANT_Device_CTRL(
                    self.node, self.config, {}, antName
                )
                self.ctrl_searcher.channel.on_acknowledge_data = self.on_data_ctrl
                self.ctrl_searcher.send_data = True
                self.ctrl_searcher.connect(isCheck=False, isChange=False)

            self.searchState = True

    def stop_search(self, resetWait=True):
        if self.config.G_ANT["STATUS"] and self.searchState:
            if self.antName not in ["CTRL"]:
                self.disconnect(isCheck=False, isChange=False)  # USE: True -> False

                # for background scan
                self.channel.enable_extended_messages(0)
                self.node.set_lib_config(0x00)
                self.channel.set_low_priority_search_timeout(0x00)

                if resetWait:
                    self.set_wait_normal_mode()

            elif self.antName == "CTRL":
                self.ctrl_searcher.disconnect(isCheck=False, isChange=False)
                self.ctrl_searcher.delete()
                del self.ctrl_searcher

            self.searchState = False

    def getSearchList(self):
        if self.config.G_ANT["STATUS"]:
            return self.searchList
        else:
            # dummy
            timestamp = datetime.now()
            if 0 < timestamp.second % 30 < 15:
                return {
                    12345: (0x79, False),
                    23456: (0x7A, False),
                    6789: (0x78, False),
                }
            elif 15 < timestamp.second % 30 < 30:
                return {
                    12345: (0x79, False),
                    23456: (0x7A, False),
                    34567: (0x7B, False),
                    45678: (0x0B, False),
                    45679: (0x0B, True),
                    56789: (0x78, False),
                    6789: (0x78, False),
                }
            else:
                return {}
