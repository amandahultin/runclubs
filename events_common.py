"""Shared utilities for all generate_*_events.py scripts.

Any fix to fetch logic, date/time parsing, or sheet constants goes here once
and automatically applies to all four generators.
"""

from __future__ import annotations

import html as _html_lib
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import gspread
from google.oauth2.service_account import Credentials

log = logging.getLogger(__name__)

# ── Sheet config ─────────────────────────────────────────────────────────────

EVENTS_SHEET_ID     = "1DjQO84D3ihq-1VMOYZI6Q7WqC3mAdL-l0fRhZrwOFG4"
WORKSHEET_NAME      = "Events"
WEEKLY_WORKSHEET    = "WeeklyRuns"
OVERRIDES_WORKSHEET = "Overrides"
SPECIAL_WORKSHEET   = "SpecialEvents"
LOOKAHEAD_DAYS      = 30

HEADERS = [
    "source", "club", "title", "date", "location",
    "description", "link", "image_url", "engagement", "fetched_at",
]
WEEKLY_HEADERS    = ["club", "day_of_week", "time", "location", "city", "title", "description", "link"]
OVERRIDES_HEADERS = ["club", "date", "city", "action", "time", "location", "title", "description", "link"]
SPECIAL_HEADERS   = ["club", "title", "date", "time", "location", "city", "description", "link", "image_url"]

CLUB_NAME_ALIASES = {
    "dc runclub":              "Saucony Run Club Sverige",
    "downtown camper run club": "Saucony Run Club Sverige",
    "saucony run club":        "Saucony Run Club Sverige",
    "slowrunners göteborg":    "Pace & People",
}

def normalize_club_name(name: str) -> str:
    return CLUB_NAME_ALIASES.get(name.strip().lower(), name.strip())


def _normalize_city(text: str) -> str:
    t = text.lower()
    if "stockholm" in t:
        return "Stockholm"
    if any(k in t for k in ("göteborg", "goteborg", "gothenburg", "västra götaland")):
        return "Göteborg"
    if any(k in t for k in (
        "malmö", "malmo", "malmoe", "skåne",
        "varberg", "halmstad", "falkenberg",
        "uppsala", "gavle", "gävle", "linkoping", "linköping",
        "norrkoping", "norrköping",
    )):
        return "Övriga landet"
    return ""


def build_club_cities(weekly_records: list[dict]) -> dict[str, str]:
    """Return {club_name_lower: canonical_city} derived from the WeeklyRuns sheet.

    Used as a fallback when a Strava event's location field doesn't contain a
    recognisable city keyword.
    """
    mapping: dict[str, str] = {}
    for r in weekly_records:
        club = normalize_club_name(r.get("club") or "").strip()
        if not club:
            continue
        city_raw = (r.get("city") or "").strip()
        city = _normalize_city(city_raw)
        if city:
            mapping[club.lower()] = city
    return mapping

DAYS_MAP = {
    "monday": 0,    "måndag": 0,
    "tuesday": 1,   "tisdag": 1,
    "wednesday": 2, "onsdag": 2,
    "thursday": 3,  "torsdag": 3,
    "friday": 4,    "fredag": 4,
    "saturday": 5,  "lördag": 5,
    "sunday": 6,    "söndag": 6,
}

STOCKHOLM = ZoneInfo("Europe/Stockholm")

# ── Google Sheets client ──────────────────────────────────────────────────────

