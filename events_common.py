"""Shared utilities for all generate_*_events.py scripts.

Any fix to fetch logic, date/time parsing, or sheet constants goes here once
and automatically applies to all four generators.
"""

from __future__ import annotations

import html as _html_lib
import json
import logging
import os
import re
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
    # Strava spells several clubs differently from the WeeklyRuns sheet. Map
    # them onto the sheet's name — the one the club's own page uses — so the
    # cards dedupe and the club filter lists each club once.
    "saucony sverige":                           "Saucony Run Club Sverige",
    "måndagsklubben_gbg":                        "Måndagsklubben",
    "göteborg running club (grc)":               "Göteborg Running Club",
    "rtc":                                       "Roberg Training Club (RTC)",
    "stadium run club - sverige":                "Stadium Run Club",
    "nasci run club - för gravida & postpartum": "Nasci Run Club",
    "triple threshold running communion":        "Triple Threshold RC",
    "solemates run club":                        "Solemates Runclub",
    "slowrunners":                               "Slowrunners Stockholm",
    "run for a bun":                             "Run For a Bun Jönköping",
}

# The Special Events sheet appends the venue to the club name
# ("ESS Runners Club @Pigalle") and the venue changes from week to week.
_VENUE_SUFFIX = re.compile(r"\s*@.*$")


def normalize_club_name(name: str) -> str:
    """Canonical club name, used for display, filter pills and deduping.

    The venue suffix from the Special Events sheet is dropped — the venue is
    already carried by the event's location — so a club gets one name, one
    filter pill and one dedupe key no matter which sheet it came in through.
    """
    n = _VENUE_SUFFIX.sub("", name.strip()).strip()
    return CLUB_NAME_ALIASES.get(n.lower(), n)


# ── City resolution ──────────────────────────────────────────────────────────
# The only place that decides which city page an event lands on. Keywords are
# written in plain Swedish; matching folds å/ä/ö so "Varmdo" and "Värmdö" both
# hit, and only at the start of a word so "kista" doesn't match "Pakistan".

CITY_STOCKHOLM = "Stockholm"
CITY_GOTEBORG  = "Göteborg"
CITY_OVRIGA    = "Övriga landet"

STOCKHOLM_KEYWORDS = (
    "stockholm", "sthlm",
    "solna", "sundbyberg", "nacka", "värmdö", "hemmesta", "gustavsberg",
    "lidingö", "täby", "danderyd", "huddinge", "haninge", "tyresö",
    "botkyrka", "järfälla", "sollentuna", "upplands väsby", "vallentuna",
    "österåker", "ekerö", "södertälje", "bromma", "kista", "hammarby",
    "södermalm", "kungsholmen", "vasastan", "östermalm", "liljeholmen",
    "hägersten",
)
GOTEBORG_KEYWORDS = (
    "göteborg", "gothenburg", "västra götaland",
    "mölndal", "partille", "kungälv", "lerum", "härryda", "hisingen",
    "askim", "frölunda", "torslanda", "billdal",
)
# Known places outside the two big cities. Not needed for the fallback (which
# lands in Övriga landet anyway) but checked before the club's home city, so a
# Stockholm club racing in Malmö isn't listed under Stockholm.
OVRIGA_LANDET_KEYWORDS = (
    "malmö", "malmoe", "skåne", "limhamn", "lund", "helsingborg",
    "varberg", "halmstad", "falkenberg", "uppsala", "gävle",
    "linköping", "norrköping", "jönköping", "örebro", "västerås",
    "umeå", "luleå", "sundsvall", "karlstad", "växjö", "kalmar", "visby",
)

_FOLD = str.maketrans("åäö", "aao")


def _fold(text: str) -> str:
    return text.lower().translate(_FOLD)


def _keyword_pattern(keywords: tuple[str, ...], whole_word: bool = False) -> re.Pattern:
    alts = "|".join(re.escape(_fold(k)) for k in keywords)
    # Whole words (plus genitive -s) for other towns, so Stockholm streets
    # like Lundagatan or Kalmarvägen aren't read as Lund or Kalmar.
    tail = r"s?(?![a-z0-9])" if whole_word else ""
    return re.compile(rf"(?<![a-z0-9])(?:{alts}){tail}")


_CITY_PATTERNS = (
    (CITY_STOCKHOLM, _keyword_pattern(STOCKHOLM_KEYWORDS)),
    (CITY_GOTEBORG,  _keyword_pattern(GOTEBORG_KEYWORDS)),
    (CITY_OVRIGA,    _keyword_pattern(OVRIGA_LANDET_KEYWORDS, whole_word=True)),
)


def _match_city(text: str) -> str:
    """City whose keywords appear in `text`, or "" if none do."""
    t = _fold(text)
    for city, pattern in _CITY_PATTERNS:
        if pattern.search(t):
            return city
    return ""


def _normalize_city(text: str) -> str:
    """Canonical city for a curated `city` column (WeeklyRuns, SpecialEvents).

    Blank stays blank (the row is skipped); anything filled in that isn't
    Stockholm or Göteborg is Övriga landet.
    """
    if not text.strip():
        return ""
    return _match_city(text) or CITY_OVRIGA


