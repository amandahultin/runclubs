"""Render Instagram-ready images for next week's Stockholm Strava events.

Reads the Events worksheet (the same sheet the site's event pages read from),
filters to Strava-sourced events in Stockholm happening in the target week,
and renders one branded PNG per event in two sizes:

  - <slug>-post.png   1080x1350  (Instagram feed post, 4:5)
  - <slug>-story.png  1080x1920  (Instagram story / reel cover, 9:16)

Optionally uploads both files per event to a Google Drive folder.

Usage:
    python generate_instagram_event_images.py --out-dir instagram/generated
    python generate_instagram_event_images.py --out-dir instagram/generated --upload
    python generate_instagram_event_images.py --week-start 2026-07-27 --out-dir /tmp/preview

Env (only required with --upload, or always for the sheet fetch):
    GOOGLE_SERVICE_ACCOUNT_JSON   service account JSON (same one used elsewhere in this repo)
    EVENTS_SHEET_ID               defaults to events_common.EVENTS_SHEET_ID if unset
    INSTAGRAM_DRIVE_FOLDER_ID     required with --upload

Templates live under instagram/components/ (reusable pieces: tokens, logo,
city pill, date block, location line) and instagram/templates/ (the two
formats below, which compose those pieces). Edit those .html files to
change the look — this script only supplies data and does the rendering.
The same files are synced to a Claude Design project for visual browsing;
see the design-sync tooling docs for how to push updates there.

Dependencies: playwright (chromium), gspread, google-api-python-client (for --upload), jinja2.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from events_common import (
    EVENTS_SHEET_ID,
    _SV_DAYS,
    _SV_MONTHS_SHORT,
    _parse_date,
    fetch_events,
    normalize_club_name,
)

log = logging.getLogger(__name__)

STOCKHOLM_KEYWORDS = {"stockholm"}

INSTAGRAM_DIR = Path(__file__).resolve().parent / "instagram"
_JINJA_ENV = Environment(
    loader=FileSystemLoader(str(INSTAGRAM_DIR)),
    autoescape=select_autoescape(["html"]),
)

# Title-size tiering scale per output format — matches instagram/templates/event-*.html.
VARIANT_SCALE = {"post": 1.0, "story": 1.3}

_DIMS_RE = re.compile(r'data-width="(\d+)"\s+data-height="(\d+)"')


def _title_font_size(title: str, scale: float) -> int:
    n = len(title)
    if n <= 28:
        base = 82
    elif n <= 45:
        base = 66
    elif n <= 65:
        base = 52
    else:
        base = 42
    return round(base * scale)


def _slugify(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return text or "event"


def event_page_html(ev: dict, variant: str) -> str:
    d: datetime = ev["_dt"]
    js_day = (d.weekday() + 1) % 7  # Python Mon=0..Sun=6 -> Sun=0..Sat=6
    scale = VARIANT_SCALE[variant]

    tpl = _JINJA_ENV.get_template(f"templates/event-{variant}.html")
    return tpl.render(
        city="Stockholm",
        day=d.day,
        day_name=_SV_DAYS[js_day].upper(),
        month=_SV_MONTHS_SHORT[d.month - 1].upper(),
        club=ev["club"],
        title=ev["title"],
        location=ev["location"],
        title_size=_title_font_size(ev["title"], scale),
    )


async def render_event(ev: dict, out_dir: Path) -> list[Path]:
    from playwright.async_api import async_playwright

    slug = f"{ev['_dt'].strftime('%Y-%m-%d')}-{_slugify(ev['club'])}-{_slugify(ev['title'])[:40]}"
    paths: list[Path] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            for variant in VARIANT_SCALE:
                html = event_page_html(ev, variant)
                match = _DIMS_RE.search(html)
                if not match:
                    raise ValueError(f"templates/event-{variant}.html is missing data-width/data-height")
                width, height = int(match.group(1)), int(match.group(2))

                html_path = out_dir / f"{slug}-{variant}.html"
                html_path.write_text(html, encoding="utf-8")
                png_path = out_dir / f"{slug}-{variant}.png"

                ctx = await browser.new_context(
                    viewport={"width": width, "height": height}, device_scale_factor=1
                )
                page = await ctx.new_page()
                await page.goto(f"file://{html_path}")
                await page.evaluate("document.fonts.ready")
                await page.wait_for_timeout(400)
                await page.screenshot(
                    path=str(png_path),
                    clip={"x": 0, "y": 0, "width": width, "height": height},
                )
                await ctx.close()
                html_path.unlink(missing_ok=True)
                paths.append(png_path)
        finally:
            await browser.close()

    return paths


def week_window(week_start: str | None) -> tuple[datetime, datetime]:
    """Return (monday_00:00, next_monday_00:00) in UTC for the target week.

    Defaults to the coming Mon-Sun (i.e. running this on a Sunday picks the
    week that starts the next day).
    """
    if week_start:
        start = datetime.strptime(week_start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        today = datetime.now(timezone.utc)
        days_ahead = (7 - today.weekday()) % 7  # days until next Monday
        days_ahead = days_ahead or 7
        start = (today + timedelta(days=days_ahead)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    return start, start + timedelta(days=7)


def gather_events(sheet_id: str, week_start: str | None) -> list[dict]:
    start, end = week_window(week_start)
    log.info("Target week: %s -> %s (UTC)", start.date(), end.date())

    records = fetch_events(sheet_id)
    events: list[dict] = []
    seen: set[tuple] = set()

    for r in records:
        source = (r.get("source") or "").strip().lower()
        if source != "strava":
            continue

        loc = (r.get("location") or "").lower()
        if not any(kw in loc for kw in STOCKHOLM_KEYWORDS):
            continue

        dt = _parse_date((r.get("date") or "").strip())
        if dt is None:
            continue
        dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        if not (start <= dt < end):
            continue

        club = normalize_club_name(r.get("club") or "")
        title = (r.get("title") or "Untitled").strip()
        key = (club, dt.isoformat(), title)
        if key in seen:
            continue
        seen.add(key)

        events.append({
            "club": club,
            "title": title,
            "location": (r.get("location") or "").strip(),
            "_dt": dt,
        })

    events.sort(key=lambda e: e["_dt"])
    log.info("%d Stockholm Strava events in target week", len(events))
    return events


def upload_to_drive(paths: list[Path], folder_id: str) -> None:
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = Credentials.from_service_account_info(
        json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]),
        scopes=["https://www.googleapis.com/auth/drive"],
    )
    drive = build("drive", "v3", credentials=creds)

    for path in paths:
        media = MediaFileUpload(str(path), mimetype="image/png", resumable=False)
        drive.files().create(
            body={"name": path.name, "parents": [folder_id]},
            media_body=media,
            fields="id",
            supportsAllDrives=True,
        ).execute()
        log.info("Uploaded %s to Drive folder %s", path.name, folder_id)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", default="instagram/generated", help="Local output directory")
    ap.add_argument("--week-start", default=None, help="Override target week's Monday, YYYY-MM-DD")
    ap.add_argument("--upload", action="store_true", help="Upload generated PNGs to Google Drive")
    ap.add_argument("--sheet-id", default=os.environ.get("EVENTS_SHEET_ID") or EVENTS_SHEET_ID)
    args = ap.parse_args()

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    events = gather_events(args.sheet_id, args.week_start)
    if not events:
        log.info("No matching events — nothing to render")
        return

    all_paths: list[Path] = []
    for ev in events:
        paths = asyncio.run(render_event(ev, out_dir))
        log.info("Rendered %s (%s)", ev["title"], ", ".join(p.name for p in paths))
        all_paths.extend(paths)

    if args.upload:
        folder_id = os.environ.get("INSTAGRAM_DRIVE_FOLDER_ID")
        if not folder_id:
            sys.exit("INSTAGRAM_DRIVE_FOLDER_ID must be set to use --upload")
        upload_to_drive(all_paths, folder_id)


if __name__ == "__main__":
    main()
