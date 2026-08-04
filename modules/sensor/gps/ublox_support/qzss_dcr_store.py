import hashlib
import json
from datetime import datetime

from .qzss_dcr import (
    Category,
    DCX_MESSAGE_TYPE,
    JMA_MESSAGE_TYPE,
    _as_list,
    _event_field_sets,
    _marine_event_is_cancel,
    _weather_region_pairs,
    build_qzss_dcr_event,
)
from .qzss_dcr_area import (
    DEFAULT_POPUP_MARGIN_KM,
    LOCATION_FAR,
    QzssDcrAreaResolver,
    distance_km,
    target_key,
)

DEFAULT_HISTORY_LIMIT = 100
DEFAULT_ACTIVE_GRACE_SECONDS = 5 * 60
DEFAULT_STALE_SECONDS = 30 * 60
DEFAULT_FRAGMENT_SETTLE_SECONDS = 3 * 60
DEFAULT_FAR_RECHECK_DISTANCE_KM = 5.0

_AREA_IDENTITIES = {
    Category.TSUNAMI: "tsunami_forecast_regions",
    Category.NW_PACIFIC_TSUNAMI: "coastal_regions",
    Category.FLOOD: "flood_forecast_regions",
    Category.MARINE: "marine_forecast_regions",
}
_EARTHQUAKE_IDENTITIES = {
    Category.EEW: None,
    Category.EPICENTER: "coordinates_of_hypocenter",
    Category.INTENSITY: None,
}
_POPUP_SUPPRESSED_CATEGORIES = {
    Category.EPICENTER,
    Category.INTENSITY,
}
_PRIORITY_RANK = {"normal": 0, "warning": 1, "urgent": 2}


def _is_marine_event(event):
    return (
        event.get("message_type") == JMA_MESSAGE_TYPE
        and event.get("category_no") == Category.MARINE
    )


def _field_values(fields, name):
    return _as_list(fields.get(f"{name}_raw")) or _as_list(fields.get(name))


def _optional_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _datetime(value=None):
    if isinstance(value, datetime):
        return value
    if value:
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            pass
    return datetime.now().astimezone()