# Events abroad (clubs with chapters in Oslo, Copenhagen, Istanbul…) must not
# fall through to Övriga landet. Strava locations end in the country name, and
# titles often carry a flag emoji.
ABROAD_KEYWORDS = (
    "danmark", "denmark", "københavn", "kobenhavn", "copenhagen", "köpenhamn",
    "norge", "norway", "oslo", "trondheim", "bergen",
    "finland", "suomi", "helsingfors", "helsinki",
    "belgië", "belgie", "belgium", "belgien",
    "deutschland", "germany", "tyskland", "berlin",
    "nederland", "netherlands", "amsterdam",
    "united kingdom", "england", "london",
    "france", "frankrike", "paris",
    "españa", "spain", "spanien", "barcelona", "madrid",
    "italia", "italy", "italien",
    "türkiye", "turkey", "turkiet", "istanbul",
    "usa", "united states", "new york",
)
_ABROAD_PATTERN = _keyword_pattern(ABROAD_KEYWORDS, whole_word=True)
# A pair of regional-indicator symbols is a flag; 🇸🇪 is the only one we keep.
_FLAG_PATTERN = re.compile("[\U0001F1E6-\U0001F1FF]{2}")


def is_abroad(location: str, title: str = "") -> bool:
    """True when an event is clearly outside Sweden."""
    if _ABROAD_PATTERN.search(_fold(location)):
        return True
    return any(flag != "🇸🇪" for flag in _FLAG_PATTERN.findall(f"{location} {title}"))


def resolve_city(location: str, club: str, club_cities: dict[str, str] | None,
                 title: str = "") -> str:
    """City for a Strava event, or "" for events abroad (callers skip those).

    Order: keywords in the location, then events abroad are dropped, then the
    club's city from WeeklyRuns, then Övriga landet (logged, so missing places
    can be added above).
    """
    city = _match_city(location)
    if city:
        return city
    if is_abroad(location, title):
        log.info("Dropping event abroad: club=%r location=%r title=%r", club, location, title)
        return ""
    club_key = normalize_club_name(club).lower()
    city = (club_cities or {}).get(club_key, "")
    if city:
        return city
    log.info("City fallback → Övriga landet: club=%r location=%r", club, location)
    return CITY_OVRIGA


def build_club_cities(weekly_records: list[dict]) -> dict[str, str]:
    """Return {club_name_lower: canonical_city} derived from the WeeklyRuns sheet.

    Used by resolve_city() when a Strava event's location field doesn't contain
    a recognisable city keyword.
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


# Highest priority first. When several sources describe the same club's run on
# the same day, the card from the earliest source in this tuple is the one kept:
# Strava carries the real title, description, map and event link; a Special
# Event is a hand-curated one-off; the WeeklyRuns card is the generic fallback.
SOURCE_PRIORITY = ("strava", "special", "weekly_run")

def club_match_key(name: str) -> str:
    """Key deciding whether two cards describe the same club.

    normalize_club_name() already drops the venue suffix and applies
    CLUB_NAME_ALIASES, so a club spelled differently between two sheets needs
    an entry there to be recognised as the same club.
    """
    return normalize_club_name(name).casefold()


def drop_duplicate_cards(events: list[dict]) -> list[dict]:
    """Collapse cards describing the same club's run on the same day.

    A club can reach the site through all three sheets at once — a WeeklyRuns
    entry for the recurring slot, a Special Events entry for that week's
    version, and a Strava event the club posted itself — which renders as two
    or three cards for a single run. Keep the highest-priority source present
    for that club and day (see SOURCE_PRIORITY) and drop the rest.

    Matching is per calendar day, not per start time, because the same run is
    routinely listed a few minutes apart across sheets.
    """
    rank = {src: i for i, src in enumerate(SOURCE_PRIORITY)}

    best: dict[tuple, int] = {}
    for e in events:
        if not e.get("date") or e.get("source") not in rank:
            continue
        k = (club_match_key(e["club"]), e["date"][:10])
        r = rank[e["source"]]
        if r < best.get(k, len(rank)):
            best[k] = r

    kept: list[dict] = []
    dropped: list[dict] = []
    for e in events:
        if e.get("date") and e.get("source") in rank:
            k = (club_match_key(e["club"]), e["date"][:10])
            if rank[e["source"]] > best[k]:
                dropped.append(e)
                continue
        kept.append(e)

    for e in dropped:
        log.info("Hidden as duplicate (%s outranked): %s on %s — %s",
                 e["source"], e["club"], e["date"][:10], e.get("title", ""))
    if dropped:
        log.info("Dropped %d duplicate card(s) across sources", len(dropped))
    return kept


# ── Static HTML rendering ─────────────────────────────────────────────────────

_SV_MONTHS_SHORT = ['jan','feb','mar','apr','maj','jun','jul','aug','sep','okt','nov','dec']
_SV_DAYS         = ['Söndag','Måndag','Tisdag','Onsdag','Torsdag','Fredag','Lördag']
_SV_MONTHS       = ['Januari','Februari','Mars','April','Maj','Juni','Juli','Augusti','September','Oktober','November','December']


def sv_long_date(d) -> str:
    """Format a date/datetime as "19 augusti 2026" (Swedish, lowercase month).

    strftime("%B") would emit the C-locale English month name on a Swedish page.
    """
    return f"{d.day} {_SV_MONTHS[d.month - 1].lower()} {d.year}"


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


def render_events_section(events: list[dict], card_fn=None) -> tuple[str, int, int]:
    """Group events by date and return (static_html, total_count, club_count).

    card_fn renders one card; defaults to card_html (used by the city pages).
    """
    card_fn = card_fn or card_html
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
        cards = "".join(card_fn(ev) for ev in group["events"])
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
        cards = "".join(card_fn(ev) for ev in no_date)
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
