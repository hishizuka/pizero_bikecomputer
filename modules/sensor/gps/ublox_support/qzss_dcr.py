from datetime import datetime

from pynmeagps import calc_checksum

_QZQSM_MESSAGE_TYPE = {
    43: "災危通報（気象庁防災情報）",
    44: "災危通報（他機関）",
}

_QZQSM_REPORT_CLASSIFICATION = {
    1: "最優先",
    2: "優先",
    3: "通常",
    7: "訓練・試験",
}

_QZQSM_DISASTER_CATEGORY = {
    1: "緊急地震速報",
    2: "震源",
    3: "震度",
    4: "南海トラフ地震",
    5: "津波",
    6: "北西太平洋津波",
    8: "火山",
    9: "降灰",
    10: "気象",
    11: "洪水",
    12: "台風",
    14: "海上",
}

_QZQSM_URGENT_CATEGORIES = {
    "緊急地震速報",
    "津波",
    "北西太平洋津波",
    "火山",
    "洪水",
}

_QZQSM_SUMMARY_KEYS = (
    "震央地名",
    "地震発生時刻",
    "深さ",
    "マグニチュード",
    "震度(下限)",
    "震度(上限)",
    "長周期地震動階級(下限)",
    "長周期地震動階級(上限)",
    "津波到達予想時刻",
    "津波の高さ",
    "火山名",
    "現象",
    "警報等情報要素",
    "警報レベル",
    "台風番号",
    "中心気圧",
    "最大風速",
    "最大瞬間風速",
    "A4 - Hazard category and type",
    "A5 - Severity",
    "EX1 - Target area (ja)",
    "EX9 - Target area list (ja)",
)

_QZQSM_SKIP_SUMMARY_PREFIXES = (
    "防災気象情報(",
    "JMA-DC Report",
    "***",
    "### DCX Message",
)


def sfrbx_to_qzqsm(parsed):
    if parsed.gnssId != 5 or parsed.sigId != 1 or parsed.numWords < 9:
        return None

    data = bytearray()
    for i in range(9):
        word = getattr(parsed, f"dwrd_{i + 1:02d}", None)
        if word is None:
            return None
        data.extend(word.to_bytes(4, "big"))

    message_type = data[1] >> 2
    if message_type not in [43, 44]:
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
    return [
        ("CFG_SIGNAL_QZSS_L1S_ENA", output_enabled),
        (f"CFG_MSGOUT_UBX_RXM_SFRBX_{port}", output_enabled),
    ]


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

    parsed.update({"sentence": sentence, "satellite_id": fields[1], "message": message})
    parsed.update(decode_qzqsm_report(sentence))
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

    return {
        "report_text": str(report),
        "report_decoder": "azarashi",
    }


def build_qzss_dcr_event(dcr, event_id=None, received_at=None):
    message_type = dcr.get("message_type")
    category = dcr.get("disaster_category_str")
    classification = dcr.get("report_classification_str")
    report_text = dcr.get("report_text") or ""
    is_training = dcr.get("report_classification") == 7
    is_cancel = "取り消し" in report_text or "CANCELLATION" in report_text

    title = category or dcr.get("message_type_str", "QZSS DC Report")

    summary = _build_qzss_dcr_summary(dcr, report_text)
    priority = _qzss_dcr_priority(
        message_type=message_type,
        category=category,
        classification_no=dcr.get("report_classification"),
        report_text=report_text,
        is_training=is_training,
    )

    return {
        "id": event_id,
        "received_at": received_at,
        "title": title,
        "summary": summary,
        "body": report_text,
        "priority": priority,
        "category": category,
        "classification": classification,
        "message_type": message_type,
        "message_type_str": dcr.get("message_type_str"),
        "satellite_id": dcr.get("satellite_id"),
        "sentence": dcr.get("sentence"),
        "message": dcr.get("message"),
        "is_training": is_training,
        "is_cancel": is_cancel,
        "dedupe_key": dcr.get("sentence") or dcr.get("message"),
        "decoder_error": dcr.get("report_decoder_error"),
        "raw": dcr,
    }


def build_qzss_dcr_test_event(event_id):
    now = datetime.now()
    received_at = now.isoformat()
    report_time = now.strftime("%m月%d日%H時%M分")
    sentence = f"TEST-QZSS-DCR-{event_id:04d}"
    dcr = {
        "timestamp": received_at,
        "sentence": sentence,
        "satellite_id": "99",
        "message": sentence,
        "message_type": 43,
        "message_type_str": "災危通報（気象庁防災情報）",
        "report_classification": 1,
        "report_classification_str": "最優先",
        "disaster_category": 1,
        "disaster_category_str": "緊急地震速報",
        "version": 1,
        "report_text": (
            "防災気象情報(緊急地震速報)(発表)(最優先)\n"
            "緊急地震速報\n"
            "強い揺れに警戒してください。\n\n"
            f"発表時刻: {report_time}\n\n"
            "震央地名: テスト沖\n"
            "地震発生時刻: 5日12時33分\n"
            "深さ: 10km\n"
            "マグニチュード: 7.1\n"
            "震度(下限): 震度5弱\n"
            "震度(上限): 震度6弱\n"
            "東京都、神奈川県、千葉県"
        ),
        "report_decoder": "test",
    }
    return dcr, build_qzss_dcr_event(
        dcr,
        event_id=event_id,
        received_at=received_at,
    )


def _build_qzss_dcr_summary(dcr, report_text):
    if not report_text:
        error = dcr.get("report_decoder_error")
        if error:
            return f"Decode error: {error}"
        return dcr.get("message_type_str", "No decoded message")

    lines = [line.strip() for line in report_text.splitlines() if line.strip()]
    keyed_lines = [
        line
        for line in lines
        if any(line.startswith(f"{key}:") for key in _QZQSM_SUMMARY_KEYS)
    ]
    if keyed_lines:
        return "\n".join(keyed_lines[:3])

    content_lines = [
        line for line in lines if not line.startswith(_QZQSM_SKIP_SUMMARY_PREFIXES)
    ]
    if content_lines:
        return "\n".join(content_lines[:2])
    return lines[0] if lines else dcr.get("message_type_str", "QZSS DC Report")


def _qzss_dcr_priority(
    message_type,
    category,
    classification_no,
    report_text,
    is_training,
):
    if is_training:
        return "test"
    if classification_no == 1:
        return "urgent"
    if classification_no == 2:
        return "warning"
    if message_type == 44:
        text = report_text or ""
        if (
            "J-Alert" in text
            or "J Alert" in text
            or "Extreme" in text
            or "Severe" in text
        ):
            return "urgent"
        return "normal"
    if classification_no is None and category in _QZQSM_URGENT_CATEGORIES:
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
        "message_type_str": _QZQSM_MESSAGE_TYPE.get(message_type, "不明"),
    }
    if message_type == 43:
        report_classification = int(bits[14:17], 2)
        disaster_category = int(bits[17:21], 2)
        parsed.update(
            {
                "report_classification": report_classification,
                "report_classification_str": _QZQSM_REPORT_CLASSIFICATION.get(
                    report_classification,
                    "不明",
                ),
                "disaster_category": disaster_category,
                "disaster_category_str": _QZQSM_DISASTER_CATEGORY.get(
                    disaster_category,
                    "不明",
                ),
                "version": int(bits[21:27], 2),
            }
        )
    return parsed