def _key(*parts):
    return json.dumps(
        parts,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


class QzssDcrStore:
    def __init__(
        self,
        history_limit=DEFAULT_HISTORY_LIMIT,
        active_grace_seconds=DEFAULT_ACTIVE_GRACE_SECONDS,
        stale_seconds=DEFAULT_STALE_SECONDS,
        fragment_settle_seconds=DEFAULT_FRAGMENT_SETTLE_SECONDS,
        area_resolver=None,
    ):
        self.history_limit = int(history_limit)
        self.active_grace_seconds = float(active_grace_seconds)
        self.stale_seconds = float(stale_seconds)
        self.fragment_settle_seconds = float(fragment_settle_seconds)
        self.area_resolver = area_resolver
        self.active = {}
        self.history = []
        self._content_index = {}
        self._pending_popups = {}
        self._far_popup_judgments = {}
        self._next_id = 0
        self._last_any_seen_ts = None

    def ingest(self, dcr, received_at=None):
        fields = dcr.get("report_fields") or {}
        if fields.get("satellite_designation_mask_type") == "MT44 transmission status":
            return {"event": None, "is_new_content": False}

        received_at = _datetime(received_at or dcr.get("timestamp"))
        received_iso = received_at.isoformat()
        received_ts = received_at.timestamp()
        self._last_any_seen_ts = received_ts
        self.refresh(received_at)

        content_key = self._content_key(dcr)
        event = self._content_index.get(content_key)
        if event:
            self._observe(event, received_ts)
            if event["status"] == "stale":
                self._reopen(event, received_ts)
            return {"event": event, "is_new_content": False}

        fragment = build_qzss_dcr_event(dcr)
        bulletin_key = self._bulletin_key(dcr)
        series_keys = self._series_keys(dcr)
        event = self._find_event(
            bulletin_key,
            series_keys,
            include_history=fragment["is_cancel"],
        )
        identity = content_key, bulletin_key, series_keys
        reception = received_iso, received_ts
        if event:
            self._append(event, fragment, dcr, identity, reception)
        else:
            event = self._create(fragment, dcr, identity, reception)

        self._content_index[content_key] = event
        if event.get("is_cancel") and not _is_marine_event(event):
            self._finish(event, "cancelled", received_ts)
        return {"event": event, "is_new_content": True}

    @staticmethod
    def _match_event(events, bulletin_key, series_keys):
        if bulletin_key:
            matches = [
                event for event in events if bulletin_key in event["_bulletin_keys"]
            ]
            if len(matches) == 1:
                return matches[0]
        matches = [
            event for event in events if series_keys.intersection(event["_series_keys"])
        ]
        return matches[0] if len(matches) == 1 else None

    def _find_event(self, bulletin_key, series_keys, include_history=False):
        event = self._match_event(self.active.values(), bulletin_key, series_keys)
        if event is None and include_history:
            event = self._match_event(self.history, bulletin_key, series_keys)
        return event

    def _create(self, fragment, dcr, identity, reception):
        content_key, bulletin_key, series_keys = identity
        received_iso, received_ts = reception
        self._next_id += 1
        if self.area_resolver is None:
            self.area_resolver = QzssDcrAreaResolver()
        targets, unresolved = self.area_resolver.resolve_dcr(dcr)
        pages, total_pages = self._pages(dcr)
        event = {
            **fragment,
            "id": self._next_id,
            "status": self._status(pages, total_pages),
            "page_numbers": pages,
            "total_pages": total_pages,
            "fragments": [self._fragment(fragment, received_iso)],
            "location_targets": targets,
            "location_unresolved": unresolved,
            "popup_was_displayed": False,
            "_bulletin_keys": {bulletin_key} if bulletin_key else set(),
            "_series_keys": set(series_keys),
            "_content_keys": {content_key},
            "_last_seen_ts": received_ts,
            "_updated_ts": received_ts,
        }
        self._update_marine_cancellation(event)
        self.active[event["id"]] = event
        if self._popup_priority(fragment):
            self._pending_popups[event["id"]] = event
        return event

    def _append(self, event, fragment, dcr, identity, reception):
        content_key, bulletin_key, series_keys = identity
        received_iso, received_ts = reception
        previous_priority = event.get("priority", "normal")
        previous_issue = self._issue_signature(event)
        previous_action_rank = self._dcx_action_rank(event)
        self._observe(event, received_ts)

        event["_content_keys"].add(content_key)
        event["_series_keys"].update(series_keys)
        if bulletin_key:
            event["_bulletin_keys"].add(bulletin_key)
        event["fragments"].append(self._fragment(fragment, received_iso))

        pages, total_pages = self._pages(dcr)
        event["page_numbers"].update(pages)
        if total_pages is not None:
            event["total_pages"] = max(event.get("total_pages") or 0, total_pages)

        event.update(fragment)
        self._update_marine_cancellation(event)
        event["_updated_ts"] = received_ts
        event["status"] = self._status(
            event["page_numbers"],
            event["total_pages"],
        )

        targets, unresolved = self.area_resolver.resolve_dcr(dcr)
        known_targets = {target_key(target) for target in event["location_targets"]}
        event["location_targets"].extend(
            target for target in targets if target_key(target) not in known_targets
        )
        event["location_unresolved"] |= unresolved
        self._far_popup_judgments.pop(event["id"], None)

        priority_increased = _PRIORITY_RANK.get(event.get("priority"), 0) > (
            _PRIORITY_RANK.get(previous_priority, 0)
        )
        issue_changed = self._issue_signature(event) != previous_issue
        action_increased = self._dcx_action_rank(event) > previous_action_rank
        popup_changed = (
            priority_increased
            or issue_changed
            or action_increased
            or event.get("is_cancel")
        )
        if (
            event.get("message_type") == JMA_MESSAGE_TYPE
            and event.get("category_no") == Category.EEW
            and event["popup_was_displayed"]
        ):
            popup_changed = False
        if self._popup_priority(event) and popup_changed:
            self._pending_popups[event["id"]] = event

    @staticmethod
    def _fragment(fragment, received_at):
        return {
            "received_at": received_at,
            "report_fields": fragment.get("report_fields"),
            "is_cancel": fragment.get("is_cancel"),
        }

    @staticmethod
    def _update_marine_cancellation(event):
        if not _is_marine_event(event):
            return
        is_cancel = _marine_event_is_cancel(event)
        if is_cancel is not None:
            event["is_cancel"] = is_cancel

    def _observe(self, event, received_ts):
        event["_last_seen_ts"] = received_ts
        if event["status"] == "unknown":
            event["status"] = self._status(
                event["page_numbers"],
                event["total_pages"],
                received_ts - event["_updated_ts"],
            )

    def _reopen(self, event, received_ts):
        if event in self.history:
            self.history.remove(event)
        event["status"] = self._status(
            event["page_numbers"],
            event["total_pages"],
            received_ts - event["_updated_ts"],
        )
        event["_updated_ts"] = received_ts
        self.active[event["id"]] = event

    def _finish(self, event, status, finished_ts):
        self.active.pop(event["id"], None)
        event["status"] = status
        event["_updated_ts"] = finished_ts
        if event in self.history:
            self.history.remove(event)
        self.history.insert(0, event)
        self._far_popup_judgments.pop(event["id"], None)
        if status != "cancelled" or not event["popup_was_displayed"]:
            self._pending_popups.pop(event["id"], None)
        if len(self.history) > self.history_limit:
            removed = self.history.pop()
            self._pending_popups.pop(removed["id"], None)
            for key in removed["_content_keys"]:
                if self._content_index.get(key) is removed:
                    self._content_index.pop(key, None)

    def refresh(self, now=None):
        now_value = _datetime(now)
        now_ts = now_value.timestamp()
        for event in list(self.active.values()):
            age = now_ts - event["_last_seen_ts"]
            settled = now_ts - event["_updated_ts"] >= self.fragment_settle_seconds
            if settled and _is_marine_event(event) and event.get("is_cancel"):
                self._finish(event, "cancelled", now_ts)
                continue
            if event["status"] == "collecting" and settled:
                event["status"] = "active"
            if age < self.active_grace_seconds:
                continue
            if (
                age >= self.stale_seconds
                and self._last_any_seen_ts is not None
                and self._last_any_seen_ts - event["_last_seen_ts"]
                >= self.stale_seconds
            ):
                self._finish(event, "stale", now_ts)
            else:
                event["status"] = "unknown"

    def get_active_events(self, now=None):
        self.refresh(now)
        return sorted(
            self.active.values(),
            key=lambda event: (event["_updated_ts"], event["id"]),
            reverse=True,
        )

    def get_history(self, limit=None):
        return self.history if limit is None else self.history[: int(limit)]

    def get_pending_popup_events(self, now=None):
        if not self._pending_popups:
            return []
        self.refresh(now)
        if len(self._pending_popups) == 1:
            return list(self._pending_popups.values())
        return sorted(
            self._pending_popups.values(),
            key=lambda event: (event["_updated_ts"], event["id"]),
            reverse=True,
        )

    def mark_popup_handled(self, event, displayed=False):
        self._pending_popups.pop(event["id"], None)
        self._far_popup_judgments.pop(event["id"], None)
        event["popup_was_displayed"] |= displayed

    def location_status(
        self,
        event,
        latitude,
        longitude,
        margin_km=DEFAULT_POPUP_MARGIN_KM,
    ):
        return self.area_resolver.evaluate(
            event.get("location_targets") or [],
            bool(event.get("location_unresolved")),
            latitude,
            longitude,
            margin_km,
        )

    def popup_weather_pairs(self, event, latitude, longitude, margin_km):
        if event.get("category_no") != Category.WEATHER:
            return None

        nearby = set()
        found = False
        for fields in _event_field_sets(event):
            for _, code, region, region_code in _weather_region_pairs(fields):
                found = True
                targets, unresolved = self.area_resolver.resolve_area(
                    "weather",
                    region,
                    region_code,
                )
                if (
                    self.area_resolver.evaluate(
                        targets,
                        unresolved,
                        latitude,
                        longitude,
                        margin_km,
                    )
                    != LOCATION_FAR
                ):
                    nearby.add((code, str(region)))
        return nearby if found else None

    def popup_location_status(
        self,
        event,
        latitude,
        longitude,
        margin_km=DEFAULT_POPUP_MARGIN_KM,
    ):
        try:
            latitude = float(latitude)
            longitude = float(longitude)
            margin_km = float(margin_km)
        except (TypeError, ValueError):
            self._far_popup_judgments.pop(event["id"], None)
            return self.location_status(event, latitude, longitude, margin_km)

        judgment = self._far_popup_judgments.get(event["id"])
        if judgment is not None and margin_km == judgment[2]:
            try:
                moved_km = distance_km(
                    judgment[0],
                    judgment[1],
                    latitude,
                    longitude,
                )
            except ValueError:
                moved_km = DEFAULT_FAR_RECHECK_DISTANCE_KM
            if moved_km < DEFAULT_FAR_RECHECK_DISTANCE_KM:
                return LOCATION_FAR

        status = self.location_status(event, latitude, longitude, margin_km)
        if status == LOCATION_FAR:
            self._far_popup_judgments[event["id"]] = (
                latitude,
                longitude,
                margin_km,
            )
        else:
            self._far_popup_judgments.pop(event["id"], None)
        return status

    @staticmethod
    def _pages(dcr):
        fields = dcr.get("report_fields") or {}
        page = _optional_int(fields.get("page_number"))
        total = _optional_int(fields.get("total_page"))
        return ({page} if page is not None else set()), total

    def _status(self, pages, total, age=0):
        if total and len(pages) >= total:
            return "active"
        if total:
            return "assembling"
        return "active" if age >= self.fragment_settle_seconds else "collecting"

    @staticmethod
    def _popup_priority(event):
        if (
            event.get("message_type") == JMA_MESSAGE_TYPE
            and event.get("category_no") in _POPUP_SUPPRESSED_CATEGORIES
        ):
            return False
        return event.get("priority") in {"urgent", "warning"}

    @staticmethod
    def _issue_signature(event):
        fields = event.get("report_fields") or {}
        if event.get("message_type") == DCX_MESSAGE_TYPE:
            return None
        return (
            event.get("message_type"),
            fields.get("report_time"),
            fields.get("information_type_no"),
        )

    @staticmethod
    def _dcx_action_rank(event):
        if event.get("message_type") != DCX_MESSAGE_TYPE:
            return 0
        fields = event.get("report_fields") or {}
        guidance = " ".join(
            str(fields.get(name) or "")
            for name in (
                "a11_japanese_library_ja",
                "a11_japanese_library",
                "a11_international_library",
            )
        ).casefold()
        if (
            "避難の呼びかけを解除" in guidance
            or "evacuation will be cancel" in guidance
        ):
            return 0
        japanese_shelter = "避難" in guidance
        english_shelter = "shelter" in guidance or "evacuat" in guidance
        if ("直ちに" in guidance and japanese_shelter) or (
            "immediately" in guidance and english_shelter
        ):
            return 2
        return 1 if japanese_shelter or english_shelter else 0

    @staticmethod
    def _content_key(dcr):
        canonical = dcr.get("canonical_payload")
        if canonical:
            return f"raw:{str(canonical).upper()}"
        message = dcr.get("message") or dcr.get("sentence")
        if message:
            return f"message:{message}"
        payload = (
            dcr.get("message_type"),
            dcr.get("report_classification"),
            dcr.get("disaster_category"),
            dcr.get("message"),
            dcr.get("report_fields") or {},
            dcr.get("report_text"),
        )
        digest = hashlib.sha256(_key(*payload).encode()).hexdigest()
        return f"sha256:{digest}"

    @staticmethod
    def _bulletin_key(dcr):
        if dcr.get("message_type") == DCX_MESSAGE_TYPE:
            return None
        fields = dcr.get("report_fields") or {}
        report_time = fields.get("report_time")
        if report_time is None:
            return None
        return (
            "bulletin",
            dcr.get("report_classification"),
            dcr.get("disaster_category"),
            report_time,
            fields.get("information_type_no"),
        )

    @classmethod
    def _series_keys(cls, dcr):
        if dcr.get("message_type") == DCX_MESSAGE_TYPE:
            return {_key("dcx", cls._dcx_identity(dcr))}
        if dcr.get("is_test"):
            message_mode = "display_test"
        else:
            message_mode = (
                "test" if dcr.get("report_classification") == 7 else "operational"
            )
        prefix = (
            "series",
            dcr.get("message_type"),
            message_mode,
            dcr.get("disaster_category"),
        )
        return {_key(*prefix, identity) for identity in cls._series_identities(dcr)}

    @classmethod
    def _series_identities(cls, dcr):
        fields = dcr.get("report_fields") or {}
        category = dcr.get("disaster_category")
        if category in _EARTHQUAKE_IDENTITIES:
            field = _EARTHQUAKE_IDENTITIES[category]
            occurrence = fields.get("occurrence_time_of_earthquake") or fields.get(
                "report_time"
            )
            return [(occurrence, fields.get(field) if field else None)]
        if category == Category.NANKAI:
            return [("runtime_episode",)]
        if category in _AREA_IDENTITIES:
            label_field = _AREA_IDENTITIES[category]
            values = _field_values(fields, label_field)
            return [("area", value) for value in values if value is not None]
        if category in {Category.VOLCANO, Category.ASH_FALL}:
            volcano = fields.get("volcano_name_raw") or fields.get("volcano_name")
            return [("volcano", volcano)] if volcano is not None else []
        if category == Category.WEATHER:
            return cls._weather_identities(fields)
        if category == Category.TYPHOON:
            typhoon = fields.get("typhoon_number_raw") or fields.get("typhoon_number")
            return [("typhoon", typhoon)] if typhoon is not None else []
        return []

    @staticmethod
    def _weather_identities(fields):
        return [
            ("weather", subcategory, region)
            for _, subcategory, _, region in _weather_region_pairs(fields)
            if subcategory is not None and region is not None
        ]

    @staticmethod
    def _dcx_identity(dcr):
        fields = dcr.get("report_fields") or {}
        message_mode = (
            "test"
            if (fields.get("a1_message_type") or fields.get("dcx_message_type"))
            == "Test"
            else "operational"
        )
        target = (
            fields.get("ex1_target_area_ja")
            or fields.get("ex9_target_area_list_ja")
            or (
                fields.get("a12_ellipse_centre_latitude"),
                fields.get("a13_ellipse_centre_longitude"),
                fields.get("a14_ellipse_semi_major_axis"),
            )
        )
        identity = (
            DCX_MESSAGE_TYPE,
            message_mode,
            fields.get("a2_country_region_name"),
            fields.get("a3_provider_identifier"),
            fields.get("a4_hazard_type_raw") or fields.get("a4_hazard_type"),
            fields.get("a6a7_hazard_onset_datetime"),
            target,
        )
        return identity + ((dcr.get("message"),) if not any(identity[1:]) else ())
