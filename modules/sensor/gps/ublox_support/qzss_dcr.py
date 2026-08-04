from datetime import datetime
from enum import IntEnum

from pynmeagps import calc_checksum

JMA_MESSAGE_TYPE = 43
DCX_MESSAGE_TYPE = 44
# QZSS L1S uses 250 bits; some firmware adds a ninth SFRBX word.
_QZSS_DCR_DATA_WORDS = 8


class Category(IntEnum):
    EEW = 1
    EPICENTER = 2
    INTENSITY = 3
    NANKAI = 4
    TSUNAMI = 5
    NW_PACIFIC_TSUNAMI = 6
    VOLCANO = 8
    ASH_FALL = 9
    WEATHER = 10
    FLOOD = 11
    TYPHOON = 12
    MARINE = 14


_QZQSM_URGENT_CATEGORY_NOS = {
    Category.EEW,
    Category.NANKAI,
    Category.TSUNAMI,
    Category.NW_PACIFIC_TSUNAMI,
    Category.VOLCANO,
    Category.FLOOD,
}
_QZQSM_WEATHER_URGENT_CODES = {2}
_QZQSM_WEATHER_WARNING_CODES = {23}

_QZSS_DCR_REPORT_FIELD_NAMES = (
    "information_type",
    "weather_warning_state",
    "weather_related_disaster_sub_categories",
    "weather_forecast_regions",
    "typhoon_number",
    "reference_time_type",
    "marine_warning_codes",
    "marine_forecast_regions",
    "dcx_message_type",
    "a4_hazard_type",
    "a5_severity",
    "ex1_target_area_ja",
)

_QZSS_DCR_REPORT_FIELD_EXCLUDES = {
    "sentence",
    "timestamp",
    "message",
    "nmea",
    "message_header",
    "satellite_id",
    "satellite_prn",
    "raw",
    "preamble",
    "message_type",
    "camf",
}


def _as_list(value):
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple, set)) else [value]


def _event_field_sets(event):
    fields = [
        fragment["report_fields"]
        for fragment in event.get("fragments") or ()
        if fragment.get("report_fields")
    ]
    return fields or [event.get("report_fields") or {}]


def _marine_warning_states(event):
    field_sets = _event_field_sets(event)
    report_times = [
        str(fields.get("report_time"))
        for fields in field_sets
        if fields.get("report_time")
    ]
    if report_times:
        latest = max(report_times)
        field_sets = [
            fields for fields in field_sets if str(fields.get("report_time")) == latest
        ]

    states = {}
    for fields in field_sets:
        warnings = _as_list(fields.get("marine_warning_codes"))
        raw_codes = _as_list(fields.get("marine_warning_codes_raw"))
        regions = _as_list(fields.get("marine_forecast_regions"))
        if len(warnings) == 1:
            warnings *= len(regions)
        if len(raw_codes) == 1:
            raw_codes *= len(regions)
        for index, region in enumerate(regions):
            states[str(region)] = (
                str(warnings[index]) if index < len(warnings) else "",
                raw_codes[index] if index < len(raw_codes) else None,
            )
    return [
        (region, warning, raw_code) for region, (warning, raw_code) in states.items()
    ]


def _marine_event_is_cancel(event):
    states = _marine_warning_states(event)
    if not states or any(raw_code is None for _, _, raw_code in states):
        return None
    return all(str(raw_code) == "0" for _, _, raw_code in states)


def _weather_region_pairs(fields):
    subcategories = _as_list(fields.get("weather_related_disaster_sub_categories"))
    raw_subcategories = _as_list(
        fields.get("weather_related_disaster_sub_categories_raw")
    )
    regions = _as_list(fields.get("weather_forecast_regions"))
    raw_regions = _as_list(fields.get("weather_forecast_regions_raw"))
    if len(subcategories) == 1:
        subcategories *= len(regions)
    if len(raw_subcategories) == 1:
        raw_subcategories *= len(regions)
    if len(regions) == 1:
        regions *= max(len(subcategories), len(raw_subcategories))
    if len(raw_regions) == 1:
        raw_regions *= len(regions)
    return [
        (
            subcategory,
            (
                raw_subcategories[index]
                if index < len(raw_subcategories)
                else subcategory
            ),
            region,
            raw_regions[index] if index < len(raw_regions) else region,
        )
        for index, (subcategory, region) in enumerate(zip(subcategories, regions))
    ]


