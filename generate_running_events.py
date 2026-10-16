"""Generate running-events.html from the running-clubs events Google Sheet.

Reads from two worksheets:
  - Events       populated by mikaelsto/runclubs-events-feed (Strava)
  - WeeklyRuns   manually maintained recurring club runs

Filters to Stockholm, Göteborg, and everywhere else in Sweden ("Övriga landet").

Usage:
    python generate_running_events.py                    # writes running-events.html
    python generate_running_events.py path/to/out.html   # custom output path
"""

from __future__ import annotations

import hashlib
import html
import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from events_common import (
    DAYS_MAP,
    EVENTS_SHEET_ID,
    LOOKAHEAD_DAYS,
    STOCKHOLM,
    _normalize_city,
    build_club_cities,
    combine_date_time,
    drop_duplicate_cards,
    fetch_events,
    fetch_overrides,
    fetch_special_events,
    fetch_weekly_runs,
    normalize_club_name,
    render_events_section,
    resolve_city,
    sv_long_date,
    _parse_date,
    _parse_time,
    _ARR_SVG,
    _EXT_SVG,
    _PIN_SVG,
    _SV_DAYS,
    _SV_MONTHS_SHORT,
    _e,
    club_match_key,
)

log = logging.getLogger(__name__)

def _utc_to_stockholm(dt: datetime) -> datetime:
    """Convert a naive datetime (assumed UTC) to Stockholm local time (naive)."""
    return dt.replace(tzinfo=timezone.utc).astimezone(STOCKHOLM).replace(tzinfo=None)


def build_club_pages(weekly_records: list[dict]) -> dict[str, str]:
    """Map club name (lowercased) → club page URL.

    First scans local club HTML files (CLUB_NAMES → canonical URL), then
    overlays WeeklyRuns sheet data so sheet values take precedence.
    """
    import glob, re as _re
    pages: dict[str, str] = {}
    # Scan all local HTML files for CLUB_NAMES + canonical URL
    for path in glob.glob("*.html"):
        try:
            text = open(path, encoding="utf-8").read()
        except OSError:
            continue
        m_canon = _re.search(
            r'rel=["\']canonical["\'][^>]*href=["\']([^"\']+)["\']'
            r'|href=["\']([^"\']+)["\'][^>]*rel=["\']canonical["\']', text)
        if not m_canon:
            continue
        canonical = m_canon.group(1) or m_canon.group(2)
        m_names = _re.search(r'var CLUB_NAMES\s*=\s*\[([^\]]+)\]', text)
        if not m_names:
            continue
        for name in _re.findall(r'"([^"]+)"', m_names.group(1)):
            pages[name.lower()] = canonical
    # Overlay WeeklyRuns sheet (takes precedence)
    for r in weekly_records:
        club = (r.get("club") or "").strip()
        link = (r.get("link") or "").strip()
        if club and link:
            pages[club.lower()] = link
    return pages


def prepare_special_events(records: list[dict], club_pages: dict[str, str]) -> list[dict]:
    today = datetime.now(STOCKHOLM).date()
    events: list[dict] = []

    for r in records:
        raw_date = (r.get("date") or "").strip()
        raw_time = (r.get("time") or "").strip()

        raw_date = combine_date_time(raw_date, raw_time)
        dt = _parse_date(raw_date)
        if dt is not None and dt.date() < today:
            continue

        city_raw = (r.get("city") or "").strip()
        city = _normalize_city(city_raw)
        if not city:
            continue

        club = normalize_club_name(r.get("club") or "")
        events.append({
            "type":        "event",
            "source":      "special",
            "club":        club,
            "title":       (r.get("title") or "Untitled").strip(),
            "date":        dt.strftime("%Y-%m-%dT%H:%M:%S") if dt else "",
            "location":    (r.get("location") or "").strip(),
            "city":        city,
            "club_page":   club_pages.get(club.lower(), ""),
            "description": (r.get("description") or "").strip(),
            "link":        (r.get("link") or "").strip(),
            "image_url":   (r.get("image_url") or "").strip(),
            "engagement":  "",
        })

    log.info("%d special events after filtering (all cities)", len(events))
    return events


def prepare_events(
    records: list[dict],
    club_pages: dict[str, str],
    club_cities: dict[str, str] | None = None,
) -> list[dict]:
    today = datetime.now(STOCKHOLM).date()
    events: list[dict] = []

    for r in records:
        raw_date = (r.get("date") or "").strip()
        dt = _parse_date(raw_date)
        if dt is not None:
            dt = _utc_to_stockholm(dt)  # Strava times are UTC → convert to Stockholm
            if dt.date() < today:
                continue

        loc = (r.get("location") or "").strip()
        city = resolve_city(loc, r.get("club") or "", club_cities)

        club = normalize_club_name(r.get("club") or "")
        events.append({
            "type":        "event",
            "source":      (r.get("source") or "").strip().lower(),
            "club":        club,
            "title":       (r.get("title") or "Untitled").strip(),
            "date":        dt.strftime("%Y-%m-%dT%H:%M:%S") if dt else "",
            "location":    loc,
            "city":        city,
            "club_page":   club_pages.get(club.lower(), ""),
            "description": (r.get("description") or "").strip(),
            "link":        (r.get("link") or "").strip(),
            "image_url":   (r.get("image_url") or "").strip(),
            "engagement":  str(r.get("engagement") or "").strip(),
        })

    seen: set[tuple] = set()
    unique: list[dict] = []
    for e in events:
        key = (e["club"], e["date"], e["title"])
        if key not in seen:
            seen.add(key)
            unique.append(e)
    if len(unique) < len(events):
        log.warning("Dropped %d duplicate Strava rows from sheet", len(events) - len(unique))
    log.info("%d upcoming events after filtering (all cities)", len(unique))
    return unique


def expand_weekly_runs(
    records: list[dict],
    overrides: dict[tuple[str, str], dict],
) -> list[dict]:
    today = datetime.now(timezone.utc).date()
    cutoff = today + timedelta(days=LOOKAHEAD_DAYS)
    events: list[dict] = []

    for r in records:
        day_str = (r.get("day_of_week") or "").lower().strip()
        target_weekday = DAYS_MAP.get(day_str)
        if target_weekday is None:
            log.warning("Unknown day_of_week %r for club %r — skipping", day_str, r.get("club"))
            continue

        city = _normalize_city((r.get("city") or "").strip())
        if not city:
            continue

        club      = normalize_club_name(r.get("club") or "")
        hour, minute = _parse_time(r.get("time") or "")

        current = today
        while current <= cutoff:
            if current.weekday() == target_weekday:
                date_key = current.strftime("%Y-%m-%d")
                override = overrides.get((club.lower(), date_key))

                if override:
                    action = (override.get("action") or "").strip().lower()
                    if action == "cancel":
                        log.info("Cancelled weekly run: %s on %s", club, date_key)
                        current += timedelta(days=1)
                        continue
                    # action == "override": use override values, fall back to template
                    o_time = (override.get("time") or "").strip()
                    h, m   = _parse_time(o_time) if o_time else (hour, minute)
                    dt     = datetime(current.year, current.month, current.day, h, m)
                    club_link = (override.get("link") or r.get("link") or "").strip()
                    events.append({
                        "type":        "weekly_run",
                        "source":      "weekly_run",
                        "club":        club,
                        "title":       (override.get("title") or r.get("title") or "").strip(),
                        "date":        dt.strftime("%Y-%m-%dT%H:%M:%S"),
                        "location":    (override.get("location") or r.get("location") or "").strip(),
                        "city":        city,
                        "club_page":   club_link,
                        "description": (override.get("description") or r.get("description") or "").strip(),
                        "link":        club_link,
                        "image_url":   "",
                        "engagement":  "",
                    })
                    log.info("Override applied: %s on %s", club, date_key)
                else:
                    dt = datetime(current.year, current.month, current.day, hour, minute)
                    club_link = (r.get("link") or "").strip()
                    events.append({
                        "type":        "weekly_run",
                        "source":      "weekly_run",
                        "club":        club,
                        "title":       (r.get("title") or "").strip(),
                        "date":        dt.strftime("%Y-%m-%dT%H:%M:%S"),
                        "location":    (r.get("location") or "").strip(),
                        "city":        city,
                        "club_page":   club_link,
                        "description": (r.get("description") or "").strip(),
                        "link":        club_link,
                        "image_url":   "",
                        "engagement":  "",
                    })

            current += timedelta(days=1)

    log.info("%d weekly run occurrences expanded (all cities, (next %d days)", len(events), LOOKAHEAD_DAYS)
    return events


# ── /events feed cards ────────────────────────────────────────────────────────

ROOT = Path(__file__).parent
CLUB_LISTING_PAGES = ("stockholm.html", "goteborg.html", "ovriga-landet.html")

_CLUB_CARD_START_RE = re.compile(r'<a href="(?P<href>[^"]+)" class="club-card"')
_CARD_IMG_RE  = re.compile(r'<img src="(?P<src>[^"]+)"(?P<attrs>[^>]*)>')
_CARD_NAME_RE = re.compile(r'<div class="card-name">(?P<name>[^<]+)</div>')
_OBJ_POS_RE = re.compile(r"object-position:\s*([^;\"]+)")


def _page_slug(url: str) -> str:
    """'https://runclubs.se/bbrs.html' and '/stockholm/bbrs/' both → 'bbrs'."""
    path = re.sub(r"^https?://[^/]+", "", url or "").split("?")[0].strip("/")
    last = path.rsplit("/", 1)[-1]
    return last[:-5] if last.endswith(".html") else last