def _sheet_client() -> gspread.Client:
    raw = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    creds = Credentials.from_service_account_info(
        json.loads(raw),
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    return gspread.authorize(creds)


_RETRY_STATUSES = {429, 500, 502, 503, 504}


def _with_retry(fn, *, attempts: int = 4, base_delay: float = 2.0):
    for i in range(attempts):
        try:
            return fn()
        except gspread.exceptions.APIError as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status not in _RETRY_STATUSES or i == attempts - 1:
                raise
            delay = base_delay * (2 ** i)
            log.warning("Sheets API %s — retrying in %.1fs (attempt %d/%d)", status, delay, i + 1, attempts)
            time.sleep(delay)


def fetch_events(sheet_id: str) -> list[dict]:
    def _do():
        gc = _sheet_client()
        sh = gc.open_by_key(sheet_id)
        ws = sh.worksheet(WORKSHEET_NAME)
        return ws.get_all_records(expected_headers=HEADERS)
    records = _with_retry(_do)
    log.info("Fetched %d rows from Events sheet", len(records))
    return records


def fetch_weekly_runs(sheet_id: str) -> list[dict]:
    def _do():
        gc = _sheet_client()
        sh = gc.open_by_key(sheet_id)
        ws = sh.worksheet(WEEKLY_WORKSHEET)
        return ws.get_all_records(expected_headers=WEEKLY_HEADERS)
    records = _with_retry(_do)
    log.info("Fetched %d rows from WeeklyRuns sheet", len(records))
    return records


def fetch_overrides(sheet_id: str) -> dict[tuple[str, str], dict]:
    """Return a dict keyed by (club_lower, YYYY-MM-DD) → override row.

    Returns an empty dict if the Overrides worksheet doesn't exist yet.
    """
    def _do():
        gc = _sheet_client()
        sh = gc.open_by_key(sheet_id)
        try:
            ws = sh.worksheet(OVERRIDES_WORKSHEET)
        except gspread.exceptions.WorksheetNotFound:
            return None
        return ws.get_all_records(expected_headers=OVERRIDES_HEADERS)
    records = _with_retry(_do)
    if records is None:
        log.warning("Overrides worksheet not found — skipping overrides")
        return {}
    log.info("Fetched %d rows from Overrides sheet", len(records))
    result = {}
    for r in records:
        club     = (r.get("club") or "").strip().lower()
        date_val = (r.get("date") or "").strip()
        if club and date_val:
            result[(club, date_val)] = r
    return result


def fetch_special_events(sheet_id: str) -> list[dict]:
    """Return rows from the SpecialEvents worksheet, or [] if it doesn't exist yet."""
    def _do():
        gc = _sheet_client()
        sh = gc.open_by_key(sheet_id)
        try:
            ws = sh.worksheet(SPECIAL_WORKSHEET)
        except gspread.exceptions.WorksheetNotFound:
            return None
        return ws.get_all_records(expected_headers=SPECIAL_HEADERS)
    records = _with_retry(_do)
    if records is None:
        log.warning("SpecialEvents worksheet not found — skipping")
        return []
    log.info("Fetched %d rows from SpecialEvents sheet", len(records))
    return records

# ── Date / time parsing ───────────────────────────────────────────────────────

def _parse_date(raw: str) -> datetime | None:
    """Parse an ISO-ish date string. Accepts with/without seconds and date-only."""
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.strip(), fmt)
        except (ValueError, AttributeError):
            continue
    return None


def _parse_time(time_str: str) -> tuple[int, int]:
    """Return (hour, minute) from a loose time string like '18:00', '8.30', etc."""
    parts = time_str.strip().replace(".", ":").split(":")
    try:
        return int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        return 0, 0


def combine_date_time(raw_date: str, raw_time: str) -> str:
    """Merge separate date and time strings into a single ISO datetime string.

    Handles times of any length ('8:00', '18:00', '18:00:00', '18.30') by
    normalising through _parse_time rather than relying on string length.
    If raw_date already contains a 'T' (already combined) it is returned as-is.
    """
    if raw_date and "T" not in raw_date and raw_time:
        h, m = _parse_time(raw_time)
        return f"{raw_date}T{h:02d}:{m:02d}:00"
    return raw_date


# ── Static HTML rendering ─────────────────────────────────────────────────────

_SV_MONTHS_SHORT = ['jan','feb','mar','apr','maj','jun','jul','aug','sep','okt','nov','dec']
_SV_DAYS         = ['Söndag','Måndag','Tisdag','Onsdag','Torsdag','Fredag','Lördag']
_SV_MONTHS       = ['Januari','Februari','Mars','April','Maj','Juni','Juli','Augusti','September','Oktober','November','December']

_PIN_SVG = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>'
_PPL_SVG = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></svg>'
_EXT_SVG = '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="vertical-align:middle;margin-left:2px;"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>'
_ARR_SVG = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M12 5l7 7-7 7"/></svg>'


def _e(s: object) -> str:
    return _html_lib.escape(str(s or ""), quote=True)


