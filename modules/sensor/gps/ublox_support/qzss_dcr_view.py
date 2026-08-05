import html
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .qzss_dcr import (
    Category,
    DCX_MESSAGE_TYPE,
    JMA_MESSAGE_TYPE,
    _as_list,
    _event_field_sets,
    _marine_warning_states,
    _weather_region_pairs,
)
from .qzss_dcr_area import coordinate

VOLCANO_ERUPTION_CODE = 52
JST = timezone(timedelta(hours=9))

WEATHER_PRIORITY = {2: 0, 23: 1}
KANTO_ORDER = (
    "東京都",
    "神奈川県",
    "埼玉県",
    "千葉県",
    "茨城県",
    "栃木県",
    "群馬県",
)
EEW_BROAD_REGIONS = {
    66: "中国",
    67: "四国",
    68: "九州",
}
TSUNAMI_SHORT_NAMES = {
    600: "宇和海",
    751: "豊後水道",
}
_CATEGORY_TITLES_JA = {
    Category.EEW: "緊急地震速報",
    Category.EPICENTER: "震源情報",
    Category.INTENSITY: "震度情報",
    Category.NANKAI: "南海トラフ地震",
    Category.TSUNAMI: "津波情報",
    Category.NW_PACIFIC_TSUNAMI: "北西太平洋津波情報",
    Category.VOLCANO: "火山情報",
    Category.ASH_FALL: "降灰情報",
    Category.WEATHER: "気象情報",
    Category.FLOOD: "洪水情報",
    Category.TYPHOON: "台風情報",
    Category.MARINE: "海上警報",
}
_LIST_TITLE_FIELDS_JA = {
    Category.EEW: (
        "緊急地震速報",
        ("seismic_epicenter", "seismic_intensity_lower_limit"),
    ),
    Category.EPICENTER: ("", ("seismic_epicenter", "magnitude")),
    Category.INTENSITY: ("震度情報", ("seismic_intensities",)),
    Category.NANKAI: ("南海トラフ", ("information_serial_code",)),
    Category.VOLCANO: ("", ("volcano_name", "volcanic_warning_code")),
    Category.FLOOD: ("", ("flood_forecast_regions", "flood_warning_levels")),
}
_EVENT_AREA_FIELDS = {
    JMA_MESSAGE_TYPE: (
        "eew_forecast_regions",
        "prefectures",
        "tsunami_forecast_regions",
        "local_governments",
        "weather_forecast_regions",
        "flood_forecast_regions",
        "marine_forecast_regions",
    ),
    DCX_MESSAGE_TYPE: ("ex1_target_area_ja", "ex9_target_area_list_ja"),
}
Block = tuple[str, str]

_DETAIL_STYLE = """
<style>
  body { color: #111111; font-size: 16px; }
  .time { color: #555555; font-size: 16px; font-weight: 600; margin-bottom: 12px; }
  .lead { font-size: 23px; font-weight: 700; margin-bottom: 2px; }
  .area { font-size: 18px; margin-bottom: 10px; }
  .action { font-size: 20px; font-weight: 700; margin-bottom: 14px; }
  .section { font-size: 17px; font-weight: 600; margin: 3px 0; }
  .heading { font-size: 16px; font-weight: 700; margin-top: 14px; }
  .forecast { font-size: 16px; font-weight: 700; margin: 3px 0; }
  .text { font-size: 16px; font-weight: 600; margin: 7px 0; }
  .regions { font-size: 15px; font-weight: 600; }
  .source, .received { color: #555555; font-size: 14px; font-weight: 600; margin-top: 14px; }
</style>
"""


@dataclass(frozen=True)
class ListView:
    title: str
    detail: str


@dataclass(frozen=True)
class PopupView:
    title: str
    lines: tuple[str, ...]


@dataclass(frozen=True)
class DetailView:
    title: str
    timestamp: str
    blocks: tuple[Block, ...]
    source: str
    received_at: str


def _unique(values):
    return list(dict.fromkeys(str(value) for value in values if value))


def _first(value, default=""):
    values = _unique(_as_list(value))
    return values[0] if values else default


def _blocks(*values):
    return tuple((kind, str(value)) for kind, value in values if value)


def _metric(fields, name, label, prefix=""):
    value = fields.get(name)
    return "section", f"{label}：{prefix}{value}" if value else ""


def _fragments(event):
    return (
        fragment
        for fragment in event.get("fragments", [])
        if fragment.get("report_fields")
    )


