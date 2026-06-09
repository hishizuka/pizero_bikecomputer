import hashlib

from pyubx2.ubxhelpers import calc_checksum

_STATE_CHIPCODE = "ublox_assistnow_chipcode"
_STATE_ZTP_TOKEN_ID = "ublox_assistnow_ztp_token_id"
_STATE_LEGACY_TOKEN_ID = "ublox_assistnow_token_id"
_STATE_UNIQUE_ID = "ublox_assistnow_unique_id"


class AssistNowClient:
    def __init__(self, config, state, api_client):
        self.config = config
        self.state = state
        self.api = api_client

    @property
    def enabled(self):
        return bool(self.config["STATUS"])

    @property
    def has_credentials(self):
        return self.enabled and bool(self._ztp_token())

    @property
    def has_cached_chipcode(self):
        return self.enabled and bool(self._cached_chipcode())

    async def get_messages(self, sec_uniqid_raw=None, mon_ver_raw=None):
        async def request():
            if sec_uniqid_raw is None or mon_ver_raw is None:
                chipcode = self._cached_chipcode()
                if not chipcode:
                    raise RuntimeError("AssistNow cached chipcode is not available")
            else:
                chipcode = await self._get_chipcode(sec_uniqid_raw, mon_ver_raw)
            return await self.api.get_ublox_assistnow_data(chipcode)

        response = await self.api.run_ublox_assistnow_session(request)
        return list(iter_ubx_messages(response))

    async def _get_chipcode(self, sec_uniqid_raw, mon_ver_raw):
        ztp_token = self._ztp_token().lower()
        if not ztp_token:
            raise RuntimeError("AssistNow ZTP_TOKEN is not configured")

        unique_id = _receiver_unique_id(sec_uniqid_raw)
        ztp_token_id = _ztp_token_id(ztp_token)
        chipcode = self._chipcode(unique_id, ztp_token_id)
        if chipcode:
            return chipcode

        chipcode = await self.api.get_ublox_assistnow_chipcode(
            ztp_token,
            sec_uniqid_raw,
            mon_ver_raw,
        )
        self.state.set_value(_STATE_ZTP_TOKEN_ID, ztp_token_id)
        self.state.set_value(_STATE_UNIQUE_ID, unique_id)
        self.state.set_value(_STATE_CHIPCODE, chipcode, force_apply=True)
        return chipcode

    def _chipcode(self, unique_id, ztp_token_id):
        if self.state.get_value(_STATE_UNIQUE_ID, "") != unique_id:
            return ""
        if self._cached_ztp_token_id() != ztp_token_id:
            return ""
        return self.state.get_value(_STATE_CHIPCODE, "")

    def _cached_chipcode(self):
        ztp_token = self._ztp_token().lower()
        if not ztp_token:
            return ""
        ztp_token_id = _ztp_token_id(ztp_token)
        if self._cached_ztp_token_id() != ztp_token_id:
            return ""
        return self.state.get_value(_STATE_CHIPCODE, "")

    def _cached_ztp_token_id(self):
        return self.state.get_value(
            _STATE_ZTP_TOKEN_ID,
            self.state.get_value(_STATE_LEGACY_TOKEN_ID, ""),
        )

    def _ztp_token(self):
        return self.config["ZTP_TOKEN"].strip()


def _receiver_unique_id(sec_uniqid_raw):
    return sec_uniqid_raw.hex().upper()


def _ztp_token_id(ztp_token):
    return hashlib.sha256(ztp_token.encode("utf-8")).hexdigest()


def iter_ubx_messages(data):
    pos = 0
    while True:
        start = data.find(b"\xb5\x62", pos)
        if start < 0:
            return
        if start + 8 > len(data):
            return

        payload_len = int.from_bytes(data[start + 4 : start + 6], "little")
        end = start + 6 + payload_len + 2
        if end > len(data):
            return

        message = data[start:end]
        checksum = calc_checksum(message[2:-2])
        if checksum == message[-2:]:
            yield message
            pos = end
        else:
            pos = start + 1