def card_html(ev: dict) -> str:
    """Render one event card as static HTML, matching the JS cardHTML() function."""
    source = ev.get("source") or ""
    club   = ev.get("club")   or ""
    title  = ev.get("title")  or ""
    link   = ev.get("link")   or ""

    d: datetime | None = None
    date_str = ev.get("date") or ""
    if date_str:
        try:
            d = datetime.fromisoformat(date_str)
        except ValueError:
            pass

    if d:
        js_day     = (d.weekday() + 1) % 7  # Python Mon=0..Sun=6 → JS Sun=0..Sat=6
        date_block = (
            f'<div class="event-date-block">'
            f'<div class="event-day-num">{d.day}</div>'
            f'<div class="event-month-abbr">{_SV_MONTHS_SHORT[d.month - 1]}</div>'
            f'<div class="event-day-name">{_SV_DAYS[js_day][:3]}</div>'
            f'</div>'
        )
    else:
        date_block = '<div class="event-date-block no-date"><div class="event-day-num">—</div></div>'

    image_html = (
        f'<img class="event-card-image" src="{_e(ev["image_url"])}" alt="" loading="lazy">'
        if ev.get("image_url") else ""
    )

    loc_html = (
        f'<div class="event-location">{_PIN_SVG}{_e(ev["location"])}</div>'
        if ev.get("location") else ""
    )

    desc_html = (
        f'<p class="event-desc">{_e(ev["description"])}</p>'
        if ev.get("description") else ""
    )

    if ev.get("type") == "weekly_run":
        type_badge = '<span class="type-badge type-weekly">Weekly run</span>'
    elif source in ("strava", "special"):
        type_badge = ""
    else:
        type_badge = '<span class="type-badge type-event">Event</span>'

    if source == "weekly_run":
        source_badge = ""
    elif source == "special":
        source_badge = '<span class="source-badge source-special">Special Event</span>'
    elif source == "strava":
        source_badge = '<span class="source-badge source-strava">Strava</span>'
    else:
        source_badge = f'<span class="source-badge source-other">{_e(source)}</span>'

    engagement = str(ev.get("engagement") or "")
    eng_html = (
        f'<span class="event-engagement">{_PPL_SVG}{_e(engagement)} anmälda</span>'
        if engagement and source == "strava"
        else "<span></span>"
    )

    if link:
        cta_icon = _EXT_SVG if source == "strava" else _ARR_SVG
        cta_html = f'<span class="event-cta">Läs mer {cta_icon}</span>'
    else:
        cta_html = ""

    inner = (
        f'{image_html}'
        f'<div class="event-card-top">'
        f'{date_block}'
        f'<div class="event-card-body">'
        f'<div class="event-source-row">{type_badge}{source_badge}<span class="event-club">{_e(club)}</span></div>'
        f'<div class="event-title">{_e(title)}</div>'
        f'{loc_html}{desc_html}'
        f'</div>'
        f'</div>'
        f'<div class="event-card-footer">{eng_html}{cta_html}</div>'
    )

    special_class = " event-card--special" if source == "special" else ""
    club_page = ev.get("club_page") or ""
    for prefix in ("https://runclubs.se/", "http://runclubs.se/"):
        if club_page.startswith(prefix):
            club_page = club_page[len(prefix):]
            break
    href = (club_page or link) if source == "special" else link

    data = f'data-source="{_e(source)}" data-club="{_e(club)}"'
    if href:
        target = ' target="_blank" rel="noopener"' if source == "strava" else ""
        return f'<a href="{_e(href)}"{target} class="event-card{special_class}" aria-label="{_e(title)}" {data}>{inner}</a>'
    return f'<div class="event-card event-card--no-link{special_class}" aria-label="{_e(title)}" {data}>{inner}</div>'


def render_events_section(events: list[dict]) -> tuple[str, int, int]:
    """Group events by date and return (static_html, total_count, club_count)."""
    by_date: dict[str, dict] = {}
    no_date: list[dict] = []

    for ev in events:
        date_str = ev.get("date") or ""
        if date_str:
            try:
                d = datetime.fromisoformat(date_str)
                key = date_str[:10]
                if key not in by_date:
                    js_day = (d.weekday() + 1) % 7
                    label  = f"{_SV_DAYS[js_day]} {d.day} {_SV_MONTHS[d.month - 1]}"
                    by_date[key] = {"label": label, "events": []}
                by_date[key]["events"].append(ev)
            except ValueError:
                no_date.append(ev)
        else:
            no_date.append(ev)

    parts: list[str] = []
    for key in sorted(by_date.keys()):
        group = by_date[key]
        count = len(group["events"])
        s     = "s" if count != 1 else ""
        cards = "".join(card_html(ev) for ev in group["events"])
        parts.append(
            f'<div class="date-group" data-date-group="{key}">'
            f'<div class="date-heading">'
            f'<span class="date-name">{group["label"]}</span>'
            f'<div class="date-line"></div>'
            f'<span class="date-count" data-count-label="{key}">{count} event{s}</span>'
            f'</div>'
            f'<div class="events-grid">{cards}</div>'
            f'</div>'
        )

    if no_date:
        count = len(no_date)
        s     = "ar" if count != 1 else ""
        cards = "".join(card_html(ev) for ev in no_date)
        parts.append(
            f'<div class="date-group" data-date-group="nodate">'
            f'<div class="date-heading">'
            f'<span class="date-name">Inget datum</span>'
            f'<div class="date-line"></div>'
            f'<span class="date-count" data-count-label="nodate">{count} post{s}</span>'
            f'</div>'
            f'<div class="events-grid">{cards}</div>'
            f'</div>'
        )

    total_count = len(events)
    club_count  = len({ev.get("club") for ev in events if ev.get("club")})
    return "\n".join(parts), total_count, club_count