_LOOSE_DROP_RE = re.compile(r"\b(run(ning)? ?club|gbg|sthlm|göteborg|stockholm|sverige|sweden)\b")


def _loose_club_key(name: str) -> str:
    """Forgiving club key: 'Mile Makers Run Club' ~ 'Mile Makers', 'Pace & People GBG' ~ 'Pace & People'."""
    k = club_match_key(html.unescape(name)).replace("&", " och ")
    return re.sub(r"[^0-9a-zåäö]", "", _LOOSE_DROP_RE.sub(" ", k))


def _load_slug_redirects() -> dict[str, str]:
    """Old club URLs → current ones, from _redirects (e.g. slowrunners-goteborg → pace-people)."""
    path = ROOT / "_redirects"
    if not path.exists():
        return {}
    redirects = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) >= 2 and not parts[0].startswith("http"):
            redirects.setdefault(_page_slug(parts[0]), _page_slug(parts[1]))
    return redirects


def load_club_images() -> dict[str, dict]:
    """Club card photos from the city listing pages, keyed by page slug and club name."""
    images: dict[str, dict] = {}
    for old, new in _load_slug_redirects().items():
        images["redirect:" + old] = new
    for name in CLUB_LISTING_PAGES:
        path = ROOT / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        starts = list(_CLUB_CARD_START_RE.finditer(text))
        for i, start in enumerate(starts):
            # Look only inside this card, so a card without a photo never borrows the next one's.
            card = text[start.end():starts[i + 1].start() if i + 1 < len(starts) else len(text)]
            m_img, m_name = _CARD_IMG_RE.search(card), _CARD_NAME_RE.search(card)
            if not m_img or not m_name or m_img.start() > m_name.start():
                continue
            pos = _OBJ_POS_RE.search(m_img["attrs"])
            src = m_img["src"] if m_img["src"].startswith(("http", "/")) else "/" + m_img["src"]
            img = {"src": src, "pos": pos.group(1).strip() if pos else "center"}
            images.setdefault("slug:" + _page_slug(start["href"]), img)
            images.setdefault("name:" + _loose_club_key(m_name["name"].strip()), img)
    return images


def club_image(ev: dict, club_images: dict[str, dict]) -> dict | None:
    slug = _page_slug(ev.get("club_page") or "")
    slug = club_images.get("redirect:" + slug, slug)
    return (club_images.get("slug:" + slug) if slug else None) or \
        club_images.get("name:" + _loose_club_key(ev.get("club") or ""))


# ── Distance / pace chips ─────────────────────────────────────────────────────
#
# Only shown on a sure hit: one distance (or one explicit range), one pace (or
# one range), or pace groups with their paces listed. Anything ambiguous —
# e.g. interval sessions listing several distances — gets no chip.

_NUM = r"\d{1,3}(?:[.,]\d)?"
_DIST_RE = re.compile(
    rf"(?<![\d:.,/])({_NUM})(?:\s*(?:[–-]|till)\s*({_NUM}))?\s*(?:km|k)\b(?!\s*/\s*h)",
    re.IGNORECASE,
)
_PACE = r"\d{1,2}[:.]\d{2}"
_PACE_RANGE = rf"(?<![\d:])({_PACE})(?:\s*[–-]\s*({_PACE}))?"
_PACE_RES = (
    # 5:30 min/km · 4:30/km · 6:30 minutes/km · 5:00 min per km
    re.compile(rf"{_PACE_RANGE}\s*(?:min(?:utes?|uter)?\s*(?:/|per)\s*km|/\s*km)", re.IGNORECASE),
    # tempo 06:00-06:30 · pace: 5:30
    re.compile(rf"\b(?:tempo|pace)\b[:\s]*(?:ca\.?\s*|~\s*)?{_PACE_RANGE}(?![\d])", re.IGNORECASE),
    # @ 5:30-5:45 pace
    re.compile(rf"{_PACE_RANGE}\s*(?:pace|tempo)\b", re.IGNORECASE),
)
_PACE_GROUP_RE = re.compile(r"pace[\s-]?(?:groups?|grupp(?:er)?)|tempogrupp(?:er)?", re.IGNORECASE)
_PACE_TIME_RE = re.compile(rf"(?<![\d:])({_PACE})(?![\d])")


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def _fmt_km(v: float) -> str:
    return f"{v:g}".replace(".", ",")


def _pace_secs(s: str) -> int | None:
    m, sec = re.split(r"[:.]", s)
    m, sec = int(m), int(sec)
    return m * 60 + sec if 3 <= m <= 9 and sec < 60 else None


def _fmt_pace(secs: int) -> str:
    return f"{secs // 60}:{secs % 60:02d}"


def parse_run_stats(text: str) -> list[str]:
    """Chips like '10 km', '10–12 km', '5:30 min/km', 'Pace groups 5:00–6:00'."""
    text = text or ""
    chips: list[str] = []

    distances = set()
    for lo, hi in _DIST_RE.findall(text):
        lo_v, hi_v = _num(lo), (_num(hi) if hi else None)
        if not 1 <= lo_v <= 100 or (hi_v is not None and not lo_v < hi_v <= 100):
            continue
        distances.add((lo_v, hi_v))
    if len(distances) == 1:
        lo_v, hi_v = distances.pop()
        chips.append(f"{_fmt_km(lo_v)}–{_fmt_km(hi_v)} km" if hi_v else f"{_fmt_km(lo_v)} km")

    group = _PACE_GROUP_RE.search(text)
    if group:
        window = text[group.end():group.end() + 80]
        times = sorted({t for t in map(_pace_secs, _PACE_TIME_RE.findall(window)) if t})
        if len(times) >= 2:
            chips.append(f"Pace groups {_fmt_pace(times[0])}–{_fmt_pace(times[-1])}")
        else:
            chips.append("Pace groups")
        return chips

    paces = set()
    for pace_re in _PACE_RES:
        for lo, hi in pace_re.findall(text):
            lo_s, hi_s = _pace_secs(lo), (_pace_secs(hi) if hi else None)
            if lo_s is None or (hi and (hi_s is None or hi_s <= lo_s)):
                continue
            paces.add((lo_s, hi_s))
    if len(paces) == 1:
        lo_s, hi_s = paces.pop()
        chips.append(f"{_fmt_pace(lo_s)}–{_fmt_pace(hi_s)} min/km" if hi_s else f"{_fmt_pace(lo_s)} min/km")
    return chips


def _is_route_map(url: str) -> bool:
    """Strava sends the route map as image_url (cloudfront …/maps/…)."""
    return "/maps/" in url


def _club_initial(ev: dict) -> str:
    for ch in (ev.get("club") or ev.get("title") or ""):
        if ch.isalnum():
            return ch.upper()
    return "•"


_HEART_SVG = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1-1.1a5.5 5.5 0 0 0-7.8 7.8l1 1.1L12 21l7.8-7.5 1-1.1a5.5 5.5 0 0 0 0-7.8z"/></svg>'

_SHARE_SVG = '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 12v7a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-7"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg>'

SITE_EVENTS_URL = "https://runclubs.se/events"


def event_id(ev: dict) -> str:
    """Stable per-occurrence id: same club run on the same day keeps its id across rebuilds,
    even if the start time is moved. Used for share links, likes and clicks."""
    key = "|".join((
        ev.get("source") or "",
        club_match_key(ev.get("club") or ""),
        (ev.get("date") or "")[:10],
        ev.get("link") or ev.get("title") or "",
    ))
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]


MEDIA_LABELS = {"photo": "Eventfoto", "map": "Karta", "club": "Klubbkort", "initial": "Initial"}


def pick_media(ev: dict, club_images: dict[str, dict], allow_map: bool = True) -> tuple[str, str]:
    """Image chain: event photo → route map → club card → peach plate with the club's initial.

    Returns (kind, inner_html). The highlight passes allow_map=False to skip the map.
    """
    url = ev.get("image_url") or ""
    if url and not _is_route_map(url):
        return "photo", f'<img src="{_e(url)}" alt="" loading="lazy" decoding="async">'
    if url and allow_map:
        return "map", f'<img src="{_e(url)}" alt="Karta över rutten" loading="lazy" decoding="async">'
    if (img := club_image(ev, club_images)):
        # Logos are shown whole on white; photos fill the panel.
        logo = ' class="ev-logo"' if "logo" in img["src"].rsplit("/", 1)[-1].lower() else ""
        return "club", (f'<img{logo} src="{_e(img["src"])}" alt="" loading="lazy" decoding="async" '
                        f'style="object-position: {_e(img["pos"])};">')
    return "initial", f'<span class="ev-initial" aria-hidden="true">{_e(_club_initial(ev))}</span>'


