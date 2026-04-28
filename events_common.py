"""Shared utilities for all generate_*_events.py scripts.

Any fix to fetch logic, date/time parsing, or sheet constants goes here once
and automatically applies to all four generators.
"""

from __future__ import annotations

import json
import logging
import os
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
}

def normalize_club_name(name: str) -> str:
    return CLUB_NAME_ALIASES.get(name.strip().lower(), name.strip())

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


def fetch_events(sheet_id: str) -> list[dict]:
    gc = _sheet_client()
    sh = gc.open_by_key(sheet_id)
    ws = sh.worksheet(WORKSHEET_NAME)
    records = ws.get_all_records(expected_headers=HEADERS)
    log.info("Fetched %d rows from Events sheet", len(records))
    return records


def fetch_weekly_runs(sheet_id: str) -> list[dict]:
    gc = _sheet_client()
    sh = gc.open_by_key(sheet_id)
    ws = sh.worksheet(WEEKLY_WORKSHEET)
    records = ws.get_all_records(expected_headers=WEEKLY_HEADERS)
    log.info("Fetched %d rows from WeeklyRuns sheet", len(records))
    return records


def fetch_overrides(sheet_id: str) -> dict[tuple[str, str], dict]:
    """Return a dict keyed by (club_lower, YYYY-MM-DD) → override row.

    Returns an empty dict if the Overrides worksheet doesn't exist yet.
    """
    gc = _sheet_client()
    sh = gc.open_by_key(sheet_id)
    try:
        ws = sh.worksheet(OVERRIDES_WORKSHEET)
    except gspread.exceptions.WorksheetNotFound:
        log.warning("Overrides worksheet not found — skipping overrides")
        return {}
    records = ws.get_all_records(expected_headers=OVERRIDES_HEADERS)
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
    gc = _sheet_client()
    sh = gc.open_by_key(sheet_id)
    try:
        ws = sh.worksheet(SPECIAL_WORKSHEET)
    except gspread.exceptions.WorksheetNotFound:
        log.warning("SpecialEvents worksheet not found — skipping")
        return []
    records = ws.get_all_records(expected_headers=SPECIAL_HEADERS)
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
