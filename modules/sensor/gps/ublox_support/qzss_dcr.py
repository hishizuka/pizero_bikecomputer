from pynmeagps import calc_checksum

from modules.sensor.gps.qzss.dcr import DCX_MESSAGE_TYPE, JMA_MESSAGE_TYPE

_QZSS_DCR_DATA_WORDS = 8


def sfrbx_to_packet(parsed):
    if (
        parsed.gnssId != 5
        or parsed.sigId != 1
        or parsed.numWords < _QZSS_DCR_DATA_WORDS
    ):
        return None
    data = bytearray()
    for index in range(_QZSS_DCR_DATA_WORDS):
        word = getattr(parsed, f"dwrd_{index + 1:02d}", None)
        if word is None:
            return None
        data.extend(word.to_bytes(4, "big"))
    if data[1] >> 2 not in (JMA_MESSAGE_TYPE, DCX_MESSAGE_TYPE):
        return None
    data[-1] &= 0xC0
    satellite_id = (parsed.svId + 182) & 0x3F
    return bytes([satellite_id]) + bytes(data)


def sfrbx_to_qzqsm(parsed):
    packet = sfrbx_to_packet(parsed)
    if packet is None:
        return None
    sentence = f"$QZQSM,{packet[0]:02d},{packet[1:].hex().upper()[:-1]}"
    return f"{sentence}*{calc_checksum(sentence[1:])}"


def qzss_dcr_enabled(requested, power_save_enabled):
    return requested and not power_save_enabled


def qzss_dcr_blocked_by_power_save(requested, power_save_enabled):
    return requested and power_save_enabled


def qzss_dcr_configure_status(requested, power_save_enabled):
    if qzss_dcr_enabled(requested, power_save_enabled):
        return "pending"
    if qzss_dcr_blocked_by_power_save(requested, power_save_enabled):
        return "disabled_power_save"
    return "disabled"


def qzss_dcr_output_status(enabled, requested, power_save_enabled):
    if enabled:
        return "enabled"
    if qzss_dcr_blocked_by_power_save(requested, power_save_enabled):
        return "disabled_power_save"
    return "disabled"


def qzss_dcr_cfg_data(transport_type, enabled):
    port = "I2C" if transport_type == "i2c" else "UART1"
    output_enabled = int(enabled)
    cfg_data = []
    if enabled:
        # MAX-M10S and MAX-M10N share these QZSS SLAS configuration keys.
        cfg_data.extend(
            [
                ("CFG_SIGNAL_QZSS_ENA", 1),
                ("CFG_QZSS_USE_SLAS_DGNSS", 1),
                ("CFG_QZSS_USE_SLAS_TESTMODE", 0),
            ]
        )
    cfg_data.extend(
        [
            ("CFG_SIGNAL_QZSS_L1S_ENA", output_enabled),
            (f"CFG_MSGOUT_UBX_RXM_SFRBX_{port}", output_enabled),
        ]
    )
    return cfg_data
