"""generate_homepage_events.py

Patches index.html with:
  1. window.__EVENTS__ = [...] — the full events JSON, so the JS never
     needs to fetch running-events.html (faster, works without JS for crawlers).
  2. Static HTML cards for today's events inside <!-- EVENTS-START/END -->
     so Googlebot sees real content in the initial HTML even if it skips JS.

Run after generate_running_events.py (which produces running-events.html):
    python generate_homepage_events.py

The script is idempotent: safe to run multiple times.
"""

from __future__ import annotations

import html as html_module
import json
import logging
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

STOCKHOLM = ZoneInfo("Europe/Stockholm")
ROOT = Path(__file__).parent

SV_DAYS   = ["Söndag", "Måndag", "Tisdag", "Onsdag", "Torsdag", "Fredag", "Lördag"]
SV_MONTHS = ["januari","februari","mars","april","maj","juni",
             "juli","augusti","september","oktober","november","december"]
CITY_CLASS = {"Stockholm": "tag-sthlm", "Göteborg": "tag-gbg", "Malmö": "tag-malm"}


# ── Extract events from running-events.html ──────────────────────────────────

def load_events(running_events_path: Path) -> list[dict]:
    text = running_events_path.read_text(encoding="utf-8")
    m = re.search(r"const events = (\[[\s\S]*?\]);", text)
    if not m:
        raise ValueError("Could not find 'const events = [...]' in running-events.html")
    events = json.loads(m.group(1))
    log.info("Loaded %d events from running-events.html", len(events))
    return events


# ── Build static HTML cards for today ────────────────────────────────────────

def render_cards(events: list[dict]) -> str:
    now_sthlm  = datetime.now(STOCKHOLM)
    today      = now_sthlm.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end  = today + timedelta(days=1)

    today_events = [
        ev for ev in events
        if ev.get("date") and _in_range(ev["date"], today, today_end)
    ]
    today_events.sort(key=lambda ev: ev["date"])

    day_label = SV_DAYS[today.weekday()] if False else SV_DAYS[today.isoweekday() % 7]
    date_label = f"{day_label} {today.day} {SV_MONTHS[today.month - 1]}"

    if not today_events:
        return (
            f'<div class="schedule-empty" data-seo-date="{today.date()}">'
            f'Inga events {date_label} — välj en annan dag!</div>'
        )

    cards = []
    for ev in today_events:
        d          = datetime.fromisoformat(ev["date"])
        day_str    = SV_DAYS[d.isoweekday() % 7][:3].upper()
        date_num   = d.day
        loc        = (ev.get("location") or "").split(",")[0].strip()
        title_raw  = ev.get("title") or ""
        title      = (title_raw[:38] + "…") if len(title_raw) > 40 else title_raw
        club       = html_module.escape(ev.get("club") or "")
        title_esc  = html_module.escape(title)
        loc_esc    = html_module.escape(loc)
        club_page  = (ev.get("club_page") or "").replace("https://runclubs.se/", "")
        href       = club_page or f"running-events?club={html_module.escape(ev.get('club') or '')}"
        city       = ev.get("city") or ""
        city_cls   = CITY_CLASS.get(city, "")
        city_pill  = f'<span class="pass-city-tag {city_cls}">{html_module.escape(city)}</span>' if city_cls else ""

        loc_html = f'<div class="event-teaser-loc">{loc_esc}</div>' if loc_esc else ""
        cards.append(
            f'<a href="{href}" class="event-teaser-card">'
            f'<div class="event-teaser-time no-time" style="line-height:1.1;">{day_str}<br>{date_num}</div>'
            f'<div class="event-teaser-info">'
            f'<div class="event-teaser-club">{club}{city_pill}</div>'
            f'<div class="event-teaser-name">{title_esc}</div>'
            f'{loc_html}'
            f'<span class="event-teaser-link">Läs mer →</span>'
            f'</div></a>'
        )

    log.info("Rendered %d cards for %s", len(cards), date_label)
    return "\n      ".join(cards)


def _in_range(date_str: str, start: datetime, end: datetime) -> bool:
    try:
        d = datetime.fromisoformat(date_str)
        # Make timezone-aware if naive (treat as Stockholm local)
        if d.tzinfo is None:
            d = d.replace(tzinfo=STOCKHOLM)
        return start <= d < end
    except ValueError:
        return False


# ── Patch index.html ─────────────────────────────────────────────────────────

def patch_index(index_path: Path, events: list[dict], cards_html: str) -> None:
    original = index_path.read_text(encoding="utf-8")
    patched  = original

    # 1. Inline the full events JSON for the JS (replaces placeholder comment block)
    events_json = json.dumps(events, ensure_ascii=False, separators=(",", ":"))
    json_inject = f"window.__EVENTS__ = {events_json};"
    patched = re.sub(
        r"// EVENTS-JSON-START.*?// EVENTS-JSON-END",
        f"// EVENTS-JSON-START\n    {json_inject}\n    // EVENTS-JSON-END",
        patched,
        flags=re.DOTALL,
    )

    # 2. Inject static cards between EVENTS-START / EVENTS-END
    patched = re.sub(
        r"<!-- EVENTS-START -->.*?<!-- EVENTS-END -->",
        f"<!-- EVENTS-START -->{cards_html}<!-- EVENTS-END -->",
        patched,
        flags=re.DOTALL,
    )

    if patched == original:
        log.warning("index.html unchanged — markers may be missing")
    else:
        index_path.write_text(patched, encoding="utf-8")
        log.info("✓ index.html patched")


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    running_events = ROOT / "running-events.html"
    index          = ROOT / "index.html"

    if not running_events.exists():
        log.error("running-events.html not found — run generate_running_events.py first")
        sys.exit(1)

    events    = load_events(running_events)
    cards_html = render_cards(events)
    patch_index(index, events, cards_html)


if __name__ == "__main__":
    main()