def sfrbx_to_qzqsm(parsed):
    if (
        parsed.gnssId != 5
        or parsed.sigId != 1
        or parsed.numWords < _QZSS_DCR_DATA_WORDS
    ):
        return None

    data = bytearray()
    for i in range(_QZSS_DCR_DATA_WORDS):
        word = getattr(parsed, f"dwrd_{i + 1:02d}", None)
        if word is None:
            return None
        data.extend(word.to_bytes(4, "big"))

    message_type = data[1] >> 2
    if message_type not in (JMA_MESSAGE_TYPE, DCX_MESSAGE_TYPE):
        return None

    satellite_id = (parsed.svId + 182) & 0x3F
    dcr_message = (bytes(data[:31]) + bytes([data[31] & 0xC0])).hex().upper()[:-1]
    sentence = f"$QZQSM,{satellite_id:02d},{dcr_message}"
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


def parse_qzqsm_sentence(sentence):
    if not sentence.startswith("$QZQSM,") or "*" not in sentence:
        return None

    body, checksum = sentence.rsplit("*", 1)
    if calc_checksum(body[1:]) != checksum[:2].upper():
        return None

    fields = body.split(",")
    if len(fields) != 3:
        return None

    message = fields[2].upper()
    if len(message) != 63 or any(ch not in "0123456789ABCDEF" for ch in message):
        return None

    parsed = parse_qzqsm_message(message)
    if parsed is None:
        return None

    decoded_report = decode_qzqsm_report(sentence)
    if decoded_report.get("is_null_message"):
        return None

    parsed.update({"sentence": sentence, "satellite_id": fields[1], "message": message})
    parsed.update(decoded_report)
    return parsed


def decode_qzqsm_report(sentence):
    try:
        import azarashi
    except ImportError as exc:
        return {"report_text": None, "report_decoder_error": str(exc)}

    try:
        report = azarashi.decode(sentence, msg_type="nmea")
    except Exception as exc:
        return {"report_text": None, "report_decoder_error": str(exc)}

    report_text = str(report)
    report_fields = _decoded_report_fields(report)
    dcx_message_type = report_fields.get("dcx_message_type")
    raw = getattr(report, "raw", None)
    canonical_payload = raw.hex().upper() if isinstance(raw, bytes) else None
    return {
        "report_text": report_text,
        "report_decoder": "azarashi",
        "report_fields": report_fields,
        "canonical_payload": canonical_payload,
        "dcx_message_type": dcx_message_type,
        "is_null_message": dcx_message_type == "Null Message",
    }


def _decoded_report_fields(report):
    get_params = getattr(report, "get_params", None)
    if callable(get_params):
        try:
            params = get_params()
        except Exception:
            params = {}
    else:
        params = {}
    if not isinstance(params, dict):
        params = {}

    fields = {
        name: _serialize_report_value(value)
        for name, value in params.items()
        if name not in _QZSS_DCR_REPORT_FIELD_EXCLUDES and value is not None
    }
    for name in _QZSS_DCR_REPORT_FIELD_NAMES:
        value = getattr(report, name, None)
        if value is not None:
            fields[name] = _serialize_report_value(value)
    return fields