def _display_fields(event):
    ignore_cancel = event.get("is_cancel")
    fields = next(
        (
            fragment["report_fields"]
            for fragment in reversed(event.get("fragments") or ())
            if fragment.get("report_fields")
            and not (ignore_cancel and fragment.get("is_cancel"))
        ),
        None,
    )
    return fields or event.get("report_fields") or {}


def _received_time(event):
    fragments = event.get("fragments") or ()
    value = fragments[-1].get("received_at") if fragments else event.get("timestamp")
    if not value:
        return ""
    return f"受信：{_clock(value, with_date=True, with_seconds=True)}"


def _clock(value, with_date=False, compact=False, with_seconds=False):
    if not value:
        return "-"
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return str(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    parsed = parsed.astimezone(JST if with_date or compact else None)
    time_format = "%H:%M:%S" if with_seconds else "%H:%M"
    if compact:
        return f"{parsed.month}/{parsed.day} {parsed.strftime(time_format)}"
    if with_date:
        return f"{parsed.month}月{parsed.day}日 {parsed.strftime(time_format)}"
    return parsed.strftime(time_format)


def _official_time(event, fields):
    field_sets = [fields]
    field_sets.extend(fragment["report_fields"] for fragment in _fragments(event))
    report_times = [item.get("report_time") for item in field_sets]
    report_times = [str(value) for value in report_times if value]
    if report_times:
        return f"発表：{_clock(max(report_times), with_date=True)}"
    onset = fields.get("a6a7_hazard_onset_datetime")
    return f"発生：{_clock(onset, with_date=True)}" if onset else ""


def _weather_groups(event, included_pairs=None):
    groups = {}
    for fields in _event_field_sets(event):
        for label, code, region, _ in _weather_region_pairs(fields):
            if included_pairs is not None and (code, str(region)) not in included_pairs:
                continue
            group = groups.setdefault(
                code,
                {"code": code, "label": str(label), "regions": []},
            )
            group["regions"].append(str(region))
    for group in groups.values():
        group["regions"] = _unique(group["regions"])
    return list(groups.values())


def _primary_weather(event, included_pairs=None):
    groups = _weather_groups(event, included_pairs)
    if not groups:
        return None, []
    primary = min(
        groups,
        key=lambda group: WEATHER_PRIORITY.get(group["code"], 100),
    )
    return primary, [group for group in groups if group is not primary]


def _format_lines(values, first_line=4):
    values = _unique(values)
    if not values:
        return []
    lines = ["・".join(values[:first_line])]
    if values[first_line:]:
        lines.append("・".join(values[first_line:]))
    return lines


def _compact_prefecture(value):
    value = str(value)
    if value == "北海道":
        return value
    return value[:-1] if value.endswith(("都", "府", "県")) else value


def _eew_area(fields, popup=False):
    labels = _as_list(fields.get("eew_forecast_regions"))
    codes = _as_list(fields.get("eew_forecast_regions_raw"))
    by_code = dict(zip(codes, labels))
    order = (68, 67, 66) if popup else (66, 67, 68)
    broad = [str(by_code[code]) for code in order if code in by_code]
    if broad:
        return "・".join(broad) + "地方"
    return "・".join(_compact_prefecture(value) for value in labels[:4])


def _tsunami_areas(fields, compact=False):
    labels = _as_list(fields.get("tsunami_forecast_regions"))
    if not compact:
        return [str(value) for value in labels]
    codes = _as_list(fields.get("tsunami_forecast_regions_raw"))
    values = []
    for index, label in enumerate(labels):
        code = codes[index] if index < len(codes) else None
        values.append(
            TSUNAMI_SHORT_NAMES.get(
                code,
                _compact_prefecture(str(label).removesuffix("沿岸")),
            )
        )
    return values


def _flood_parts(fields):
    value = _first(fields.get("flood_forecast_regions"))
    match = re.match(r"(.+?)[(（](.+?)[)）]$", value)
    return match.groups() if match else (value, "")


def _flood_regions(fields):
    return _unique(
        str(value) for value in _as_list(fields.get("flood_forecast_regions"))
    )


def _marine_warnings(event):
    return [(region, warning) for region, warning, _ in _marine_warning_states(event)]


def _marine_list_title(event, fields, show_state):
    warnings = _unique(
        warning
        for _, warning, raw_code in _marine_warning_states(event)
        if str(raw_code) != "0"
    )
    title = _format_values(warnings) or _CATEGORY_TITLES_JA[Category.MARINE]
    state = fields.get("information_type") if not event.get("is_cancel") else None
    return f"{title}（{state}）" if state and show_state else title


def _detail_marine(event):
    groups = {}
    for region, warning in _marine_warnings(event):
        groups.setdefault(warning or "対象海域", []).append(region)
    values = []
    for warning, regions in groups.items():
        values.append(("heading", warning))
        values.extend(("section", region) for region in _unique(regions))
    return _blocks(*values)


def _guidance(fields):
    return [
        str(value)
        for value in _as_list(fields.get("notifications_on_disaster_prevention"))
    ]


def _assembled_text(event):
    pages = {}
    for fragment in _fragments(event):
        fields = fragment["report_fields"]
        page = fields.get("page_number")
        text = fields.get("text_information")
        if page is None or not text:
            continue
        try:
            pages[int(page)] = bytes.fromhex(str(text))
        except (TypeError, ValueError):
            continue
    try:
        return b"".join(pages[key] for key in sorted(pages)).rstrip(b"\0").decode()
    except UnicodeDecodeError:
        return ""


def _ash_values(event):
    phenomena, areas = [], []
    for fragment in _fragments(event):
        fields = fragment["report_fields"]
        phenomena.extend(_as_list(fields.get("ash_fall_warning_codes")))
        areas.extend(_as_list(fields.get("local_governments")))
    return _unique(phenomena), _unique(areas)


def _format_values(values, limit=2):
    values = _unique(_as_list(values))
    text = "、".join(values[:limit])
    if len(values) > limit:
        text += f"、ほか{len(values) - limit}件"
    return text


def _typhoon_title(fields):
    number = fields.get("typhoon_number")
    if not number:
        return ""
    number = str(number)
    return number if number.startswith("台風") else f"台風{number}"


def _list_title(category, fields, show_state=True):
    default = _CATEGORY_TITLES_JA.get(category)
    if category == Category.ASH_FALL:
        return "・".join(
            _unique(
                (
                    fields.get("volcano_name"),
                    fields.get("ash_fall_warning_type") or default,
                )
            )
        )
    if category == Category.WEATHER:
        title = _format_values(fields.get("weather_related_disaster_sub_categories"))
        state = fields.get("weather_warning_state") or fields.get("information_type")
        return (
            f"{title}（{state}）"
            if title and state and show_state
            else title or default
        )
    if category == Category.TYPHOON:
        return _typhoon_title(fields) or default
    if category == Category.MARINE:
        title = _format_values(fields.get("marine_warning_codes")) or default
        state = fields.get("information_type")
        return f"{title}（{state}）" if state and show_state else title

    prefix, field_names = _LIST_TITLE_FIELDS_JA.get(category, ("", ()))
    values = _unique(_first(fields.get(name)) for name in field_names)
    return "・".join(([prefix] if prefix else []) + values) if values else default


def _report_title(event, fields, category, popup, weather):
    default = _CATEGORY_TITLES_JA.get(category)
    if category == Category.TSUNAMI:
        if popup and event.get("is_cancel"):
            return "津波警報解除"
        return str(fields.get("tsunami_warning_code") or default)
    if category == Category.VOLCANO:
        return (
            "火山噴火"
            if fields.get("volcanic_warning_code_raw") == VOLCANO_ERUPTION_CODE
            else fields.get("volcanic_warning_code") or default
        )
    if category == Category.WEATHER:
        primary, _ = weather
        return primary["label"] if primary else default
    if category == Category.FLOOD:
        if popup and event.get("is_cancel"):
            return "洪水警報解除"
        return _first(fields.get("flood_warning_levels"), default)
    if category == Category.TYPHOON:
        return _typhoon_title(fields) or default
    if category == Category.MARINE:
        return "海上警報解除" if event.get("is_cancel") else default
    return default


def _title(event, fields, surface="detail", history=False, weather=None):
    list_view = surface == "list"
    popup = surface == "popup"
    message_type = event.get("message_type")
    if message_type == JMA_MESSAGE_TYPE:
        category = event.get("category_no")
        title = (
            _marine_list_title(event, fields, show_state=not history)
            if list_view and category == Category.MARINE
            else (
                _list_title(category, fields, show_state=not history)
                if list_view
                else _report_title(event, fields, category, popup, weather)
            )
        )
    elif message_type == DCX_MESSAGE_TYPE:
        hazard = fields.get("a4_hazard_type")
        title = str(hazard) if hazard else ""
    else:
        title = ""
    title = title or "QZSS DC Report"

    if surface in {"list", "popup"} and event.get("is_test"):
        return f"[test] {title}"
    if surface in {"list", "popup"} and event.get("is_training"):
        if list_view and event.get("is_cancel") and not history:
            return f"[訓練・解除] {title}"
        return f"[訓練] {title}"
    if list_view and event.get("is_cancel") and not history:
        return f"[解除] {title}"
    return title


def _decoded_lines(event):
    report_text = event.get("body") or ""
    if not report_text:
        error = event.get("report_decoder_error")
        return [f"Decode error: {error}"] if error else []
    return [
        line.strip()
        for line in report_text.splitlines()
        if line.strip()
        and not line.startswith(("防災気象情報(", "JMA-DC Report", "***", "### DCX"))
    ]


def build_popup_view(event, weather_pairs=None):
    fields = event.get("report_fields") or {}
    message_type = event.get("message_type")
    weather = None
    lines = []
    if message_type == JMA_MESSAGE_TYPE:
        category = event.get("category_no")
        weather = (
            _primary_weather(event, weather_pairs)
            if category == Category.WEATHER
            else None
        )
        if category == Category.EEW:
            lines.append(_eew_area(fields, popup=True))
            intensity = fields.get("seismic_intensity_lower_limit")
            if intensity:
                lines.append(f"{intensity}以上")
            lines.append("強い揺れに警戒")
        elif category == Category.NANKAI:
            lines.extend(
                (
                    fields.get("information_serial_code"),
                    "大規模地震の可能性が",
                    "平常時より高まっています",
                )
            )
        elif category == Category.TSUNAMI:
            lines.extend(_format_lines(_tsunami_areas(fields, compact=True), 4))
            if event.get("is_cancel"):
                guidance = _guidance(fields)
                if guidance:
                    lines.append(guidance[0].splitlines()[-1].rstrip("。"))
            else:
                height = _first(fields.get("tsunami_heights"))
                if height:
                    lines.append(f"予想{height}")
                lines.append("ただちに高台へ避難")
        elif category == Category.VOLCANO:
            lines.append(fields.get("volcano_name"))
            areas = [
                re.sub(r"^.+?[都道府県]", "", str(value))
                for value in _as_list(fields.get("local_governments"))
            ]
            lines.extend(_format_lines(areas, 2))
        elif category == Category.WEATHER:
            primary, _ = weather
            if primary:
                lines.extend(
                    _format_lines(
                        [_compact_prefecture(value) for value in primary["regions"]],
                        4,
                    )
                )
        elif category == Category.FLOOD:
            lines.extend(value for value in _flood_parts(fields) if value)
        else:
            lines.extend(_decoded_lines(event)[:3])
    elif message_type == DCX_MESSAGE_TYPE:
        areas = fields.get("ex1_target_area_ja") or fields.get(
            "ex9_target_area_list_ja"
        )
        lines.extend(
            (
                _format_values(areas),
                fields.get("a5_severity"),
                fields.get("a11_japanese_library_ja")
                or fields.get("a11_international_library"),
            )
        )
    else:
        lines.extend(_decoded_lines(event)[:3])
    if not any(lines):
        lines.append("New disaster report received.")
    title = _title(event, fields, surface="popup", weather=weather)
    return PopupView(title, tuple(_unique(lines)))


def _detail_eew(fields):
    values = [
        (
            "lead",
            (
                f"{fields['seismic_intensity_lower_limit']}以上"
                if fields.get("seismic_intensity_lower_limit")
                else ""
            ),
        ),
        ("area", _eew_area(fields)),
        ("action", _first(_guidance(fields), "強い揺れに警戒してください。")),
        ("rule", True),
        _metric(fields, "seismic_epicenter", "震源"),
        _metric(fields, "magnitude", "規模", "M"),
        _metric(fields, "depth_of_hypocenter", "深さ"),
    ]
    long_period = fields.get("long_period_ground_motion_lower_limit")
    if long_period:
        values.append(
            (
                "section",
                "長周期地震動：" + str(long_period).replace("長周期地震動階級", "階級"),
            )
        )
    codes = _as_list(fields.get("eew_forecast_regions_raw"))
    labels = _as_list(fields.get("eew_forecast_regions"))
    regions = [
        label
        for index, label in enumerate(labels)
        if index >= len(codes) or codes[index] not in EEW_BROAD_REGIONS
    ]
    if regions:
        values.extend((("heading", "対象地域"), ("regions", "、".join(regions))))
    return _blocks(*values)


def _detail_tsunami(fields):
    heights = _as_list(fields.get("tsunami_heights"))
    areas = _tsunami_areas(fields)
    arrivals = _as_list(fields.get("expected_tsunami_arrival_times"))
    guidance = _first(_guidance(fields))
    guidance_lines = [line for line in guidance.splitlines() if line]
    action = guidance_lines[2] if len(guidance_lines) >= 3 else ""
    caution = "".join(guidance_lines[3:])
    values = [
        ("lead", f"予想{_first(heights)}" if heights else ""),
        ("area", "・".join(_tsunami_areas(fields, compact=True))),
        ("action", action),
        ("rule", True),
        ("heading", "対象地域・到達予想"),
    ]
    for index, area in enumerate(areas):
        arrival = _clock(arrivals[index]) if index < len(arrivals) else "-"
        height = heights[index] if index < len(heights) else "-"
        values.append(("section", f"{area}　{arrival} / {height}"))
    if caution:
        values.extend((("heading", "注意"), ("text", caution)))
    return _blocks(*values)


def _detail_weather(weather):
    primary, others = weather
    if not primary:
        return ()
    regions = primary["regions"]
    if set(regions) == set(KANTO_ORDER):
        regions = list(KANTO_ORDER)
        lead = "関東7都県"
    elif len(regions) == 1:
        lead = regions[0]
        regions = []
    else:
        lead = f"{len(regions)}地域"
    values = [("lead", lead)]
    values.extend(
        ("area", line)
        for line in _format_lines([_compact_prefecture(value) for value in regions], 4)
    )
    if others:
        values.extend((("rule", True), ("heading", "併せて発表")))
        for group in others:
            values.append(("section", group["label"]))
            area_text = (
                f"同じ{len(primary['regions'])}都県"
                if set(group["regions"]) == set(primary["regions"])
                else "、".join(group["regions"])
            )
            values.append(("regions", area_text))
    return _blocks(*values)


def _compact_angle(value, positive, negative):
    degree, seconds = divmod(round(abs(value) * 3600), 3600)
    minute, seconds = divmod(seconds, 60)
    suffix = f"{seconds}″" if seconds else ""
    return f"{positive if value >= 0 else negative}{degree}°{minute}′{suffix}"


def _known_typhoon_value(value):
    return value if str(value or "").strip() not in {"", "なし", "不明"} else None


def _detail_typhoon(event):
    fragments = _event_field_sets(event)
    latest = max(str(item.get("report_time") or "") for item in fragments)
    forecasts = {
        item.get("reference_time") or f"#{index}": item
        for index, item in enumerate(fragments)
        if not latest or str(item.get("report_time")) == latest
    }
    forecasts = sorted(
        forecasts.values(), key=lambda item: item.get("reference_time") or ""
    )
    values = []
    for forecast in forecasts:
        heading = _clock(forecast.get("reference_time"), compact=True)
        reference_type = forecast.get("reference_time_type")
        if reference_type:
            heading += f"　{reference_type}"
        point = coordinate(forecast.get("coordinates_of_typhoon"))
        position = (
            f"{_compact_angle(point[0], '北緯', '南緯')}　"
            f"{_compact_angle(point[1], '東経', '西経')}"
            if point
            else ""
        )
        scale = _known_typhoon_value(forecast.get("typhoon_scale_category"))
        intensity = _known_typhoon_value(forecast.get("typhoon_intensity_category"))
        pressure = _known_typhoon_value(forecast.get("central_pressure"))
        wind = _known_typhoon_value(forecast.get("maximum_wind_speed"))
        gust = _known_typhoon_value(forecast.get("maximum_gust_wind_speed"))
        values.extend(
            (
                ("rule", True),
                ("forecast", heading),
                ("section", scale),
                ("section", intensity),
                ("regions", position),
                ("section", f"中心気圧 {pressure}" if pressure else ""),
                ("section", f"最大風速 {wind}" if wind else ""),
                ("section", f"瞬間最大風速{gust}" if gust else ""),
            )
        )
    return _blocks(*values)


def _detail_body(event, fields, weather=None):
    message_type = event.get("message_type")
    if message_type == JMA_MESSAGE_TYPE:
        category = event.get("category_no")
    elif message_type == DCX_MESSAGE_TYPE:
        return _blocks(
            ("lead", fields.get("a4_hazard_type")),
            ("section", fields.get("a5_severity")),
            (
                "area",
                fields.get("ex1_target_area_ja")
                or fields.get("ex9_target_area_list_ja"),
            ),
            (
                "action",
                fields.get("a11_japanese_library_ja")
                or fields.get("a11_international_library"),
            ),
        )
    else:
        return _blocks(
            ("text", "\n".join(_decoded_lines(event)) or "No decoded message.")
        )
    if category == Category.EEW:
        return _detail_eew(fields)
    if category == Category.EPICENTER:
        return _blocks(
            ("lead", fields.get("seismic_epicenter")),
            _metric(fields, "magnitude", "規模", "M"),
            _metric(fields, "depth_of_hypocenter", "深さ"),
        )
    if category == Category.INTENSITY:
        return _blocks(
            ("lead", _first(fields.get("seismic_intensities"))),
            ("regions", "、".join(_unique(fields.get("prefectures", [])))),
        )
    if category == Category.NANKAI:
        paragraphs = [
            value for value in re.split(r"(?<=。)", _assembled_text(event)) if value
        ]
        values = [("lead", fields.get("information_serial_code"))]
        values.extend(
            ("action" if index == len(paragraphs) - 1 else "text", paragraph)
            for index, paragraph in enumerate(paragraphs)
        )
        return _blocks(*values)
    if category == Category.TSUNAMI:
        return _detail_tsunami(fields)
    if category == Category.VOLCANO:
        areas = _unique(fields.get("local_governments", []))
        values = [("lead", fields.get("volcano_name"))]
        if areas:
            values.extend((("rule", True), ("heading", "対象地域")))
            values.extend(("section", value) for value in areas)
        return _blocks(*values)
    if category == Category.ASH_FALL:
        phenomena, areas = _ash_values(event)
        return _blocks(
            ("lead", fields.get("volcano_name")),
            ("heading", "現象" if phenomena else ""),
            ("regions", "、".join(phenomena)),
            ("heading", "対象地域" if areas else ""),
            ("regions", "、".join(areas)),
        )
    if category == Category.WEATHER:
        return _detail_weather(weather)
    if category == Category.FLOOD:
        return _blocks(*(("section", value) for value in _flood_regions(fields)))
    if category == Category.TYPHOON:
        return _detail_typhoon(event)
    if category == Category.MARINE:
        return _detail_marine(event)
    return _blocks(("text", "\n".join(_decoded_lines(event)) or "No decoded message."))


def build_detail_view(event):
    fields = _display_fields(event)
    message_type = event.get("message_type")
    weather = (
        _primary_weather(event)
        if message_type == JMA_MESSAGE_TYPE
        and event.get("category_no") == Category.WEATHER
        else None
    )
    provider = (
        "気象庁"
        if message_type == JMA_MESSAGE_TYPE
        else fields.get("a3_provider_identifier") or "他機関"
    )
    return DetailView(
        title=_title(event, fields, weather=weather),
        timestamp=_official_time(event, fields),
        blocks=_detail_body(event, fields, weather),
        source=f"発信：{provider}",
        received_at=_received_time(event),
    )


def build_list_view(event, history=False):
    fields = _display_fields(event)
    area_fields = _EVENT_AREA_FIELDS.get(
        event.get("message_type"), sum(_EVENT_AREA_FIELDS.values(), ())
    )
    if (
        event.get("message_type") == JMA_MESSAGE_TYPE
        and event.get("category_no") == Category.MARINE
    ):
        areas = [region for region, _ in _marine_warnings(event)]
    else:
        areas = next(
            (fields.get(name) for name in area_fields if fields.get(name)),
            None,
        )
    return ListView(
        title=_title(event, fields, surface="list", history=history),
        detail=_format_values(areas) if areas else "",
    )


def _div(class_name, value):
    escaped = html.escape(str(value or "")).replace("\n", "<br>")
    return f'<div class="{class_name}">{escaped}</div>' if escaped else ""


def format_qzss_dcr_detail(event):
    view = build_detail_view(event)
    parts = [_DETAIL_STYLE, _div("time", view.timestamp)]
    for kind, value in view.blocks:
        parts.append("<hr>" if kind == "rule" else _div(kind, value))
    parts.append(_div("source", view.source))
    parts.append(_div("received", view.received_at))
    return view.title, "".join(parts)