def feed_card_html(ev: dict, club_images: dict[str, dict], highlight: bool = False) -> str:
    """One /events card: full-height image left, content right."""
    source = ev.get("source") or ""
    club   = ev.get("club")   or ""
    title  = ev.get("title")  or ""
    link   = ev.get("link")   or ""

    when = ""
    date_str = ev.get("date") or ""
    if date_str:
        try:
            d = datetime.fromisoformat(date_str)
            js_day = (d.weekday() + 1) % 7
            when = f"{_SV_DAYS[js_day][:3]} {d.day} {_SV_MONTHS_SHORT[d.month - 1]}"
            if (d.hour, d.minute) != (0, 0):
                when += f" · {d:%H:%M}"
        except ValueError:
            pass

    media_kind, media = pick_media(ev, club_images, allow_map=not highlight)

    if source == "weekly_run":
        badge = '<span class="ev-badge ev-badge--weekly">Weekly run</span>'
    elif source == "special":
        badge = '<span class="ev-badge ev-badge--event">Event</span>'
    elif source == "strava":
        badge = '<span class="ev-badge ev-badge--strava">Strava</span>'
    else:
        badge = f'<span class="ev-badge">{_e(source)}</span>'

    meta = f'<span class="ev-club">{_e(club)}</span>' if club else ""
    if ev.get("location"):
        meta += f'<span class="ev-place">{_PIN_SVG}{_e(ev["location"])}</span>'

    desc_html = f'<p class="ev-desc">{_e(ev["description"])}</p>' if ev.get("description") else ""
    chips = parse_run_stats(ev.get("description") or "")
    chips_html = (
        '<div class="ev-chips">' + "".join(f'<span class="ev-chip">{_e(c)}</span>' for c in chips) + '</div>'
        if chips else ""
    )

    engagement = str(ev.get("engagement") or "")
    eng_html = (f'<span class="ev-engagement">{_e(engagement)} anmälda</span>'
                if engagement and source == "strava" else "")

    club_page = ev.get("club_page") or ""
    for prefix in ("https://runclubs.se/", "http://runclubs.se/"):
        if club_page.startswith(prefix):
            club_page = club_page[len(prefix):]
            break
    href = (club_page or link) if source == "special" else link

    if href:
        target = ' target="_blank" rel="noopener"' if source == "strava" else ""
        icon = _EXT_SVG if source == "strava" else _ARR_SVG
        title_html = f'<a class="ev-link" href="{_e(href)}"{target}>{_e(title)}</a>'
        cta_html = f'<a class="ev-cta" href="{_e(href)}"{target} tabindex="-1" aria-hidden="true">Till passet {icon}</a>'
    else:
        title_html = _e(title)
        cta_html = ""

    special = " ev-card--special" if source == "special" else ""
    if highlight:
        special += " ev-card--highlight"
    eid = event_id(ev)
    # Only the list card carries the anchor id; the highlight is a second copy of the same event.
    anchor = "" if highlight else f' id="ev-{eid}"'
    share_url = f"{SITE_EVENTS_URL}#ev-{eid}"
    return (
        f'<article class="ev-card{special}"{anchor} data-id="{eid}" data-source="{_e(source)}" data-club="{_e(club)}">'
        f'<div class="ev-media ev-media--{media_kind}">{media}'
        f'<span class="ev-media-label">{MEDIA_LABELS[media_kind]}</span></div>'
        f'<div class="ev-body">'
        f'<div class="ev-top">{badge}<span class="ev-when">{when}</span></div>'
        f'<h3 class="ev-title">{title_html}</h3>'
        f'<div class="ev-meta">{meta}</div>'
        f'{chips_html}'
        f'{desc_html}'
        f'<div class="ev-actions">'
        f'<button type="button" class="ev-like" aria-pressed="false" aria-label="Gilla {_e(title)}">'
        f'{_HEART_SVG}<span class="ev-like-count"></span></button>'
        f'<button type="button" class="ev-share" data-url="{_e(share_url)}" data-title="{_e(title)}" '
        f'aria-label="Dela {_e(title)}">{_SHARE_SVG}</button>'
        f'{eng_html}{cta_html}</div>'
        f'</div>'
        f'</article>'
    )


HIGHLIGHT_WINDOW_DAYS = 7


def pick_highlight(events: list[dict], now: datetime | None = None) -> dict | None:
    """Veckans höjdpunkt: a SpecialEvent with its own photo if there is one this week,
    else another SpecialEvent, else the Strava event with most sign-ups, else the next event."""
    now = now or datetime.now(STOCKHOLM).replace(tzinfo=None)
    cutoff = now + timedelta(days=HIGHLIGHT_WINDOW_DAYS)

    def upcoming(ev: dict) -> bool:
        try:
            return now <= datetime.fromisoformat(ev.get("date") or "") <= cutoff
        except ValueError:
            return False

    week = [ev for ev in events if upcoming(ev)]
    if not week:
        return None

    def has_photo(ev: dict) -> bool:
        return bool(ev.get("image_url")) and not _is_route_map(ev["image_url"])

    def signups(ev: dict) -> int:
        digits = re.sub(r"\D", "", str(ev.get("engagement") or ""))
        return int(digits) if digits else 0

    specials = [ev for ev in week if ev.get("source") == "special"]
    for pool in ([ev for ev in specials if has_photo(ev)], specials):
        if pool:
            return pool[0]
    strava = [ev for ev in week if ev.get("source") == "strava" and signups(ev) > 0]
    if strava:
        return max(strava, key=signups)
    return week[0]


def highlight_section_html(ev: dict | None, club_images: dict[str, dict]) -> str:
    if not ev:
        return ""
    return (
        '<section class="highlight" aria-labelledby="highlight-heading">'
        '<h2 class="section-heading" id="highlight-heading">Veckans höjdpunkt</h2>'
        f'{feed_card_html(ev, club_images, highlight=True)}'
        '</section>'
    )