def _serialize_report_value(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex().upper()
    if isinstance(value, dict):
        return {str(key): _serialize_report_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize_report_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _is_qzss_dcr_cancellation(message_type, category_no, report_fields, report_text):
    if report_fields.get("information_type_no") == 2 or (
        message_type == DCX_MESSAGE_TYPE
        and report_fields.get("a1_message_type") == "All Clear"
    ):
        return True
    if (
        category_no == Category.TSUNAMI
        and report_fields.get("tsunami_warning_code_raw") == 2
    ):
        return True
    if category_no == Category.FLOOD and _all_raw_values(
        report_fields.get("flood_warning_levels_raw"),
        1,
    ):
        return True
    if category_no == Category.WEATHER and _all_raw_values(
        report_fields.get("weather_warning_state_raw"),
        2,
    ):
        return True
    if category_no == Category.MARINE and _all_raw_values(
        report_fields.get("marine_warning_codes_raw"),
        0,
    ):
        return True
    return any(marker in report_text for marker in ("CANCELLATION", "ALL CLEAR"))


def _all_raw_values(value, expected):
    if value is None:
        return False
    values = list(value) if isinstance(value, (list, tuple)) else [value]
    return bool(values) and all(item == expected for item in values)


def build_qzss_dcr_event(dcr):
    message_type = dcr.get("message_type")
    report_fields = dcr.get("report_fields") or {}
    report_text = dcr.get("report_text") or ""
    is_training = (
        dcr.get("report_classification") == 7
        or report_fields.get("a1_message_type") == "Test"
    )
    category_no = dcr.get("disaster_category")
    is_cancel = _is_qzss_dcr_cancellation(
        message_type,
        category_no,
        report_fields,
        report_text,
    )

    priority = _qzss_dcr_priority(
        message_type=message_type,
        category_no=category_no,
        classification_no=dcr.get("report_classification"),
        report_fields=report_fields,
        is_training=is_training,
    )

    return {
        "body": report_text,
        "priority": priority,
        "category_no": dcr.get("disaster_category"),
        "message_type": message_type,
        "is_test": bool(dcr.get("is_test")),
        "is_training": is_training,
        "is_cancel": is_cancel,
        "report_fields": report_fields,
    }


def build_qzss_dcr_test_event(event_id, alert_level="urgent"):
    if alert_level not in {"urgent", "warning"}:
        raise ValueError(f"Unsupported QZSS DCR test alert level: {alert_level}")

    now = datetime.now().astimezone()
    received_at = now.isoformat()
    sentence = f"TEST-QZSS-DCR-{alert_level.upper()}-{event_id:04d}"
    if alert_level == "urgent":
        category = Category.EEW
        classification = 1
        report_text = "QZSS DCR urgent popup test"
        report_fields = {
            "report_time": received_at,
            "information_type_no": 0,
            "information_type": "発表",
            "occurrence_time_of_earthquake": received_at,
            "seismic_epicenter": "表示テスト震源",
            "seismic_intensity_lower_limit": "震度6弱",
            "eew_forecast_regions": ["関東地方"],
            "magnitude": "7.1",
            "depth_of_hypocenter": "10km",
        }
    else:
        category = Category.TSUNAMI
        classification = 2
        report_text = "QZSS DCR warning popup test"
        report_fields = {
            "report_time": received_at,
            "information_type_no": 0,
            "information_type": "発表",
            "tsunami_warning_code_raw": 3,
            "tsunami_warning_code": "津波警報",
            "tsunami_forecast_regions": ["東京湾内湾"],
            "tsunami_heights": ["3m"],
        }
    return {
        "timestamp": received_at,
        "sentence": sentence,
        "canonical_payload": sentence,
        "is_test": True,
        "message_type": JMA_MESSAGE_TYPE,
        "report_classification": classification,
        "disaster_category": category,
        "report_text": report_text,
        "report_fields": report_fields,
    }


def _qzss_dcx_priority(report_fields, is_training):
    severity = str(report_fields.get("a5_severity") or "")
    if is_training:
        return "warning"
    if severity.startswith(("Extreme", "Severe")):
        return "urgent"
    if severity.startswith("Moderate"):
        return "warning"
    return "normal"


def _qzss_dcr_priority(
    message_type,
    category_no,
    classification_no,
    report_fields,
    is_training,
):
    if classification_no == 1:
        return "urgent"
    if classification_no == 2:
        return "warning"
    if category_no == Category.WEATHER:
        weather_codes = set(
            report_fields.get("weather_related_disaster_sub_categories_raw") or []
        )
        if weather_codes.intersection(_QZQSM_WEATHER_URGENT_CODES):
            return "urgent"
        if weather_codes.intersection(_QZQSM_WEATHER_WARNING_CODES):
            return "warning"
    if is_training and category_no in _QZQSM_URGENT_CATEGORY_NOS:
        return "warning"
    if message_type == DCX_MESSAGE_TYPE:
        return _qzss_dcx_priority(report_fields, is_training)
    if classification_no is None and category_no in _QZQSM_URGENT_CATEGORY_NOS:
        return "warning"
    return "normal"


def parse_qzqsm_message(message):
    if len(message) != 63:
        return None

    bits = "".join(f"{int(ch, 16):04b}" for ch in message.upper())
    message_type = int(bits[8:14], 2)
    parsed = {
        "preamble": int(bits[0:8], 2),
        "message_type": message_type,
    }
    if message_type == JMA_MESSAGE_TYPE:
        report_classification = int(bits[14:17], 2)
        disaster_category = int(bits[17:21], 2)
        parsed.update(
            {
                "report_classification": report_classification,
                "disaster_category": disaster_category,
                "version": int(bits[21:27], 2),
            }
        )
    return parsed
