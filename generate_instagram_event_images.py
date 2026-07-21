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

Dependencies: playwright (chromium), gspread, google-api-python-client (for --upload).
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

from events_common import (
    EVENTS_SHEET_ID,
    _SV_DAYS,
    _SV_MONTHS_SHORT,
    _PIN_SVG,
    _e,
    _parse_date,
    fetch_events,
    normalize_club_name,
)

log = logging.getLogger(__name__)

STOCKHOLM_KEYWORDS = {"stockholm"}

CITY_PILL_BG, CITY_PILL_FG = "#C6EFCE", "#276221"  # Stockholm pill colors (see brand-tokens.md)

# Fonts loaded via Google Fonts so this matches runclubs.se exactly.
_HEAD = """
<meta charset='utf-8'>
<link rel='preconnect' href='https://fonts.googleapis.com'>
<link rel='preconnect' href='https://fonts.gstatic.com' crossorigin>
<link href='https://fonts.googleapis.com/css2?family=Archivo+Black&family=Inter:ital,wght@1,900&family=Oswald:wght@500;600;700&family=DM+Sans:wght@400;500;600;700&family=Playfair+Display:wght@400&display=swap' rel='stylesheet'>
"""

_LOGO = (
    '<span class="logo"><span class="run">RUN</span><span class="clubs">CLUBS</span>'
    '<span class="suffix">.se</span></span>'
)

VARIANTS = {
    "post": {
        "w": 1080, "h": 1350, "pad": 72, "date_num": 120, "footer_pad": 34,
        "scale": 1.0, "gap": 26, "blob": 480,
    },
    "story": {
        "w": 1080, "h": 1920, "pad": 84, "date_num": 190, "footer_pad": 50,
        "scale": 1.3, "gap": 38, "blob": 640,
    },
}


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
    v = VARIANTS[variant]
    d: datetime = ev["_dt"]
    js_day = (d.weekday() + 1) % 7  # Python Mon=0..Sun=6 -> Sun=0..Sat=6
    day_name = _SV_DAYS[js_day].upper()
    month = _SV_MONTHS_SHORT[d.month - 1].upper()
    s = v["scale"]
    title_size = _title_font_size(ev["title"], s)
    club, title, location = _e(ev["club"]), _e(ev["title"]), _e(ev["location"])

    return f"""<!doctype html><html><head>{_HEAD}
<style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  html,body{{width:{v['w']}px;height:{v['h']}px;overflow:hidden;font-family:'DM Sans',sans-serif;color:#1C2A45;background:#FDFAF9}}
  .poster{{position:relative;width:{v['w']}px;height:{v['h']}px;padding:{v['pad']}px;display:flex;flex-direction:column}}
  .blob{{position:absolute;top:-{v['blob']*0.35:.0f}px;right:-{v['blob']*0.35:.0f}px;width:{v['blob']}px;height:{v['blob']}px;border-radius:50%;background:radial-gradient(circle at 35% 35%, #F7E3DD 0%, #FDFAF9 72%);z-index:0}}
  .top-bar,.content,.footer{{position:relative;z-index:1}}
  .top-bar{{display:flex;justify-content:space-between;align-items:center}}
  .logo{{display:inline-flex;align-items:baseline;color:#1a1a1a;text-decoration:none;font-size:34px}}
  .logo .run{{font-family:'Inter',sans-serif;font-weight:900;font-style:italic;letter-spacing:-0.04em;padding-right:2px}}
  .logo .clubs{{font-family:'Playfair Display',serif;font-weight:400;letter-spacing:-0.02em}}
  .logo .suffix{{font-family:'Playfair Display',serif;font-size:0.45em;font-weight:400;text-transform:lowercase;margin-left:2px}}
  .logo.small{{font-size:24px}}
  .city-pill{{display:inline-block;font-size:16px;font-weight:700;letter-spacing:1.6px;text-transform:uppercase;padding:8px 18px;border-radius:100px;background:{CITY_PILL_BG};color:{CITY_PILL_FG}}}
  .content{{flex:1;display:flex;flex-direction:column;justify-content:center;gap:{v['gap']}px}}
  .kicker{{font-size:{round(20*s)}px;letter-spacing:5px;text-transform:uppercase;color:#D4715E;font-weight:600}}
  .date-row{{display:flex;align-items:flex-end;gap:22px}}
  .date-num{{font-family:'Oswald',sans-serif;font-weight:700;font-size:{v['date_num']}px;line-height:0.85;color:#D4715E}}
  .date-meta{{font-family:'Oswald',sans-serif;font-weight:600;font-size:{round(30*s)}px;letter-spacing:2px;text-transform:uppercase;color:#1C2A45;line-height:1.35;padding-bottom:10px}}
  .club{{font-size:{round(22*s)}px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#aaa}}
  .title{{font-family:'Oswald',sans-serif;font-weight:700;font-size:{title_size}px;line-height:1.12;text-transform:uppercase;letter-spacing:0.2px;color:#1C2A45;overflow:hidden;display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical}}
  .loc{{display:flex;align-items:center;gap:12px;font-size:{round(26*s)}px;color:#888;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}}
  .loc svg{{flex-shrink:0;width:{round(22*s)}px;height:{round(22*s)}px}}
  .footer{{display:flex;align-items:center;justify-content:center;gap:14px;padding-top:{v['footer_pad']}px;border-top:1.5px solid #E8D8D3}}
  .footer .site{{font-size:18px;color:#aaa;letter-spacing:1px}}
</style>
</head><body>
<div class="poster">
  <div class="blob"></div>
  <div class="top-bar">
    {_LOGO}
    <span class="city-pill">Stockholm</span>
  </div>
  <div class="content">
    <div class="kicker">Kommande event</div>
    <div class="date-row">
      <div class="date-num">{d.day}</div>
      <div class="date-meta">{day_name}<br>{month}</div>
    </div>
    <div class="club">{club}</div>
    <div class="title">{title}</div>
    <div class="loc">{_PIN_SVG}<span>{location}</span></div>
  </div>
  <div class="footer">{_LOGO.replace('class="logo"', 'class="logo small"')}<span class="site">runclubs.se</span></div>
</div>
</body></html>"""


async def render_event(ev: dict, out_dir: Path) -> list[Path]:
    from playwright.async_api import async_playwright

    slug = f"{ev['_dt'].strftime('%Y-%m-%d')}-{_slugify(ev['club'])}-{_slugify(ev['title'])[:40]}"
    paths: list[Path] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            for variant, cfg in VARIANTS.items():
                html = event_page_html(ev, variant)
                html_path = out_dir / f"{slug}-{variant}.html"
                html_path.write_text(html, encoding="utf-8")
                png_path = out_dir / f"{slug}-{variant}.png"

                ctx = await browser.new_context(
                    viewport={"width": cfg["w"], "height": cfg["h"]}, device_scale_factor=1
                )
                page = await ctx.new_page()
                await page.goto(f"file://{html_path}")
                await page.evaluate("document.fonts.ready")
                await page.wait_for_timeout(400)
                await page.screenshot(
                    path=str(png_path),
                    clip={"x": 0, "y": 0, "width": cfg["w"], "height": cfg["h"]},
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