def render_html(events: list[dict], generated_at: str) -> str:
    club_images = load_club_images()
    events_section, total_count, club_count = render_events_section(
        events, card_fn=lambda ev: feed_card_html(ev, club_images)
    )
    highlight_section = highlight_section_html(pick_highlight(events), club_images)
    events_json = json.dumps(events, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="sv">
<head>
<!-- Google Tag Manager (deferred) -->
<script>
window.dataLayer=window.dataLayer||[];
window.dataLayer.push({{'gtm.start':new Date().getTime(),event:'gtm.js'}});
document.addEventListener('DOMContentLoaded',function(){{
  setTimeout(function(){{
    var s=document.createElement('script');
    s.async=true;
    s.src='https://www.googletagmanager.com/gtm.js?id=GTM-TPSCMPZT';
    document.head.appendChild(s);
  }},1000);
}});
</script>
<!-- End Google Tag Manager -->
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Running Events Sverige — Swedish Run Clubs</title>
  <meta name="description" content="Alla kommande running events och weekly runs i Stockholm, Göteborg och övriga landet — från run clubs, grupper och communions.">
  <meta property="og:title" content="Running Events Sverige — Swedish Run Clubs">
  <meta property="og:description" content="Alla kommande running events och weekly runs i Stockholm, Göteborg och övriga landet.">
  <meta property="og:type" content="website">
  <meta property="og:url" content="https://runclubs.se/events">
  <meta property="og:image" content="https://runclubs.se/stockholm-run-clubs.jpeg">
  <link rel="canonical" href="https://runclubs.se/events">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Archivo+Black&family=Oswald:wght@500;700&family=DM+Sans:wght@400;500;600&family=Playfair+Display:ital,wght@0,400;1,400&display=swap" rel="stylesheet">
  <link rel="icon" href="/favicon.ico" sizes="any">
  <link rel="icon" href="/favicon.svg" type="image/svg+xml">
  <style>
    :root {{
      --bg: #FBF8F4;         /* off-white */
      --ink: #1F1B18;        /* mörk text */
      --ink-soft: #6B625B;
      --peach: #F6B89E;      /* accent */
      --peach-soft: #FFE6D8;
      --peach-deep: #EE9A78;
      --accent-ink: #A8502F; /* accenttext på ljus bakgrund */
    }}
    *, *::before, *::after {{ margin: 0; padding: 0; box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    html {{ background: var(--bg); }}
    body {{ font-family: 'DM Sans', sans-serif; color: var(--ink); background: var(--bg); max-width: 1400px; margin: 0 auto; -webkit-font-smoothing: antialiased; }}

    .skip-link {{
      position: absolute; top: -100%; left: 1rem;
      background: var(--peach); color: var(--ink); padding: 8px 16px;
      border-radius: 0 0 6px 6px; font-size: 13px; font-weight: 500;
      z-index: 1000; text-decoration: none;
    }}
    .skip-link:focus {{ top: 0; }}

    nav {{
      display: flex; justify-content: space-between; align-items: center;
      padding: 1.25rem 2rem;
      background: rgba(251,248,244,0.92); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
      border-bottom: 1px solid #F0E0DC;
      position: sticky; top: 0; z-index: 100;
    }}
    .logo {{
      font-family: 'DM Sans', sans-serif; font-weight: 700; font-size: 16px;
      text-transform: uppercase; letter-spacing: 2px;
      color: var(--ink); text-decoration: none;
    }}
    .run-clubs-logo {{
      display: inline-flex; align-items: baseline;
      font-family: 'Archivo Black', sans-serif; font-size: 24px; letter-spacing: -0.02em;
      color: var(--ink); text-decoration: none;
    }}
    .run-clubs-logo .run {{ color: var(--ink); }}
    .run-clubs-logo .clubs {{ color: #9A918A; }}
    .run-clubs-logo .suffix {{ font-size: 0.5em; text-transform: lowercase; margin-left: 1px; color: #9A918A; }}
    .nl-badge .run-clubs-logo, .nl-badge .run-clubs-logo span {{ color: inherit; font-size: 1em; }}
    .footer-brand .run-clubs-logo {{ font-size: 26px; display: inline-flex; margin-bottom: 0.75rem; }}
    .nav-links {{ display: flex; gap: 2rem; }}
    .nav-links a {{
      font-size: 12px; letter-spacing: 0.5px; text-decoration: none;
      color: #888; text-transform: uppercase; font-weight: 500;
      transition: color 0.2s; position: relative;
    }}
    .nav-links a::after {{
      content: ''; position: absolute; bottom: -4px; left: 0;
      width: 0; height: 1.5px; background: var(--peach-deep);
      transition: width 0.2s ease;
    }}
    .nav-links a:hover {{ color: var(--ink); }}
    .nav-links a:hover::after {{ width: 100%; }}
    .nav-links a.active {{ color: var(--ink); }}
    .nav-links a.active::after {{ width: 100%; }}
    .nav-toggle {{
      display: none; flex-direction: column; gap: 5px;
      cursor: pointer; background: none; border: none; padding: 4px;
    }}
    .nav-toggle span {{
      display: block; width: 22px; height: 2px;
      background: var(--ink); transition: all 0.3s ease;
    }}
    .nav-toggle.open span:nth-child(1) {{ transform: rotate(45deg) translate(5px, 5px); }}
    .nav-toggle.open span:nth-child(2) {{ opacity: 0; }}
    .nav-toggle.open span:nth-child(3) {{ transform: rotate(-45deg) translate(5px, -5px); }}
    .mobile-menu {{
      display: none; flex-direction: column;
      background: rgba(251,248,244,0.98); backdrop-filter: blur(12px);
      border-bottom: 1px solid #F0E0DC;
      padding: 1rem 2rem; gap: 0;
    }}
    .mobile-menu.open {{ display: flex; }}
    .mobile-menu a {{
      font-size: 13px; letter-spacing: 1px; text-decoration: none;
      color: var(--ink); text-transform: uppercase; font-weight: 500;
      padding: 0.75rem 0; border-bottom: 1px solid #F0E0DC;
      transition: color 0.15s;
    }}
    .mobile-menu a:last-child {{ border-bottom: none; }}
    .mobile-menu a:hover {{ color: var(--accent-ink); }}

    .page-header {{
      background: linear-gradient(160deg, #FFF8F3 0%, #FFDAC4 40%, #F6B89E 75%, #F88B69 100%);
      padding: 4rem 2rem 3rem;
      position: relative;
      overflow: hidden;
    }}
    .page-header::after {{
      content: ''; position: absolute; top: -90px; right: -70px;
      width: 280px; height: 280px; border-radius: 50%;
      background: rgba(255,255,255,0.35);
      pointer-events: none;
    }}
    .page-header::before {{
      content: ''; position: absolute; left: -80px; bottom: -140px;
      width: 260px; height: 260px; border-radius: 50%;
      background: rgba(31,27,24,0.08);
      pointer-events: none;
    }}
    .page-header-inner {{ max-width: 700px; position: relative; z-index: 1; }}
    .breadcrumb {{ font-size: 12px; color: rgba(31,27,24,0.45); margin-bottom: 0.75rem; }}
    .breadcrumb a {{ color: rgba(31,27,24,0.45); text-decoration: none; transition: color 0.15s; }}
    .breadcrumb a:hover {{ color: var(--accent-ink); }}
    .page-header-tag {{
      font-family: 'Playfair Display', serif; font-style: italic;
      font-size: 15px; letter-spacing: 0.5px;
      color: var(--accent-ink); margin-bottom: 1rem; font-weight: 400;
    }}
    .page-header h1 {{
      font-family: 'DM Sans', sans-serif; font-weight: 600;
      font-size: clamp(34px, 5.5vw, 58px);
      line-height: 1.08; letter-spacing: -0.02em;
      color: var(--accent-ink); margin-bottom: 1.25rem;
    }}
    .live-badge {{
      display: inline-flex; align-items: center; gap: 8px; margin-top: 1.5rem;
      padding: 7px 14px; border-radius: 100px;
      background: rgba(255,255,255,0.7); color: var(--ink);
      font-size: 12px; font-weight: 600; letter-spacing: 0.2px;
    }}
    .live-dot {{ width: 8px; height: 8px; border-radius: 50%; background: #FC5200; flex-shrink: 0; }}
    .page-header p {{
      font-size: 16px; color: rgba(31,27,24,0.75);
      line-height: 1.75; max-width: 520px;
    }}

    .stats-bar {{
      background: var(--peach);
      padding: 1rem 2rem;
      display: flex; gap: 2.5rem; flex-wrap: wrap;
    }}
    .stat-item {{ display: flex; align-items: center; gap: 8px; }}
    .stat-number {{
      font-family: 'DM Sans', sans-serif; font-weight: 600;
      font-size: 22px; color: var(--ink); line-height: 1;
    }}
    .stat-label {{
      font-size: 11px; letter-spacing: 1px; text-transform: uppercase;
      color: rgba(31,27,24,0.6); font-weight: 500;
    }}
    .stat-divider {{ width: 1px; background: rgba(31,27,24,0.15); align-self: stretch; }}

    .filters-bar {{
      padding: 1.5rem 2rem;
      border-bottom: 1px solid #F0E0DC;
    }}
    .filters-inner {{ display: flex; gap: 1.5rem; flex-wrap: wrap; align-items: center; }}
    .filter-toggle {{
      display: none;
      align-items: center; justify-content: space-between;
      width: 100%; padding: 10px 14px;
      background: #fff; border: 1px solid #E8D8D3; border-radius: 12px;
      font-family: 'DM Sans', sans-serif; font-size: 13px; font-weight: 500;
      color: var(--ink); cursor: pointer; transition: all 0.2s;
    }}
    .filter-toggle:hover {{ border-color: var(--peach-deep); }}
    .filter-toggle-label {{ display: flex; align-items: center; gap: 8px; }}
    .filter-toggle-chevron {{ transition: transform 0.2s; color: var(--accent-ink); }}
    .filters-bar.open .filter-toggle-chevron {{ transform: rotate(180deg); }}
    .close-filters {{
      font-size: 13px; color: var(--accent-ink); background: none; border: none;
      cursor: pointer; font-family: 'DM Sans', sans-serif; font-weight: 500;
      padding: 6px 0; text-decoration: underline; margin-left: auto;
      text-underline-offset: 2px; transition: color 0.15s; display: none;
    }}
    .filters-bar.open .close-filters {{ display: inline-block; }}
    .close-filters:hover {{ color: var(--ink); }}
    .filter-group {{ display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }}
    .filter-label {{
      font-size: 10px; letter-spacing: 2px; text-transform: uppercase;
      color: #bbb; font-weight: 500; margin-right: 4px;
    }}
    .filter-pill {{
      font-size: 12px; font-weight: 600; padding: 6px 16px;
      border-radius: 20px; border: 1px solid #E0D0CC;
      background: transparent; color: #888;
      cursor: pointer; font-family: 'DM Sans', sans-serif;
      transition: all 0.2s; text-transform: uppercase; letter-spacing: 0.5px;
    }}
    .filter-pill:hover {{ border-color: var(--peach-deep); color: var(--accent-ink); }}
    .filter-pill.active {{ background: var(--peach); color: var(--ink); border-color: var(--peach); }}

    .events-layout {{ padding: 3rem 2rem; max-width: 1200px; margin: 0 auto; }}

    .highlight {{ margin-bottom: 3.5rem; }}
    .section-heading {{
      font-family: 'Archivo Black', sans-serif;
      font-size: 20px; letter-spacing: 2px; text-transform: uppercase; color: var(--ink);
      margin-bottom: 1.25rem;
    }}
    .ev-card--highlight {{ min-height: 300px; border: 2px solid var(--peach); }}
    .ev-card--highlight .ev-media {{ flex-basis: 45%; max-width: 480px; }}
    .ev-card--highlight .ev-body {{ padding: 2rem 2.25rem; gap: 10px; }}
    .ev-card--highlight .ev-title {{ font-size: 26px; line-height: 1.2; }}
    .ev-card--highlight .ev-desc {{ font-size: 15px; -webkit-line-clamp: 3; }}
    .view-tabs {{
      display: inline-flex; gap: 4px; padding: 4px; margin-bottom: 2rem;
      background: #fff; border: 1px solid #EFE4E0; border-radius: 100px;
    }}
    .view-tab {{
      font-family: 'DM Sans', sans-serif; font-size: 13px; font-weight: 600;
      padding: 9px 20px; border-radius: 100px; border: none;
      background: transparent; color: #888; cursor: pointer;
      transition: background 0.2s, color 0.2s;
    }}
    .view-tab:hover {{ color: var(--ink); }}
    .view-tab[aria-selected="true"] {{ background: var(--ink); color: var(--bg); }}
    .view-tab:focus-visible {{ outline: 2px solid var(--accent-ink); outline-offset: 2px; }}

    .date-group {{ margin-bottom: 4rem; }}
    .date-heading {{ display: flex; align-items: center; gap: 1.25rem; margin-bottom: 1.75rem; }}
    .date-name {{
      font-family: 'Archivo Black', sans-serif;
      font-size: 20px; letter-spacing: 2px; text-transform: uppercase; color: var(--ink);
    }}
    .date-line {{ flex: 1; height: 1px; background: #F0E0DC; }}
    .date-count {{ white-space: nowrap; font-size: 11px; letter-spacing: 1px; text-transform: uppercase; color: #ccc; font-weight: 500; }}

    .events-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(min(100%, 440px), 1fr));
      gap: 24px;
    }}

    .ev-card {{
      position: relative;
      display: flex; align-items: stretch;
      min-height: 200px;
      background: #fff;
      border: 1px solid #EFE4E0;
      border-radius: 20px;
      overflow: hidden;
      color: var(--ink);
      transition: transform 0.25s ease, box-shadow 0.25s ease, border-color 0.25s ease;
    }}
    .ev-card[hidden] {{ display: none; }}
    .ev-card:has(.ev-link):hover {{
      transform: translateY(-3px);
      box-shadow: 0 14px 36px rgba(238,154,120,0.25);
      border-color: var(--peach-deep);
    }}
    .ev-card--special {{ border: 2px solid var(--peach); }}

    .ev-media {{
      flex: 0 0 34%; max-width: 180px;
      position: relative; overflow: hidden;
      background: var(--peach-soft);
    }}
    .ev-media img {{
      position: absolute; inset: 0;
      width: 100%; height: 100%; object-fit: cover; display: block;
    }}
    .ev-media--initial {{
      display: flex; align-items: center; justify-content: center;
      background: linear-gradient(160deg, var(--peach-soft), var(--peach));
    }}
    .ev-initial {{
      font-family: 'DM Sans', sans-serif; font-weight: 600; font-size: 60px; line-height: 1;
      color: rgba(255,255,255,0.9); text-shadow: 0 2px 12px rgba(168,80,47,0.25);
    }}
    .ev-media-label {{
      position: absolute; left: 8px; bottom: 8px; z-index: 1;
      font-size: 9px; font-weight: 700; letter-spacing: 1px; text-transform: uppercase;
      padding: 3px 7px; border-radius: 8px;
      background: rgba(31,27,24,0.7); color: #fff;
    }}
    .ev-media:has(.ev-logo) {{ background: #fff; border-right: 1px solid #F5EBE8; }}
    .ev-media .ev-logo {{ object-fit: contain; object-position: center !important; padding: 14px; }}

    .ev-body {{
      flex: 1; min-width: 0;
      padding: 1.25rem 1.5rem;
      display: flex; flex-direction: column; gap: 8px;
    }}
    .ev-top {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }}
    .ev-badge {{
      font-size: 10px; font-weight: 700; letter-spacing: 1px; text-transform: uppercase;
      padding: 4px 9px; border-radius: 10px; flex-shrink: 0;
      background: var(--ink-soft); color: #fff;
    }}
    .ev-badge--strava  {{ background: #FC5200; color: #fff; }}
    .ev-badge--weekly  {{ background: #D8F3DC; color: #1B4332; }}
    .ev-badge--event   {{ background: var(--ink); color: #fff; }}
    .ev-when {{ font-size: 13px; font-weight: 600; color: var(--ink-soft); }}
    .ev-title {{
      font-family: 'DM Sans', sans-serif; font-weight: 600;
      font-size: 18px; letter-spacing: -0.01em; line-height: 1.3; color: var(--ink);
    }}
    .ev-link {{ color: inherit; text-decoration: none; }}
    .ev-link::after {{ content: ''; position: absolute; inset: 0; z-index: 0; }}
    .ev-link:focus-visible {{ outline: none; }}
    .ev-card:has(.ev-link:focus-visible) {{ outline: 2px solid var(--accent-ink); outline-offset: 2px; }}
    .ev-meta {{
      display: flex; align-items: center; flex-wrap: wrap; gap: 2px 12px;
      font-size: 13px; color: var(--ink-soft);
    }}
    .ev-club {{ font-weight: 600; }}
    .ev-place {{ display: inline-flex; align-items: center; gap: 4px; }}
    .ev-place svg {{ flex-shrink: 0; }}
    .ev-chips {{ display: flex; flex-wrap: wrap; gap: 6px; }}
    .ev-chip {{
      font-size: 12px; font-weight: 600; color: var(--ink);
      background: var(--peach-soft); border-radius: 100px; padding: 3px 10px;
    }}
    .ev-desc {{
      font-size: 13px; color: #666; line-height: 1.65;
      display: -webkit-box; -webkit-line-clamp: 2;
      -webkit-box-orient: vertical; overflow: hidden;
    }}
    .ev-actions {{
      margin-top: auto; padding-top: 10px;
      display: flex; align-items: center; justify-content: space-between; gap: 12px;
    }}
    .ev-actions > * {{ position: relative; z-index: 1; }}
    .ev-engagement {{ font-size: 12px; font-weight: 500; color: #aaa; }}
    .ev-like {{
      display: inline-flex; align-items: center; gap: 5px;
      background: none; border: none; padding: 4px; margin: -4px;
      font-family: 'DM Sans', sans-serif; font-size: 13px; font-weight: 600;
      color: var(--ink-soft); cursor: pointer; border-radius: 8px;
      transition: color 0.2s;
    }}
    .ev-like:hover {{ color: var(--accent-ink); }}
    .ev-like:focus-visible {{ outline: 2px solid var(--accent-ink); outline-offset: 2px; }}
    .ev-like[aria-pressed="true"] {{ color: #E0533D; }}
    .ev-like[aria-pressed="true"] svg {{ fill: currentColor; }}
    .ev-like.pop svg {{ animation: heartPop 0.45s cubic-bezier(.3,1.6,.5,1); }}
    @keyframes heartPop {{
      0% {{ transform: scale(1); }}
      40% {{ transform: scale(1.35); }}
      70% {{ transform: scale(0.92); }}
      100% {{ transform: scale(1); }}
    }}
    .ev-share {{
      display: inline-flex; align-items: center; justify-content: center;
      background: none; border: none; padding: 4px; margin: -4px 0;
      color: var(--ink-soft); cursor: pointer; border-radius: 8px;
      transition: color 0.2s;
    }}
    .ev-share:hover {{ color: var(--accent-ink); }}
    .ev-share:focus-visible {{ outline: 2px solid var(--accent-ink); outline-offset: 2px; }}
    .ev-card.is-target {{ box-shadow: 0 0 0 3px var(--peach-deep), 0 14px 36px rgba(238,154,120,0.3); }}
    .toast {{
      position: fixed; left: 50%; bottom: 24px; z-index: 1100;
      transform: translate(-50%, 20px); opacity: 0; pointer-events: none;
      background: var(--ink); color: #fff; font-size: 14px; font-weight: 500;
      padding: 11px 18px; border-radius: 100px;
      box-shadow: 0 10px 30px rgba(31,27,24,0.25);
      transition: opacity 0.25s ease, transform 0.25s ease;
    }}
    .toast.show {{ opacity: 1; transform: translate(-50%, 0); }}
    .ev-cta {{
      margin-left: auto;
      font-size: 12px; font-weight: 600; letter-spacing: 0.5px;
      text-transform: uppercase; color: var(--accent-ink); text-decoration: none;
      display: inline-flex; align-items: center; gap: 4px;
      transition: gap 0.2s;
    }}
    .ev-card:hover .ev-cta {{ gap: 8px; }}

    .no-events {{
      grid-column: 1 / -1; text-align: center;
      padding: 4rem 1rem; color: #bbb;
    }}
    .no-events-icon {{ font-size: 48px; display: block; margin-bottom: 1rem; opacity: 0.55; }}
    .no-events p {{ font-size: 15px; }}

    .nl-section {{ background: #FFF8F3; border-top: 1px solid #F7E8E4; border-bottom: 1px solid #F7E8E4; position: relative; overflow: hidden; }}
    .nl-section::before {{ content: ''; position: absolute; top: -90px; left: -90px; width: 260px; height: 260px; border-radius: 50%; background: rgba(246,184,158,0.35); }}
    .nl-body {{ max-width: 560px; margin: 0 auto; padding: 4rem 2rem; text-align: center; }}
    .nl-badge {{
      display: inline-flex; align-items: center; gap: 8px;
      background: var(--peach-soft); color: var(--accent-ink);
      font-size: 11px; font-weight: 700; letter-spacing: 2px; text-transform: uppercase;
      padding: 7px 16px; border-radius: 100px; margin-bottom: 1.5rem;
    }}
    .nl-title {{
      font-family: 'Archivo Black', sans-serif;
      font-size: clamp(28px, 4vw, 42px);
      color: var(--ink); line-height: 1.1; text-transform: uppercase;
      letter-spacing: -1px; margin-bottom: 1rem;
    }}
    .nl-title em {{ color: var(--accent-ink); font-style: normal; }}
    .nl-desc {{ font-size: 15px; color: #777; line-height: 1.75; margin-bottom: 2rem; }}
    .newsletter-form {{ display: flex; flex-direction: column; gap: 12px; }}
    .newsletter-input {{
      padding: 16px 22px; border: 2px solid #F0DED4; border-radius: 100px;
      font-size: 15px; font-family: 'DM Sans', sans-serif;
      color: var(--ink); background: #fff; outline: none;
      transition: border-color 0.2s; width: 100%; box-sizing: border-box;
    }}
    .newsletter-input::placeholder {{ color: #c2ab9f; }}
    .newsletter-input:focus {{ border-color: var(--peach-deep); }}
    .newsletter-btn {{
      background: var(--peach); color: var(--ink);
      font-size: 15px; font-weight: 700; letter-spacing: 0.3px;
      padding: 17px; border-radius: 100px; border: none;
      cursor: pointer; font-family: 'DM Sans', sans-serif;
      transition: all 0.2s;
    }}
    .newsletter-btn:hover {{ background: var(--peach-deep); box-shadow: 0 8px 22px rgba(238,154,120,0.35); }}
    .nl-disclaimer {{ font-size: 11px; color: #c2ab9f; text-align: center; margin-top: 0.75rem; }}

    footer {{
      background: #F7E8E4; border-radius: 32px 32px 0 0;
      padding: 3.5rem 2rem 2.5rem; display: grid;
      grid-template-columns: 2fr 1fr 1fr; gap: 2rem;
      font-size: 13px; margin: 0 1rem;
    }}
    .footer-brand .logo {{ font-size: 14px; letter-spacing: 1.5px; display: block; margin-bottom: 0.75rem; }}
    .footer-brand p {{ font-size: 13px; color: #888; line-height: 1.6; max-width: 280px; }}
    footer h4 {{
      font-size: 10px; letter-spacing: 2px; text-transform: uppercase;
      color: #aaa; margin-bottom: 1rem; font-weight: 500;
    }}
    footer a {{ display: block; color: var(--ink); text-decoration: none; margin-bottom: 8px; transition: color 0.15s; }}
    footer a:hover {{ color: var(--accent-ink); }}
    .footer-bottom {{
      grid-column: 1 / -1; padding-top: 1.5rem;
      border-top: 1px solid #F0D8D3;
      font-size: 12px; color: #aaa;
      display: flex; justify-content: space-between; align-items: center; gap: 1rem; flex-wrap: wrap;
    }}
    .footer-updated {{ font-size: 11px; color: #ccc; margin-top: 4px; }}
    .ig-footer-btn {{ display: inline-flex; align-items: center; gap: 8px; background: var(--peach); color: var(--ink) !important; padding: 9px 18px 9px 12px; border-radius: 100px; font-size: 12px; font-weight: 600; transition: background 0.15s; text-decoration: none; }}
    .ig-footer-btn:hover {{ background: var(--peach-deep); color: var(--ink) !important; }}

    /* Delad sticky Instagram-knapp är marinblå sajtwide — mörk istället på /events. */
    body #ig-sticky-cta {{ background: var(--ink); }}
    body #ig-sticky-cta:hover {{ background: #3A332E; }}

    /* ── Mjuk rörelse ─────────────────────────────────── */
    .hero-blob {{
      position: absolute; border-radius: 50%; pointer-events: none;
      filter: blur(40px); opacity: 0.55; z-index: 0;
    }}
    .hero-blob--a {{ width: 320px; height: 320px; background: #FFC9AE; top: -60px; right: 8%; animation: blobDrift 18s ease-in-out infinite alternate; }}
    .hero-blob--b {{ width: 260px; height: 260px; background: #FFE3CF; bottom: -90px; left: 30%; animation: blobDrift 22s ease-in-out infinite alternate-reverse; }}
    @keyframes blobDrift {{
      0%   {{ transform: translate(0, 0) scale(1); }}
      50%  {{ transform: translate(-30px, 20px) scale(1.08); }}
      100% {{ transform: translate(25px, -15px) scale(0.95); }}
    }}
    .live-dot {{ position: relative; }}
    .live-dot::after {{
      content: ''; position: absolute; inset: 0; border-radius: 50%;
      background: inherit; animation: livePulse 2s ease-out infinite;
    }}
    @keyframes livePulse {{
      0%   {{ transform: scale(1); opacity: 0.6; }}
      100% {{ transform: scale(2.6); opacity: 0; }}
    }}
    html.motion .ev-card {{ opacity: 0; transform: translateY(14px); }}
    html.motion .ev-card.is-in {{
      opacity: 1; transform: none;
      transition: opacity 0.5s ease, transform 0.5s ease, box-shadow 0.25s ease, border-color 0.25s ease;
    }}
    html.motion .ev-card.is-in:has(.ev-link):hover {{ transform: translateY(-3px); }}

    @media (prefers-reduced-motion: reduce) {{
      *, *::before, *::after {{
        animation: none !important; transition: none !important; scroll-behavior: auto !important;
      }}
      .hero-blob {{ display: none; }}
      .fade-in {{ opacity: 1; transform: none; }}
      .ev-card:has(.ev-link):hover {{ transform: none; }}
    }}

    .fade-in {{ opacity: 0; transform: translateY(20px); transition: opacity 0.6s ease, transform 0.6s ease; }}
    .fade-in.visible {{ opacity: 1; transform: translateY(0); }}

    .city-nav {{
      padding: 1.75rem 2rem;
      border-bottom: 1px solid #F0E0DC;
      background: var(--bg);
      display: flex; align-items: center; gap: 1.5rem; flex-wrap: wrap;
    }}
    .city-nav-label {{
      font-size: 11px; letter-spacing: 2px; text-transform: uppercase;
      color: #aaa; font-weight: 500; white-space: nowrap;
    }}
    .city-nav-buttons {{ display: flex; gap: 8px; flex-wrap: wrap; }}
    .city-nav-btn {{
      font-size: 12px; font-weight: 600; padding: 8px 18px;
      border-radius: 100px; border: 1px solid #E8D8D3;
      background: #fff; color: var(--ink); cursor: pointer;
      font-family: 'DM Sans', sans-serif; text-decoration: none;
      transition: all 0.2s; letter-spacing: 0.3px;
      display: inline-flex; align-items: center; gap: 5px;
    }}
    .city-nav-btn:hover {{ border-color: var(--peach-deep); color: var(--accent-ink); }}

    @media (max-width: 768px) {{
      .city-nav {{ padding: 1.25rem; gap: 1rem; flex-direction: column; align-items: flex-start; }}
    }}

    @media (max-width: 768px) {{
      nav {{ padding: 1rem 1.25rem; }}
      .nav-links {{ display: none; }}
      .nav-toggle {{ display: flex; }}
      .page-header {{ padding: 3rem 1.25rem 2.5rem; }}
      .page-header h1 {{ font-size: clamp(32px, 10vw, 52px); }}
      .stats-bar {{ padding: 1rem 1.25rem; gap: 1.25rem; }}
      .stat-divider {{ display: none; }}
      .filters-bar {{ padding: 1rem 1.25rem; }}
      .filter-toggle {{ display: flex; }}
      .filters-inner {{ display: none; flex-direction: column; gap: 1rem; margin-top: 1rem; }}
      .filters-bar.open .filters-inner {{ display: flex; }}
      .filter-group {{ width: 100%; flex-wrap: wrap; }}
      .events-layout {{ padding: 2rem 1.25rem; }}
      .events-grid {{ grid-template-columns: 1fr; }}
      .ev-card {{ min-height: 170px; }}
      .ev-media {{ flex-basis: 32%; }}
      .ev-body {{ padding: 1rem 1.1rem; gap: 6px; }}
      .ev-title {{ font-size: 16px; }}
      .ev-card--highlight {{ flex-direction: column; }}
      .ev-card--highlight .ev-media {{ flex-basis: auto; max-width: none; height: 200px; }}
      .ev-card--highlight .ev-body {{ padding: 1.25rem 1.25rem 1.1rem; }}
      .ev-card--highlight .ev-title {{ font-size: 21px; }}
      footer {{ padding: 2rem 1.25rem; grid-template-columns: 1fr; gap: 1.5rem; margin: 0; border-radius: 24px 24px 0 0; }}
    }}
  </style>
<script id="CookieDeclaration" src="https://consent.cookiebot.com/c82ce3af-bded-4069-9aea-22493d3d7e2d/cd.js" type="text/javascript" async></script>
<script>
  // Kort tonar in när de syns — bara om rörelse är tillåten.
  // Hoppa över i dolda flikar/förhandsvisningar, där observern inte körs förrän sidan visas.
  if ('IntersectionObserver' in window && document.visibilityState === 'visible'
      && !matchMedia('(prefers-reduced-motion: reduce)').matches) {{
    document.documentElement.classList.add('motion');
  }}
</script>
</head>
<body>
<!-- Google Tag Manager (noscript) -->
<noscript><iframe src="https://www.googletagmanager.com/ns.html?id=GTM-TPSCMPZT"
height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>

  <a href="#main-content" class="skip-link">Hoppa till innehåll</a>

  <nav>
    <a href="/" class="run-clubs-logo"><span class="run">RUN</span><span class="clubs">CLUBS</span><span class="suffix">.se</span></a>
    <div class="nav-links">
      <a href="stockholm">Stockholm</a>
      <a href="goteborg">Göteborg</a>
      <a href="ovriga-landet">Övriga landet</a>
      <a href="magazine">Magazine</a>
      <a href="events" class="active">Events</a>
      <a href="loppkalender">Loppkalender</a>
      <a href="om-oss">Om oss</a>
    </div>
    <button class="nav-toggle" aria-label="Öppna meny" aria-expanded="false">
      <span></span><span></span><span></span>
    </button>
  </nav>

  <div class="mobile-menu" role="navigation" aria-label="Mobilmeny">
    <a href="stockholm">Stockholm</a>
    <a href="goteborg">Göteborg</a>
    <a href="ovriga-landet">Övriga landet</a>
    <a href="magazine">Magazine</a>
    <a href="events" class="active">Events</a>
    <a href="loppkalender">Loppkalender</a>
    <a href="om-oss">Om oss</a>
  </div>

  <main id="main-content">

  <header class="page-header">
    <span class="hero-blob hero-blob--a" aria-hidden="true"></span>
    <span class="hero-blob hero-blob--b" aria-hidden="true"></span>
    <div class="page-header-inner">
      <div class="breadcrumb"><a href="/">Start</a> → Running Events</div>
      <div class="page-header-tag">Alla städer</div>
      <h1>Kommande Events och Weekly runs</h1>
      <p>Running events, weekly runs och social runs med run clubs och löpargrupper i Stockholm, Göteborg och övriga landet. Hitta ett pass att springa med den här veckan.</p>
      <div class="live-badge"><span class="live-dot" aria-hidden="true"></span>Direkt från Strava · uppdateras varje dag</div>
    </div>
  </header>

  <div class="stats-bar">
    <div class="stat-item">
      <div>
        <div class="stat-number" id="stat-total">{total_count}</div>
        <div class="stat-label">Events</div>
      </div>
    </div>
    <div class="stat-divider"></div>
    <div class="stat-item">
      <div>
        <div class="stat-number" id="stat-clubs">{club_count}</div>
        <div class="stat-label">Run clubs</div>
      </div>
    </div>
    <div class="stat-divider"></div>
    <div class="stat-item">
      <div>
        <div class="stat-number">⟳</div>
        <div class="stat-label">Uppdateras varje dag</div>
      </div>
    </div>
  </div>

  <div class="city-nav">
    <span class="city-nav-label">Se alla händelser i din stad</span>
    <div class="city-nav-buttons">
      <a href="stockholm-running-events" class="city-nav-btn">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
        Stockholm
      </a>
      <a href="goteborg-running-events" class="city-nav-btn">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
        Göteborg
      </a>
      <a href="ovriga-landet-running-events" class="city-nav-btn">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
        Övriga landet
      </a>
    </div>
  </div>

  <div class="filters-bar" id="filters-bar"></div>

  <div class="events-layout">
    {highlight_section}
    <div class="view-tabs" role="tablist" aria-label="Välj vy">
      <button class="view-tab" role="tab" id="tab-upcoming" data-view="upcoming" aria-selected="true" aria-controls="events-container">Kommande event</button>
      <button class="view-tab" role="tab" id="tab-popular" data-view="popular" aria-selected="false" aria-controls="popular-container" tabindex="-1">Mest klickade</button>
    </div>
    <div id="events-container" role="tabpanel" aria-labelledby="tab-upcoming">
      {events_section}
    </div>
    <div id="popular-container" class="events-grid" role="tabpanel" aria-labelledby="tab-popular" hidden></div>
    <div id="no-events-msg" class="no-events" hidden>
      <span class="no-events-icon">🏃</span>
      <p>Inga events hittades med dessa filter.</p>
    </div>
  </div>

  <section class="nl-section fade-in">
    <div class="nl-body">
      <div class="nl-badge">Prenumerera på <span class="run-clubs-logo"><span class="run">RUN</span><span class="clubs">CLUBS</span><span class="suffix">.se</span></span> veckobrev</div>
      <h2 class="nl-title">Inbjudningar,<br><em>events</em> och<br>promo runs.</h2>
      <p class="nl-desc">Varje söndag får du en sammanställning av vad som händer kommande vecka — veckans pass, nyheter, intervjuer och events. Gratis så klart!</p>
      <form class="newsletter-form" data-placement="page-mid" onsubmit="return false;">
        <input type="email" class="newsletter-input" placeholder="din@email.se" aria-label="E-postadress">
        <button class="newsletter-btn">Anmäl mig nu →</button>
      </form>
      <p class="nl-disclaimer">Gratis. Avsluta när du vill.</p>
    </div>
  </section>

  </main>

  <footer>
    <div class="footer-brand">
      <a href="/" class="run-clubs-logo"><span class="run">RUN</span><span class="clubs">CLUBS</span><span class="suffix">.se</span></a>
      <p>Vi hjälper dig hitta de senaste och trendigaste run clubs och running events i din stad. Just nu i Stockholm, Göteborg och övriga landet.</p>
    </div>
    <div>
      <h4>Städer</h4>
      <a href="stockholm">Stockholm</a>
      <a href="goteborg">Göteborg</a>
      <a href="ovriga-landet">Övriga landet</a>
    </div>
    <div>
      <h4>Om sajten</h4>
      <a href="om-oss">Om oss</a>
      <a href="magazine">Magazine</a>
      <a href="events">Events</a>
      <a href="loppkalender">Loppkalender</a>
      <a href="kontakt">Kontakt</a>
      <a href="samarbeta">Samarbeta</a>
    </div>
    <div class="footer-bottom">
      <span>&copy; 2026 Swedish Run Clubs. Byggd med kärlek av <a href="https://amandahultin.se" target="_blank" rel="noopener noreferrer" style="display:inline; margin:0;">Amanda Hultin <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-left:2px;"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg></a>.<div class="footer-updated">Eventdata uppdaterades {generated_at}.</div></span>
      <a href="https://www.instagram.com/runclubs.se/" target="_blank" rel="noopener" aria-label="Följ oss på Instagram" class="ig-footer-btn">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 100 12.324 6.162 6.162 0 000-12.324zM12 16a4 4 0 110-8 4 4 0 010 8zm6.406-11.845a1.44 1.44 0 100 2.881 1.44 1.44 0 000-2.881z"/></svg>
        Följ oss
      </a>
    </div>
  </footer>

  <script>
    const events = {events_json};

    let activeClubs = new Set();
    let activeWeekdays = new Set();
    const WEEKDAYS = ['Måndag','Tisdag','Onsdag','Torsdag','Fredag','Lördag','Söndag'];
    const WEEKDAY_BY_JS_DAY = ['Söndag','Måndag','Tisdag','Onsdag','Torsdag','Fredag','Lördag'];

    function cardWeekday(card) {{
      const group = card.closest('.date-group');
      const key = group && group.dataset.dateGroup;
      if (!key || key === 'nodate') return null;
      return WEEKDAY_BY_JS_DAY[new Date(key + 'T00:00:00').getDay()];
    }}

    function applyFilters() {{
      const allCards = document.querySelectorAll('#events-container [data-source]');
      let visibleTotal = 0;
      const visibleClubs = new Set();

      allCards.forEach(card => {{
        const club = card.dataset.club || '';
        const weekday = cardWeekday(card);
        const clubShow = activeClubs.size === 0
          || (activeClubs.has('__ovrigt__') && !club)
          || (club && activeClubs.has(club));
        const weekdayShow = activeWeekdays.size === 0
          || (weekday && activeWeekdays.has(weekday));
        const show = clubShow && weekdayShow;
        card.hidden = !show;
        if (show) {{
          visibleTotal++;
          if (club) visibleClubs.add(club);
        }}
      }});

      document.querySelectorAll('.date-group').forEach(group => {{
        const groupCards = group.querySelectorAll('[data-source]');
        let groupVisible = 0;
        groupCards.forEach(c => {{ if (!c.hidden) groupVisible++; }});
        group.hidden = groupVisible === 0;
        const countEl = group.querySelector('[data-count-label]');
        if (countEl) {{
          const key = group.dataset.dateGroup;
          countEl.textContent = key === 'nodate'
            ? groupVisible + ' post' + (groupVisible !== 1 ? 'ar' : '')
            : groupVisible + ' event' + (groupVisible !== 1 ? 's' : '');
        }}
      }});

      const noEventsMsg = document.getElementById('no-events-msg');
      if (noEventsMsg) noEventsMsg.hidden = visibleTotal > 0;

      if (activeView === 'popular') buildPopularList();

      document.getElementById('stat-total').textContent = visibleTotal;
      document.getElementById('stat-clubs').textContent = visibleClubs.size;
    }}

    const navToggle  = document.querySelector('.nav-toggle');
    const mobileMenu = document.querySelector('.mobile-menu');
    navToggle.addEventListener('click', function() {{
      const isOpen = mobileMenu.classList.toggle('open');
      navToggle.classList.toggle('open');
      navToggle.setAttribute('aria-expanded', isOpen);
      navToggle.setAttribute('aria-label', isOpen ? 'Stäng meny' : 'Öppna meny');
    }});

    function renderFilters() {{
      const clubs = [...new Set(events.map(ev => ev.club || '').filter(Boolean))]
        .sort((a, b) => a.localeCompare(b, 'sv'));
      const hasOvrigt = events.some(ev => !ev.club);
      const bar = document.getElementById('filters-bar');
      if (!bar) return;

      let weekdayPillsHtml = `<button class="filter-pill active" data-filter="weekday" data-value="all">Alla</button>`;
      WEEKDAYS.forEach(day => {{
        weekdayPillsHtml += `<button class="filter-pill" data-filter="weekday" data-value="${{day}}">${{day}}</button>`;
      }});

      let pillsHtml = `<button class="filter-pill active" data-filter="club" data-value="all">Alla</button>`;
      clubs.forEach(club => {{
        pillsHtml += `<button class="filter-pill" data-filter="club" data-value="${{club.replace(/&/g,'&amp;').replace(/"/g,'&quot;')}}">${{club.replace(/&/g,'&amp;')}}</button>`;
      }});
      if (hasOvrigt) pillsHtml += `<button class="filter-pill" data-filter="club" data-value="__ovrigt__">Övrigt</button>`;

      bar.innerHTML = `
        <button class="filter-toggle" id="filter-toggle" aria-expanded="false" aria-controls="filters-inner">
          <span class="filter-toggle-label">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>
            Filtrera
          </span>
          <svg class="filter-toggle-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
        </button>
        <div class="filters-inner" id="filters-inner">
          <div class="filter-group"><span class="filter-label">Veckodag</span>${{weekdayPillsHtml}}</div>
          <div class="filter-group"><span class="filter-label">Klubb</span>${{pillsHtml}}</div>
          <button class="close-filters" id="close-filters">Stäng</button>
        </div>`;

      bar.querySelectorAll('[data-filter="weekday"]').forEach(btn => {{
        btn.addEventListener('click', function() {{
          const val = this.dataset.value;
          if (val === 'all') {{
            activeWeekdays.clear();
            bar.querySelectorAll('[data-filter="weekday"]').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
          }} else {{
            bar.querySelector('[data-filter="weekday"][data-value="all"]').classList.remove('active');
            if (activeWeekdays.has(val)) {{
              activeWeekdays.delete(val);
              this.classList.remove('active');
            }} else {{
              activeWeekdays.add(val);
              this.classList.add('active');
            }}
            if (activeWeekdays.size === 0) {{
              bar.querySelector('[data-filter="weekday"][data-value="all"]').classList.add('active');
            }}
          }}
          syncURL();
          applyFilters();
        }});
      }});

      bar.querySelectorAll('[data-filter="club"]').forEach(btn => {{
        btn.addEventListener('click', function() {{
          const val = this.dataset.value;
          if (val === 'all') {{
            activeClubs.clear();
            bar.querySelectorAll('[data-filter="club"]').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
          }} else {{
            bar.querySelector('[data-filter="club"][data-value="all"]').classList.remove('active');
            if (activeClubs.has(val)) {{
              activeClubs.delete(val);
              this.classList.remove('active');
            }} else {{
              activeClubs.add(val);
              this.classList.add('active');
            }}
            if (activeClubs.size === 0) {{
              bar.querySelector('[data-filter="club"][data-value="all"]').classList.add('active');
            }}
          }}
          syncURL();
          applyFilters();
        }});
      }});

      const filterToggle = document.getElementById('filter-toggle');
      if (filterToggle) {{
        filterToggle.addEventListener('click', () => {{
          const isOpen = bar.classList.toggle('open');
          filterToggle.setAttribute('aria-expanded', isOpen);
        }});
      }}
      const closeBtn = document.getElementById('close-filters');
      if (closeBtn) {{
        closeBtn.addEventListener('click', () => {{
          bar.classList.remove('open');
          if (filterToggle) filterToggle.setAttribute('aria-expanded', 'false');
        }});
      }}
    }}

    const upcomingContainer = document.getElementById('events-container');
    const popularContainer  = document.getElementById('popular-container');
    const viewTabs = [...document.querySelectorAll('.view-tab')];
    let activeView = 'upcoming';

    function popularityScore(card) {{
      // TODO: koppla popularitet (steg 14) — gillningar + klick per event.
      // Tills vidare får alla samma poäng, så listan faller tillbaka på datumordning.
      return 0;
    }}

    function buildPopularList() {{
      const cards = [...upcomingContainer.querySelectorAll('[data-source]')];
      const ranked = cards
        .map((card, i) => ({{ card, i, score: popularityScore(card) }}))
        .sort((a, b) => b.score - a.score || a.i - b.i);
      popularContainer.replaceChildren(...ranked.map(({{ card }}) => {{
        const clone = card.cloneNode(true);
        clone.hidden = card.hidden;
        clone.classList.add('is-in');
        return clone;
      }}));
    }}

    function setView(view) {{
      activeView = view === 'popular' ? 'popular' : 'upcoming';
      viewTabs.forEach(tab => {{
        const selected = tab.dataset.view === activeView;
        tab.setAttribute('aria-selected', selected);
        tab.tabIndex = selected ? 0 : -1;
      }});
      upcomingContainer.hidden = activeView !== 'upcoming';
      popularContainer.hidden  = activeView !== 'popular';
      if (activeView === 'popular') buildPopularList();
      else popularContainer.replaceChildren();
    }}

    viewTabs.forEach((tab, i) => {{
      tab.addEventListener('click', () => {{
        setView(tab.dataset.view);
        syncURL();
      }});
      tab.addEventListener('keydown', e => {{
        if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
        const next = viewTabs[(i + (e.key === 'ArrowRight' ? 1 : -1) + viewTabs.length) % viewTabs.length];
        next.focus();
        next.click();
      }});
    }});

    function syncURL() {{
      const params = new URLSearchParams();
      if (activeView === 'popular') params.set('view', 'popular');
      activeWeekdays.forEach(d => params.append('weekday', d));
      activeClubs.forEach(c => params.append('club', c));
      const qs = params.toString();
      history.replaceState(null, '', (qs ? '?' + qs : location.pathname) + location.hash);
    }}

    if (document.documentElement.classList.contains('motion')) {{
      const cardObserver = new IntersectionObserver(entries => {{
        entries.forEach(e => {{
          if (!e.isIntersecting) return;
          e.target.classList.add('is-in');
          cardObserver.unobserve(e.target);
        }});
      }}, {{ rootMargin: '0px 0px -40px 0px' }});
      document.querySelectorAll('.ev-card').forEach(c => cardObserver.observe(c));
    }}

    document.addEventListener('click', e => {{
      const btn = e.target.closest('.ev-like');
      if (!btn) return;
      // TODO steg 15: spara gillningen mot endpointen.
      btn.setAttribute('aria-pressed', btn.getAttribute('aria-pressed') !== 'true');
      btn.classList.remove('pop');
      void btn.offsetWidth;
      btn.classList.add('pop');
    }});

    let toastTimer;
    function showToast(text) {{
      let toast = document.getElementById('toast');
      if (!toast) {{
        toast = document.createElement('div');
        toast.id = 'toast';
        toast.className = 'toast';
        toast.setAttribute('role', 'status');
        toast.setAttribute('aria-live', 'polite');
        document.body.appendChild(toast);
      }}
      toast.textContent = text;
      toast.classList.add('show');
      clearTimeout(toastTimer);
      toastTimer = setTimeout(() => toast.classList.remove('show'), 2400);
    }}

    async function copyText(text) {{
      try {{
        await navigator.clipboard.writeText(text);
        return true;
      }} catch (_) {{
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.setAttribute('readonly', '');
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        let ok = false;
        try {{ ok = document.execCommand('copy'); }} catch (_) {{}}
        ta.remove();
        return ok;
      }}
    }}

    // Mobil: systemets delningsmeny. Desktop: kopiera länken.
    const useNativeShare = !!navigator.share && matchMedia('(pointer: coarse)').matches;
    document.addEventListener('click', async e => {{
      const btn = e.target.closest('.ev-share');
      if (!btn) return;
      const url = btn.dataset.url;
      if (useNativeShare) {{
        try {{ await navigator.share({{ title: btn.dataset.title, url }}); }} catch (_) {{}}
        return;
      }}
      showToast(await copyText(url) ? 'Länken är kopierad ✓' : url);
    }});

    function focusSharedEvent() {{
      const m = location.hash.match(/^#ev-([0-9a-f]{{10}})$/);
      if (!m) return;
      const card = document.getElementById('ev-' + m[1]);
      if (!card) {{
        showToast('Det här eventet har redan varit');
        return;
      }}
      if (card.hidden || activeView !== 'upcoming') {{
        // Visa kortet även om ett filter eller en annan vy dolde det.
        activeClubs.clear();
        activeWeekdays.clear();
        setView('upcoming');
        renderFilters();
        applyFilters();
        syncURL();
      }}
      card.classList.add('is-in', 'is-target');
      const scrollToCard = () => card.scrollIntoView({{ block: 'center', behavior: 'instant' }});
      scrollToCard();
      // Typsnitt och bilder kan flytta layouten — scrolla om när sidan har laddat klart.
      if (document.readyState !== 'complete') window.addEventListener('load', scrollToCard, {{ once: true }});
      setTimeout(() => card.classList.remove('is-target'), 4000);
    }}
    window.addEventListener('hashchange', focusSharedEvent);

    const observer = new IntersectionObserver(entries => {{
      entries.forEach(e => {{ if (e.isIntersecting) e.target.classList.add('visible'); }});
    }}, {{ threshold: 0 }});
    document.querySelectorAll('.fade-in').forEach(el => observer.observe(el));

    const _weekdayParams = new URLSearchParams(window.location.search).getAll('weekday');
    _weekdayParams.forEach(d => activeWeekdays.add(d));
    const _clubParams = new URLSearchParams(window.location.search).getAll('club');
    _clubParams.forEach(c => activeClubs.add(c));

    setView(new URLSearchParams(window.location.search).get('view'));
    renderFilters();
    applyFilters();

    if (_weekdayParams.length > 0) {{
      const allWeekdayPill = document.querySelector('[data-filter="weekday"][data-value="all"]');
      if (allWeekdayPill) allWeekdayPill.classList.remove('active');
      _weekdayParams.forEach(d => {{
        const targetPill = document.querySelector(`[data-filter="weekday"][data-value="${{d}}"]`);
        if (targetPill) targetPill.classList.add('active');
      }});
    }}
    if (_clubParams.length > 0) {{
      const allPill = document.querySelector('[data-filter="club"][data-value="all"]');
      if (allPill) allPill.classList.remove('active');
      _clubParams.forEach(c => {{
        const targetPill = document.querySelector(`[data-filter="club"][data-value="${{c}}"]`);
        if (targetPill) targetPill.classList.add('active');
      }});
    }}
    focusSharedEvent();
  </script>
  <script src="/sticky-instagram-cta.js" defer></script>
  <script src="newsletter.js"></script>
</body>
</html>
"""


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("events.html")
    sheet_id = os.environ.get("GOOGLE_SHEET_ID") or EVENTS_SHEET_ID

    weekly_records  = fetch_weekly_runs(sheet_id)
    club_pages      = build_club_pages(weekly_records)
    club_cities     = build_club_cities(weekly_records)
    overrides       = fetch_overrides(sheet_id)
    weekly_events   = expand_weekly_runs(weekly_records, overrides)

    records       = fetch_events(sheet_id)
    events        = prepare_events(records, club_pages, club_cities)

    special_records = fetch_special_events(sheet_id)
    special_events  = prepare_special_events(special_records, club_pages)

    all_events = events + weekly_events + special_events
    all_events = drop_duplicate_cards(all_events)
    all_events.sort(key=lambda x: (x["date"] or "9999", x["club"]))
    log.info("%d total events after merge", len(all_events))

    generated_at = sv_long_date(datetime.now(timezone.utc))
    html_out = render_html(all_events, generated_at)

    out_path.write_text(html_out, encoding="utf-8")
    log.info("Wrote %s (%d events)", out_path, len(events))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
