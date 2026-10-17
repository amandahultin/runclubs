"""Generate goteborg-running-events.html from the running-clubs events Google Sheet.

Reads from two worksheets:
  - Events       populated by mikaelsto/runclubs-events-feed (Strava)
  - WeeklyRuns   manually maintained recurring club runs

Filters to Göteborg/Gothenburg, expands weekly runs for the next LOOKAHEAD_DAYS days,
merges both lists, and renders a self-contained HTML page.

Usage:
    python generate_goteborg_events.py                    # writes goteborg-running-events.html
    python generate_goteborg_events.py path/to/out.html   # custom output path
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from events_common import (
    CITY_GOTEBORG,
    DAYS_MAP,
    EVENTS_SHEET_ID,
    LOOKAHEAD_DAYS,
    _normalize_city,
    build_club_cities,
    combine_date_time,
    drop_duplicate_cards,
    fetch_events,
    fetch_overrides,
    fetch_special_events,
    fetch_weekly_runs,
    normalize_club_name,
    resolve_city,
    sv_long_date,
    _parse_date,
    _parse_time,
)

log = logging.getLogger(__name__)


def prepare_special_events(records: list[dict]) -> list[dict]:
    today = datetime.now(timezone.utc).date()
    events: list[dict] = []

    for r in records:
        if _normalize_city(r.get("city") or "") != CITY_GOTEBORG:
            continue

        raw_date = (r.get("date") or "").strip()
        raw_time = (r.get("time") or "").strip()

        raw_date = combine_date_time(raw_date, raw_time)
        dt = _parse_date(raw_date)
        if dt is not None and dt.date() < today:
            continue

        events.append({
            "type":        "event",
            "source":      "special",
            "club":        normalize_club_name(r.get("club") or ""),
            "title":       (r.get("title") or "Untitled").strip(),
            "date":        dt.strftime("%Y-%m-%dT%H:%M:%S") if dt else "",
            "location":    (r.get("location") or "").strip(),
            "description": (r.get("description") or "").strip(),
            "link":        (r.get("link") or "").strip(),
            "image_url":   (r.get("image_url") or "").strip(),
            "engagement":  "",
        })

    log.info("%d Göteborg special events after filtering", len(events))
    return events


def prepare_events(records: list[dict], club_cities: dict[str, str] | None = None) -> list[dict]:
    today = datetime.now(timezone.utc).date()
    events: list[dict] = []

    for r in records:
        city = resolve_city(r.get("location") or "", r.get("club") or "", club_cities, r.get("title") or "")
        if city != CITY_GOTEBORG:
            continue

        raw_date = (r.get("date") or "").strip()
        dt = _parse_date(raw_date)
        if dt is not None and dt.date() < today:
            continue

        events.append({
            "type":        "event",
            "source":      (r.get("source") or "").strip().lower(),
            "club":        normalize_club_name(r.get("club") or ""),
            "title":       (r.get("title") or "Untitled").strip(),
            "date":        dt.strftime("%Y-%m-%dT%H:%M:%S") if dt else "",
            "location":    (r.get("location") or "").strip(),
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
    log.info("%d Göteborg upcoming events after filtering", len(unique))
    return unique


def expand_weekly_runs(
    records: list[dict],
    overrides: dict[tuple[str, str], dict],
) -> list[dict]:
    today = datetime.now(timezone.utc).date()
    cutoff = today + timedelta(days=LOOKAHEAD_DAYS)
    events: list[dict] = []

    for r in records:
        if _normalize_city(r.get("city") or "") != CITY_GOTEBORG:
            continue

        day_str = (r.get("day_of_week") or "").lower().strip()
        target_weekday = DAYS_MAP.get(day_str)
        if target_weekday is None:
            log.warning("Unknown day_of_week %r for club %r — skipping", day_str, r.get("club"))
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
                    events.append({
                        "type":        "weekly_run",
                        "source":      "weekly_run",
                        "club":        club,
                        "title":       (override.get("title") or r.get("title") or "").strip(),
                        "date":        dt.strftime("%Y-%m-%dT%H:%M:%S"),
                        "location":    (override.get("location") or r.get("location") or "").strip(),
                        "description": (override.get("description") or r.get("description") or "").strip(),
                        "link":        (override.get("link") or r.get("link") or "").strip(),
                        "image_url":   "",
                        "engagement":  "",
                    })
                    log.info("Override applied: %s on %s", club, date_key)
                else:
                    dt = datetime(current.year, current.month, current.day, hour, minute)
                    events.append({
                        "type":        "weekly_run",
                        "source":      "weekly_run",
                        "club":        club,
                        "title":       (r.get("title") or "").strip(),
                        "date":        dt.strftime("%Y-%m-%dT%H:%M:%S"),
                        "location":    (r.get("location") or "").strip(),
                        "description": (r.get("description") or "").strip(),
                        "link":        (r.get("link") or "").strip(),
                        "image_url":   "",
                        "engagement":  "",
                    })

            current += timedelta(days=1)

    log.info("%d Göteborg weekly run occurrences expanded (next %d days)", len(events), LOOKAHEAD_DAYS)
    return events


CITY_PAGE = {
    "path": "goteborg-running-events",
    "title": "Göteborgs Löparevent — Swedish Run Clubs",
    "description": "Kommande grupplöpningar och events från Göteborgs run clubs — Strava-events och veckoliga grupplöpningar.",
    "og_title": "Göteborgs Löparevent — Swedish Run Clubs",
    "og_description": "Kommande grupplöpningar och events från Göteborgs run clubs.",
    "og_image": "https://runclubs.se/goteborg-run-clubs.jpeg",
    "breadcrumb": '<a href="/">Start</a> → <a href="/events">Events</a> → Göteborg',
    "tag": "Göteborgs run clubs",
    "h1": "Kommande Events och Weekly runs i Göteborg",
    "intro": "Här visas alla kommande running events från Strava och weekly runs från löpargrupper, run clubs, communions och run crews i Göteborg.",
    "city_nav_label": "Se händelser i annan stad",
}


def render_html(events: list[dict], generated_at: str) -> str:
    """Göteborg: same template and cards as /events, with its own SEO texts."""
    from generate_running_events import render_html as render_events_page
    return render_events_page(events, generated_at, page=CITY_PAGE)


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("goteborg-running-events.html")
    sheet_id = os.environ.get("GOOGLE_SHEET_ID") or EVENTS_SHEET_ID

    weekly_records  = fetch_weekly_runs(sheet_id)
    club_cities     = build_club_cities(weekly_records)
    overrides       = fetch_overrides(sheet_id)
    weekly_events   = expand_weekly_runs(weekly_records, overrides)

    records       = fetch_events(sheet_id)
    events        = prepare_events(records, club_cities)

    special_records = fetch_special_events(sheet_id)
    special_events  = prepare_special_events(special_records)

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
