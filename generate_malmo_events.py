"""Generate malmo-running-events.html from the running-clubs events Google Sheet.

Reads from two worksheets:
  - Events       populated by mikaelsto/runclubs-events-feed (Strava)
  - WeeklyRuns   manually maintained recurring club runs

Filters to Malmö, expands weekly runs for the next LOOKAHEAD_DAYS days,
merges both lists, and renders a self-contained HTML page.

Usage:
    python generate_malmo_events.py                    # writes malmo-running-events.html
    python generate_malmo_events.py path/to/out.html   # custom output path
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from events_common import (
    DAYS_MAP,
    EVENTS_SHEET_ID,
    LOOKAHEAD_DAYS,
    combine_date_time,
    fetch_events,
    fetch_overrides,
    fetch_special_events,
    fetch_weekly_runs,
    _parse_date,
    _parse_time,
)

log = logging.getLogger(__name__)

MALMO_KEYWORDS = {"malmö", "malmo"}


def prepare_special_events(records: list[dict]) -> list[dict]:
    today = datetime.now(timezone.utc).date()
    events: list[dict] = []

    for r in records:
        city = (r.get("city") or "").lower().strip()
        if not any(kw in city for kw in MALMO_KEYWORDS):
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
            "club":        (r.get("club") or "").strip(),
            "title":       (r.get("title") or "Untitled").strip(),
            "date":        dt.strftime("%Y-%m-%dT%H:%M:%S") if dt else "",
            "location":    (r.get("location") or "").strip(),
            "description": (r.get("description") or "").strip(),
            "link":        (r.get("link") or "").strip(),
            "image_url":   (r.get("image_url") or "").strip(),
            "engagement":  "",
        })

    log.info("%d Malmö special events after filtering", len(events))
    return events


def prepare_events(records: list[dict]) -> list[dict]:
    today = datetime.now(timezone.utc).date()
    events: list[dict] = []

    for r in records:
        loc = (r.get("location") or "").lower()
        if not any(kw in loc for kw in MALMO_KEYWORDS):
            continue

        raw_date = (r.get("date") or "").strip()
        dt = _parse_date(raw_date)
        if dt is not None and dt.date() < today:
            continue

        events.append({
            "type":        "event",
            "source":      (r.get("source") or "").strip().lower(),
            "club":        (r.get("club") or "").strip(),
            "title":       (r.get("title") or "Untitled").strip(),
            "date":        dt.strftime("%Y-%m-%dT%H:%M:%S") if dt else "",
            "location":    (r.get("location") or "").strip(),
            "description": (r.get("description") or "").strip(),
            "link":        (r.get("link") or "").strip(),
            "image_url":   (r.get("image_url") or "").strip(),
            "engagement":  str(r.get("engagement") or "").strip(),
        })

    log.info("%d Malmö upcoming events after filtering", len(events))
    return events



def expand_weekly_runs(
    records: list[dict],
    overrides: dict[tuple[str, str], dict],
) -> list[dict]:
    today = datetime.now(timezone.utc).date()
    cutoff = today + timedelta(days=LOOKAHEAD_DAYS)
    events: list[dict] = []

    for r in records:
        city = (r.get("city") or "").lower().strip()
        if not any(kw in city for kw in MALMO_KEYWORDS):
            continue

        day_str = (r.get("day_of_week") or "").lower().strip()
        target_weekday = DAYS_MAP.get(day_str)
        if target_weekday is None:
            log.warning("Unknown day_of_week %r for club %r — skipping", day_str, r.get("club"))
            continue

        club      = (r.get("club") or "").strip()
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

    log.info("%d Malmö weekly run occurrences expanded (next %d days)", len(events), LOOKAHEAD_DAYS)
    return events


def render_html(events: list[dict], generated_at: str) -> str:
    events_json = json.dumps(events, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="sv">
<head>
<!-- Google Tag Manager -->
<script>(function(w,d,s,l,i){{w[l]=w[l]||[];w[l].push({{'gtm.start':
new Date().getTime(),event:'gtm.js'}});var f=d.getElementsByTagName(s)[0],
j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=
'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
}})(window,document,'script','dataLayer','GTM-TPSCMPZT');</script>
<!-- End Google Tag Manager -->
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Malmös Löparevent — Swedish Run Clubs</title>
  <meta name="description" content="Kommande grupplöpningar och events från Malmös run clubs — Strava-events och veckoliga grupplöpningar.">
  <meta property="og:title" content="Malmös Löparevent — Swedish Run Clubs">
  <meta property="og:description" content="Kommande grupplöpningar och events från Malmös run clubs.">
  <meta property="og:type" content="website">
  <meta property="og:url" content="https://runclubs.se/malmo-running-events">
  <meta property="og:image" content="https://runclubs.se/malmo-run-clubs.jpeg">
  <link rel="canonical" href="https://runclubs.se/malmo-running-events">
  <link href="https://fonts.googleapis.com/css2?family=Archivo+Black&family=Inter:ital,wght@1,900&family=Oswald:wght@500;700&family=DM+Sans:wght@400;500;600&family=Playfair+Display:wght@400&display=swap" rel="stylesheet">
  <link rel="icon" href="/favicon.ico" sizes="any">
  <link rel="icon" href="/favicon.svg" type="image/svg+xml">
  <style>
    *, *::before, *::after {{ margin: 0; padding: 0; box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{ font-family: 'DM Sans', sans-serif; color: #1C2A45; background: #FDFAF9; -webkit-font-smoothing: antialiased; }}

    .skip-link {{
      position: absolute; top: -100%; left: 1rem;
      background: #D4715E; color: #fff; padding: 8px 16px;
      border-radius: 0 0 6px 6px; font-size: 13px; font-weight: 500;
      z-index: 1000; text-decoration: none;
    }}
    .skip-link:focus {{ top: 0; }}

    nav {{
      display: flex; justify-content: space-between; align-items: center;
      padding: 1.25rem 2rem;
      background: rgba(253,250,249,0.92); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
      border-bottom: 1px solid #F0E0DC;
      position: sticky; top: 0; z-index: 100;
    }}
    .logo {{
      font-family: 'Oswald', sans-serif; font-weight: 700; font-size: 16px;
      text-transform: uppercase; letter-spacing: 2px;
      color: #1C2A45; text-decoration: none;
    }}
    .run-clubs-logo {{ display: inline-flex; align-items: baseline; font-size: 36px; color: #1a1a1a; text-decoration: none; }}
    .run-clubs-logo .run {{ font-family: 'Inter', sans-serif; font-weight: 900; font-style: italic; letter-spacing: -0.04em; padding-right: 2px; }}
    .run-clubs-logo .clubs {{ font-family: 'Playfair Display', serif; font-weight: 400; letter-spacing: -0.02em; }}
    .run-clubs-logo .suffix {{ font-family: 'Playfair Display', serif; font-size: 0.45em; font-weight: 400; text-transform: lowercase; margin-left: 2px; }}
    .footer-brand .run-clubs-logo {{ font-size: 28px; display: block; margin-bottom: 0.75rem; }}
    .nav-links {{ display: flex; gap: 2rem; }}
    .nav-links a {{
      font-size: 12px; letter-spacing: 0.5px; text-decoration: none;
      color: #888; text-transform: uppercase; font-weight: 500;
      transition: color 0.2s; position: relative;
    }}
    .nav-links a::after {{
      content: ''; position: absolute; bottom: -4px; left: 0;
      width: 0; height: 1.5px; background: #D4715E;
      transition: width 0.2s ease;
    }}
    .nav-links a:hover {{ color: #1C2A45; }}
    .nav-links a:hover::after {{ width: 100%; }}
    .nav-links a.active {{ color: #1C2A45; }}
    .nav-links a.active::after {{ width: 100%; }}
    .nav-toggle {{
      display: none; flex-direction: column; gap: 5px;
      cursor: pointer; background: none; border: none; padding: 4px;
    }}
    .nav-toggle span {{
      display: block; width: 22px; height: 2px;
      background: #1C2A45; transition: all 0.3s ease;
    }}
    .nav-toggle.open span:nth-child(1) {{ transform: rotate(45deg) translate(5px, 5px); }}
    .nav-toggle.open span:nth-child(2) {{ opacity: 0; }}
    .nav-toggle.open span:nth-child(3) {{ transform: rotate(-45deg) translate(5px, -5px); }}
    .mobile-menu {{
      display: none; flex-direction: column;
      background: rgba(253,250,249,0.98); backdrop-filter: blur(12px);
      border-bottom: 1px solid #F0E0DC;
      padding: 1rem 2rem; gap: 0;
    }}
    .mobile-menu.open {{ display: flex; }}
    .mobile-menu a {{
      font-size: 13px; letter-spacing: 1px; text-decoration: none;
      color: #1C2A45; text-transform: uppercase; font-weight: 500;
      padding: 0.75rem 0; border-bottom: 1px solid #F0E0DC;
      transition: color 0.15s;
    }}
    .mobile-menu a:last-child {{ border-bottom: none; }}
    .mobile-menu a:hover {{ color: #D4715E; }}

    .page-header {{
      background: #1C2A45;
      padding: 4rem 2rem 3rem;
      position: relative;
      overflow: hidden;
    }}
    .page-header::before {{
      content: 'EVENT';
      font-family: 'Archivo Black', sans-serif;
      font-size: clamp(80px, 18vw, 220px);
      color: rgba(255,255,255,0.03);
      position: absolute;
      right: -1rem; bottom: -1rem;
      line-height: 1;
      letter-spacing: -4px;
      pointer-events: none;
      user-select: none;
    }}
    .page-header-inner {{ max-width: 700px; position: relative; z-index: 1; }}
    .breadcrumb {{ font-size: 12px; color: rgba(255,255,255,0.4); margin-bottom: 0.75rem; }}
    .breadcrumb a {{ color: rgba(255,255,255,0.4); text-decoration: none; transition: color 0.15s; }}
    .breadcrumb a:hover {{ color: #EEAA96; }}
    .page-header-tag {{
      font-size: 11px; letter-spacing: 3px; text-transform: uppercase;
      color: #EEAA96; margin-bottom: 1rem; font-weight: 500;
    }}
    .page-header h1 {{
      font-family: 'Archivo Black', sans-serif;
      font-size: clamp(36px, 6vw, 64px);
      line-height: 0.95; text-transform: uppercase;
      color: #FDFAF9; letter-spacing: -1px; margin-bottom: 1rem;
    }}
    .page-header p {{
      font-size: 15px; color: rgba(255,255,255,0.5);
      line-height: 1.7; max-width: 480px;
    }}

    .stats-bar {{
      background: #D4715E;
      padding: 1rem 2rem;
      display: flex; gap: 2.5rem; flex-wrap: wrap;
    }}
    .stat-item {{ display: flex; align-items: center; gap: 8px; }}
    .stat-number {{
      font-family: 'Archivo Black', sans-serif;
      font-size: 22px; color: #FDFAF9; line-height: 1;
    }}
    .stat-label {{
      font-size: 11px; letter-spacing: 1px; text-transform: uppercase;
      color: rgba(255,255,255,0.65); font-weight: 500;
    }}
    .stat-divider {{ width: 1px; background: rgba(255,255,255,0.2); align-self: stretch; }}

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
      color: #1C2A45; cursor: pointer; transition: all 0.2s;
    }}
    .filter-toggle:hover {{ border-color: #D4715E; }}
    .filter-toggle-label {{ display: flex; align-items: center; gap: 8px; }}
    .filter-toggle-chevron {{ transition: transform 0.2s; color: #D4715E; }}
    .filters-bar.open .filter-toggle-chevron {{ transform: rotate(180deg); }}
    .close-filters {{
      font-size: 13px; color: #D4715E; background: none; border: none;
      cursor: pointer; font-family: 'DM Sans', sans-serif; font-weight: 500;
      padding: 6px 0; text-decoration: underline; margin-left: auto;
      text-underline-offset: 2px; transition: color 0.15s; display: none;
    }}
    .filters-bar.open .close-filters {{ display: inline-block; }}
    .close-filters:hover {{ color: #C8604A; }}
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
    .filter-pill:hover {{ border-color: #D4715E; color: #D4715E; }}
    .filter-pill.active {{ background: #1C2A45; color: #FDFAF9; border-color: #1C2A45; }}

    .city-nav {{
      padding: 1.75rem 2rem;
      border-bottom: 1px solid #F0E0DC;
      background: #FDFAF9;
      display: flex; align-items: center; gap: 1.5rem; flex-wrap: wrap;
    }}
    .city-nav-label {{
      font-size: 11px; letter-spacing: 2px; text-transform: uppercase;
      color: #aaa; font-weight: 500; white-space: nowrap;
    }}
    .city-nav-buttons {{ display: flex; gap: 8px; flex-wrap: wrap; }}
    .city-nav-btn {{
      font-size: 12px; font-weight: 600; padding: 8px 18px;
      border-radius: 20px; border: 1px solid #E8D8D3;
      background: #fff; color: #1C2A45; cursor: pointer;
      font-family: 'DM Sans', sans-serif; text-decoration: none;
      transition: all 0.2s; letter-spacing: 0.3px;
      display: inline-flex; align-items: center; gap: 5px;
    }}
    .city-nav-btn:hover {{ border-color: #D4715E; color: #D4715E; }}
    .city-nav-btn.active {{ background: #1C2A45; color: #FDFAF9; border-color: #1C2A45; pointer-events: none; }}

    .events-layout {{ padding: 3rem 2rem; max-width: 1200px; margin: 0 auto; }}

    .date-group {{ margin-bottom: 3rem; }}
    .date-heading {{ display: flex; align-items: center; gap: 1rem; margin-bottom: 1.5rem; }}
    .date-name {{
      font-family: 'Archivo Black', sans-serif;
      font-size: 20px; letter-spacing: 2px; text-transform: uppercase; color: #1C2A45;
    }}
    .date-line {{ flex: 1; height: 1px; background: #F0E0DC; }}
    .date-count {{ font-size: 11px; letter-spacing: 1px; text-transform: uppercase; color: #ccc; font-weight: 500; }}

    .events-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
      gap: 16px;
    }}

    .event-card {{
      background: #fff;
      border: 1px solid #EFE4E0;
      border-radius: 16px;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      transition: transform 0.25s ease, box-shadow 0.25s ease, border-color 0.25s ease;
      text-decoration: none;
      color: #1C2A45;
    }}
    .event-card:hover {{
      transform: translateY(-4px);
      box-shadow: 0 12px 40px rgba(28,42,69,0.1);
      border-color: #D4715E;
    }}
    .event-card--no-link {{ cursor: default; }}
    .event-card--no-link:hover {{
      transform: none; box-shadow: none; border-color: #EFE4E0;
    }}

    .event-card--special {{
      border: 2px solid transparent !important;
      background: linear-gradient(#fff, #fff) padding-box,
                  linear-gradient(135deg, #ffd700, #ff7eb3, #c084fc, #60a5fa, #ffd700) border-box;
      background-size: 100% 100%, 400% 400%;
      animation: specialGradient 5s ease infinite;
      position: relative;
      overflow: hidden;
    }}
    .event-card--special:hover {{
      box-shadow: 0 12px 40px rgba(192,132,252,0.25), 0 0 0 1px rgba(255,215,0,0.3);
    }}
    @keyframes specialGradient {{
      0%, 100% {{ background-position: 0 0, 0% 50%; }}
      50% {{ background-position: 0 0, 100% 50%; }}
    }}
    .event-card--special .event-date-block {{
      background: linear-gradient(160deg, #3d1354, #6b2fa0);
    }}
    .event-card--special::after {{
      content: '✨';
      position: absolute;
      top: 10px; right: 12px;
      font-size: 18px;
      pointer-events: none;
      animation: sparkleFloat 2.5s ease-in-out infinite;
      z-index: 2;
    }}
    @keyframes sparkleFloat {{
      0%, 100% {{ transform: translateY(0) scale(1); opacity: 0.85; }}
      50% {{ transform: translateY(-4px) scale(1.2); opacity: 1; }}
    }}
    .source-special {{ background: linear-gradient(135deg, #c084fc, #818cf8); color: #fff; }}

    .event-card-image {{
      width: 100%; height: 180px; object-fit: cover; display: block;
    }}

    .event-card-top {{ display: flex; align-items: stretch; }}

    .event-date-block {{
      min-width: 72px;
      display: flex; flex-direction: column; align-items: center; justify-content: center;
      padding: 1.25rem 0.75rem;
      background: #1a3a28;
      gap: 2px; flex-shrink: 0;
    }}
    .event-date-block.no-date {{ background: #2a2535; }}

    .event-day-num {{
      font-family: 'Archivo Black', sans-serif;
      font-size: 32px; line-height: 1; color: #FDFAF9;
    }}
    .event-month-abbr {{
      font-size: 10px; letter-spacing: 2px; text-transform: uppercase;
      color: rgba(255,255,255,0.5); font-weight: 600;
    }}
    .event-day-name {{
      font-size: 9px; letter-spacing: 1px; text-transform: uppercase;
      color: rgba(255,255,255,0.3); font-weight: 500; margin-top: 4px;
    }}
    .event-date-block.no-date .event-day-num {{ font-size: 20px; letter-spacing: 2px; }}

    .event-card-body {{
      padding: 1rem 1.25rem;
      flex: 1; display: flex; flex-direction: column; gap: 6px;
    }}
    .event-source-row {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
    .source-badge {{
      font-size: 9px; font-weight: 700; letter-spacing: 1px; text-transform: uppercase;
      padding: 3px 8px; border-radius: 10px; flex-shrink: 0;
    }}
    .source-strava    {{ background: #FC5200; color: #fff; }}
    .source-other     {{ background: #4a90d9; color: #fff; }}
    .type-badge {{
      font-size: 9px; font-weight: 700; letter-spacing: 1px; text-transform: uppercase;
      padding: 3px 8px; border-radius: 10px; flex-shrink: 0;
    }}
    .type-event   {{ background: #E8EEF8; color: #1C2A45; }}
    .type-weekly  {{ background: #D8F3DC; color: #1B4332; }}
    .event-club {{
      font-size: 11px; font-weight: 600; letter-spacing: 0.5px; text-transform: uppercase;
      color: #aaa;
    }}
    .event-title {{
      font-family: 'Oswald', sans-serif; font-weight: 700;
      font-size: 17px; text-transform: uppercase;
      letter-spacing: 0.5px; line-height: 1.2; color: #1C2A45;
    }}
    .event-location {{
      display: flex; align-items: center; gap: 5px;
      font-size: 12px; color: #999;
    }}
    .event-desc {{
      font-size: 12px; color: #666; line-height: 1.55;
      display: -webkit-box; -webkit-line-clamp: 3;
      -webkit-box-orient: vertical; overflow: hidden;
      margin-top: 2px;
    }}

    .event-card-footer {{
      padding: 0.75rem 1.25rem;
      border-top: 1px solid #F5EBE8;
      display: flex; justify-content: space-between; align-items: center;
    }}
    .event-engagement {{
      font-size: 12px; font-weight: 500; color: #bbb;
      display: flex; align-items: center; gap: 4px;
    }}
    .event-cta {{
      font-size: 11px; font-weight: 600; letter-spacing: 1px;
      text-transform: uppercase; color: #D4715E;
      display: flex; align-items: center; gap: 4px;
      transition: gap 0.2s;
    }}
    .event-card:hover .event-cta {{ gap: 8px; }}

    .no-events {{
      grid-column: 1 / -1; text-align: center;
      padding: 4rem 1rem; color: #bbb;
    }}
    .no-events-icon {{ font-size: 48px; display: block; margin-bottom: 1rem; filter: grayscale(1) opacity(0.3); }}
    .no-events p {{ font-size: 15px; }}

    .nl-section {{ background: #ffffff; border-top: 1px solid #E8E8E8; border-bottom: 1px solid #E8E8E8; }}
    .nl-body {{ max-width: 560px; margin: 0 auto; padding: 4rem 2rem; text-align: center; }}
    .nl-badge {{
      display: inline-flex; align-items: center; gap: 8px;
      background: #FFF0ED; color: #D4715E;
      font-size: 11px; font-weight: 700; letter-spacing: 2px; text-transform: uppercase;
      padding: 6px 14px; border-radius: 100px; margin-bottom: 1.5rem;
    }}
    .nl-title {{
      font-family: 'Archivo Black', sans-serif;
      font-size: clamp(28px, 4vw, 42px);
      color: #1C2A45; line-height: 1.1; text-transform: uppercase;
      letter-spacing: -1px; margin-bottom: 1rem;
    }}
    .nl-title em {{ color: #D4715E; font-style: normal; }}
    .nl-desc {{ font-size: 15px; color: #777; line-height: 1.75; margin-bottom: 2rem; }}
    .newsletter-form {{ display: flex; flex-direction: column; gap: 12px; }}
    .newsletter-input {{
      padding: 16px 20px; border: 2px solid #E8E8E8; border-radius: 12px;
      font-size: 15px; font-family: 'DM Sans', sans-serif;
      color: #1C2A45; background: #fff; outline: none;
      transition: border-color 0.2s; width: 100%; box-sizing: border-box;
    }}
    .newsletter-input::placeholder {{ color: #aaa; }}
    .newsletter-input:focus {{ border-color: #D4715E; }}
    .newsletter-btn {{
      background: #D4715E; color: #fff;
      font-size: 15px; font-weight: 700; letter-spacing: 0.3px;
      padding: 17px; border-radius: 12px; border: none;
      cursor: pointer; font-family: 'DM Sans', sans-serif;
      transition: background 0.2s;
    }}
    .newsletter-btn:hover {{ background: #C8604A; }}
    .nl-disclaimer {{ font-size: 11px; color: #bbb; text-align: center; margin-top: 0.75rem; }}

    footer {{
      background: #F7E8E4; border-top: 1px solid #F0D8D3;
      padding: 3.5rem 2rem; display: grid;
      grid-template-columns: 2fr 1fr 1fr; gap: 2rem;
      font-size: 13px;
    }}
    .footer-brand .logo {{ font-size: 14px; letter-spacing: 1.5px; display: block; margin-bottom: 0.75rem; }}
    .footer-brand p {{ font-size: 13px; color: #888; line-height: 1.6; max-width: 280px; }}
    footer h4 {{
      font-size: 10px; letter-spacing: 2px; text-transform: uppercase;
      color: #aaa; margin-bottom: 1rem; font-weight: 500;
    }}
    footer a {{ display: block; color: #1C2A45; text-decoration: none; margin-bottom: 8px; transition: color 0.15s; }}
    footer a:hover {{ color: #D4715E; }}
    .footer-bottom {{
      grid-column: 1 / -1; padding-top: 1.5rem;
      border-top: 1px solid #F0D8D3;
      font-size: 12px; color: #aaa;
    }}
    .footer-updated {{ font-size: 11px; color: #ccc; margin-top: 4px; }}

    .fade-in {{ opacity: 0; transform: translateY(20px); transition: opacity 0.6s ease, transform 0.6s ease; }}
    .fade-in.visible {{ opacity: 1; transform: translateY(0); }}

    @media (max-width: 768px) {{
      nav {{ padding: 1rem 1.25rem; }}
      .nav-links {{ display: none; }}
      .nav-toggle {{ display: flex; }}
      .page-header {{ padding: 3rem 1.25rem 2.5rem; }}
      .page-header h1 {{ font-size: clamp(32px, 10vw, 52px); }}
      .stats-bar {{ padding: 1rem 1.25rem; gap: 1.25rem; }}
      .stat-divider {{ display: none; }}
      .city-nav {{ padding: 1.25rem; gap: 1rem; flex-direction: column; align-items: flex-start; }}
      .filters-bar {{ padding: 1rem 1.25rem; }}
      .filter-toggle {{ display: flex; }}
      .filters-inner {{ display: none; flex-direction: column; gap: 1rem; margin-top: 1rem; }}
      .filters-bar.open .filters-inner {{ display: flex; }}
      .filter-group {{ width: 100%; flex-wrap: wrap; }}
      .events-layout {{ padding: 2rem 1.25rem; }}
      .events-grid {{ grid-template-columns: 1fr; }}
      footer {{ padding: 2rem 1.25rem; grid-template-columns: 1fr; gap: 1.5rem; }}
    }}
  </style>
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
      <a href="malmo">Malmö</a>
      <a href="nyheter">Nyheter</a>
      <a href="running-events" class="active">Events</a>
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
    <a href="malmo">Malmö</a>
    <a href="nyheter">Nyheter</a>
    <a href="running-events" class="active">Events</a>
    <a href="loppkalender">Loppkalender</a>
    <a href="om-oss">Om oss</a>
  </div>

  <main id="main-content">

  <header class="page-header">
    <div class="page-header-inner">
      <div class="breadcrumb"><a href="/">Start</a> → <a href="/running-events">Running Events</a> → Malmö</div>
      <div class="page-header-tag">Malmös run clubs</div>
      <h1>Kommande<br>Events och Weekly runs</h1>
      <p>Här visas alla kommande running events från Strava och weekly runs från löpargrupper, run clubs, communions och run crews i Malmö.</p>
    </div>
  </header>

  <div class="stats-bar">
    <div class="stat-item">
      <div>
        <div class="stat-number" id="stat-total">—</div>
        <div class="stat-label">Events</div>
      </div>
    </div>
    <div class="stat-divider"></div>
    <div class="stat-item">
      <div>
        <div class="stat-number" id="stat-clubs">—</div>
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
    <span class="city-nav-label">Se händelser i annan stad</span>
    <div class="city-nav-buttons">
      <a href="stockholm-running-events" class="city-nav-btn">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
        Stockholm
      </a>
      <a href="goteborg-running-events" class="city-nav-btn">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
        Göteborg
      </a>
      <a href="malmo-running-events" class="city-nav-btn active">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
        Malmö
      </a>
    </div>
  </div>

  <div class="filters-bar" id="filters-bar"></div>

  <div class="events-layout">
    <div id="events-container"></div>
  </div>

  <section class="nl-section fade-in">
    <div class="nl-body">
      <div class="nl-badge">Prenumerera på <span class="run-clubs-logo" style="font-size:1em;color:#D4715E;"><span class="run">RUN</span><span class="clubs">CLUBS</span><span class="suffix">.se</span></span> veckobrev</div>
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
      <p>Vi hjälper dig hitta de senaste och trendigaste run clubs och running events i din stad. Just nu i Stockholm, Göteborg och Malmö.</p>
    </div>
    <div>
      <h4>Städer</h4>
      <a href="stockholm">Stockholm</a>
      <a href="goteborg">Göteborg</a>
      <a href="malmo">Malmö</a>
    </div>
    <div>
      <h4>Om sajten</h4>
      <a href="om-oss">Om oss</a>
      <a href="nyheter">Nyheter</a>
      <a href="running-events">Events</a>
      <a href="loppkalender">Loppkalender</a>
      <a href="kontakt">Kontakt</a>
      <a href="samarbeta">Samarbeta</a>
    </div>
    <div class="footer-bottom">
      &copy; 2026 Swedish Run Clubs. Byggd med kärlek av <a href="https://amandahultin.se" target="_blank" rel="noopener noreferrer" style="display:inline; margin:0;">Amanda Hultin <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-left:2px;"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg></a>.
      <div class="footer-updated">Eventdata uppdaterades {generated_at}.</div>
    </div>
  </footer>

  <script>
    const events = {events_json};

    const SV_MONTHS_SHORT = ['jan','feb','mar','apr','maj','jun','jul','aug','sep','okt','nov','dec'];
    const SV_DAYS         = ['Söndag','Måndag','Tisdag','Onsdag','Torsdag','Fredag','Lördag'];
    const SV_MONTHS       = ['Januari','Februari','Mars','April','Maj','Juni','Juli','Augusti','September','Oktober','November','December'];

    let activeSource = 'all';
    let activeClubs = new Set();

    function parseDate(str) {{
      if (!str) return null;
      const d = new Date(str);
      return isNaN(d.getTime()) ? null : d;
    }}

    function typeBadge(type, source) {{
      if (type === 'weekly_run') return `<span class="type-badge type-weekly">Weekly run</span>`;
      if (source === 'strava' || source === 'special') return '';
      return `<span class="type-badge type-event">Event</span>`;
    }}

    function sourceBadge(source) {{
      if (source === 'weekly_run') return '';
      if (source === 'special') return `<span class="source-badge source-special">Special Event</span>`;
      const cls   = source === 'strava' ? 'source-strava' : 'source-other';
      const label = source === 'strava' ? 'Strava' : source;
      return `<span class="source-badge ${{cls}}">${{label}}</span>`;
    }}

    function cardHTML(ev) {{
      const d       = parseDate(ev.date);
      const hasDate = d !== null;

      let dateBlockHTML;
      if (hasDate) {{
        const dayNum   = d.getDate();
        const monthStr = SV_MONTHS_SHORT[d.getMonth()];
        const dayStr   = SV_DAYS[d.getDay()].slice(0, 3);
        dateBlockHTML = `
          <div class="event-date-block">
            <div class="event-day-num">${{dayNum}}</div>
            <div class="event-month-abbr">${{monthStr}}</div>
            <div class="event-day-name">${{dayStr}}</div>
          </div>`;
      }} else {{
        dateBlockHTML = `
          <div class="event-date-block no-date">
            <div class="event-day-num">—</div>
          </div>`;
      }}

      const imageHTML = ev.image_url
        ? `<img class="event-card-image" src="${{ev.image_url}}" alt="" loading="lazy">`
        : '';

      const locHTML = ev.location
        ? `<div class="event-location">
             <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
             ${{ev.location}}
           </div>`
        : '';

      const descHTML = ev.description
        ? `<p class="event-desc">${{ev.description}}</p>`
        : '';

      const engHTML = ev.engagement && ev.source === 'strava'
        ? `<span class="event-engagement">
             <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></svg>
             ${{ev.engagement}} anmälda
           </span>`
        : '<span></span>';

      const isExternal = ev.source === 'strava';
      const ctaHTML = ev.link
        ? (isExternal
            ? `<span class="event-cta">Läs mer <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="vertical-align:middle;margin-left:2px;"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg></span>`
            : `<span class="event-cta">Läs mer <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M12 5l7 7-7 7"/></svg></span>`)
        : '';

      const inner = `
        ${{imageHTML}}
        <div class="event-card-top">
          ${{dateBlockHTML}}
          <div class="event-card-body">
            <div class="event-source-row">
              ${{typeBadge(ev.type, ev.source)}}
              ${{sourceBadge(ev.source)}}
              <span class="event-club">${{ev.club}}</span>
            </div>
            <div class="event-title">${{ev.title}}</div>
            ${{locHTML}}
            ${{descHTML}}
          </div>
        </div>
        <div class="event-card-footer">
          ${{engHTML}}
          ${{ctaHTML}}
        </div>`;

      const specialClass = ev.source === 'special' ? ' event-card--special' : '';
      const opensNewTab  = ev.source === 'strava' || ev.source === 'special';
      if (ev.link) {{
        return `<a href="${{ev.link}}" ${{opensNewTab ? 'target="_blank" rel="noopener"' : ''}} class="event-card${{specialClass}}" aria-label="${{ev.title}}">${{inner}}</a>`;
      }} else {{
        return `<div class="event-card event-card--no-link${{specialClass}}" aria-label="${{ev.title}}">${{inner}}</div>`;
      }}
    }}

    function render() {{
      const container = document.getElementById('events-container');
      container.innerHTML = '';

      const filtered = events.filter(ev => {{
        const sourceOk = activeSource === 'all' || ev.source === activeSource;
        const clubOk   = activeClubs.size === 0
          || (activeClubs.has('__ovrigt__') && !ev.club)
          || (ev.club && activeClubs.has(ev.club));
        return sourceOk && clubOk;
      }});

      if (filtered.length === 0) {{
        container.innerHTML = `
          <div class="no-events">
            <span class="no-events-icon">🏃</span>
            <p>Inga events hittades med dessa filter.</p>
          </div>`;
        document.getElementById('stat-total').textContent = 0;
        document.getElementById('stat-clubs').textContent = 0;
        return;
      }}

      const byDate = {{}};
      const noDate = [];
      filtered.forEach(ev => {{
        const d = parseDate(ev.date);
        if (d) {{
          const key = ev.date.slice(0, 10);
          if (!byDate[key]) byDate[key] = {{ label: '', events: [] }};
          byDate[key].events.push(ev);
          if (!byDate[key].label) {{
            byDate[key].label = SV_DAYS[d.getDay()] + ' ' + d.getDate() + ' ' + SV_MONTHS[d.getMonth()];
          }}
        }} else {{
          noDate.push(ev);
        }}
      }});

      Object.keys(byDate).sort().forEach(key => {{
        const group = byDate[key];
        const count = group.events.length;
        const section = document.createElement('div');
        section.className = 'date-group';
        section.innerHTML = `
          <div class="date-heading">
            <span class="date-name">${{group.label}}</span>
            <div class="date-line"></div>
            <span class="date-count">${{count}} event${{count !== 1 ? 's' : ''}}</span>
          </div>
          <div class="events-grid">${{group.events.map(cardHTML).join('')}}</div>`;
        container.appendChild(section);
      }});

      if (noDate.length > 0) {{
        const section = document.createElement('div');
        section.className = 'date-group';
        section.innerHTML = `
          <div class="date-heading">
            <span class="date-name">Inget datum</span>
            <div class="date-line"></div>
            <span class="date-count">${{noDate.length}} post${{noDate.length !== 1 ? 'ar' : ''}}</span>
          </div>
          <div class="events-grid">${{noDate.map(cardHTML).join('')}}</div>`;
        container.appendChild(section);
      }}

      document.getElementById('stat-total').textContent = filtered.length;
      document.getElementById('stat-clubs').textContent = new Set(filtered.map(ev => ev.club).filter(Boolean)).size;
    }}

    document.querySelectorAll('[data-filter]').forEach(btn => {{
      btn.addEventListener('click', function() {{
        document.querySelectorAll('[data-filter="source"]').forEach(b => b.classList.remove('active'));
        this.classList.add('active');
        activeSource = this.dataset.value;
        render();
      }});
    }});

    const navToggle  = document.querySelector('.nav-toggle');
    const mobileMenu = document.querySelector('.mobile-menu');
    navToggle.addEventListener('click', function() {{
      const isOpen = mobileMenu.classList.toggle('open');
      navToggle.classList.toggle('open');
      navToggle.setAttribute('aria-expanded', isOpen);
      navToggle.setAttribute('aria-label', isOpen ? 'Stäng meny' : 'Öppna meny');
    }});

    function renderClubFilter() {{
      const clubs = [...new Set(events.map(ev => ev.club || '').filter(Boolean))]
        .sort((a, b) => a.localeCompare(b, 'sv'));
      const hasOvrigt = events.some(ev => !ev.club);
      const bar = document.getElementById('filters-bar');
      if (!bar) return;

      let pillsHtml = `<button class="filter-pill active" data-filter="club" data-value="all">Alla</button>`;
      clubs.forEach(club => {{
        pillsHtml += `<button class="filter-pill" data-filter="club" data-value="${{club.replace(/&/g,'&amp;').replace(/"/g,'&quot;')}}">${{club.replace(/&/g,'&amp;')}}</button>`;
      }});
      if (hasOvrigt) pillsHtml += `<button class="filter-pill" data-filter="club" data-value="__ovrigt__">Övrigt</button>`;

      bar.innerHTML = `
        <button class="filter-toggle" id="filter-toggle" aria-expanded="false" aria-controls="filters-inner">
          <span class="filter-toggle-label">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>
            Filtrera klubb
          </span>
          <svg class="filter-toggle-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
        </button>
        <div class="filters-inner" id="filters-inner">
          <div class="filter-group"><span class="filter-label">Klubb</span>${{pillsHtml}}</div>
          <button class="close-filters" id="close-filters">Stäng</button>
        </div>`;

      bar.querySelectorAll('[data-filter="club"]').forEach(btn => {{
        btn.addEventListener('click', function() {{
          const val = this.dataset.value;
          if (val === 'all') {{
            activeClubs.clear();
            bar.querySelectorAll('[data-filter="club"]').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
          }} else {{
            bar.querySelector('[data-value="all"]').classList.remove('active');
            if (activeClubs.has(val)) {{
              activeClubs.delete(val);
              this.classList.remove('active');
            }} else {{
              activeClubs.add(val);
              this.classList.add('active');
            }}
            if (activeClubs.size === 0) {{
              bar.querySelector('[data-value="all"]').classList.add('active');
            }}
          }}
          render();
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

    const observer = new IntersectionObserver(entries => {{
      entries.forEach(e => {{ if (e.isIntersecting) e.target.classList.add('visible'); }});
    }}, {{ threshold: 0 }});
    document.querySelectorAll('.fade-in').forEach(el => observer.observe(el));

    const _clubParam = new URLSearchParams(window.location.search).get('club');
    if (_clubParam) activeClubs.add(_clubParam);

    render();
    renderClubFilter();

    if (_clubParam) {{
      const allPill = document.querySelector('[data-filter="club"][data-value="all"]');
      if (allPill) allPill.classList.remove('active');
      const targetPill = document.querySelector(`[data-filter="club"][data-value="${{_clubParam}}"]`);
      if (targetPill) targetPill.classList.add('active');
    }}
  </script>
  <script src="newsletter.js"></script>
</body>
</html>
"""


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("malmo-running-events.html")
    sheet_id = os.environ.get("GOOGLE_SHEET_ID") or EVENTS_SHEET_ID

    records       = fetch_events(sheet_id)
    events        = prepare_events(records)

    weekly_records  = fetch_weekly_runs(sheet_id)
    overrides       = fetch_overrides(sheet_id)
    weekly_events   = expand_weekly_runs(weekly_records, overrides)

    special_records = fetch_special_events(sheet_id)
    special_events  = prepare_special_events(special_records)

    all_events = events + weekly_events + special_events
    all_events.sort(key=lambda x: (x["date"] or "9999", x["club"]))
    log.info("%d total events after merge", len(all_events))

    generated_at = datetime.now(timezone.utc).strftime("%-d %B %Y")
    html_out = render_html(all_events, generated_at)

    out_path.write_text(html_out, encoding="utf-8")
    log.info("Wrote %s (%d events)", out_path, len(events))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
