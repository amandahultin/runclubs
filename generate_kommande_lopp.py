"""Generate kommande-lopp.html from the races Google Sheet.

Reads race data from the first tab of the Google Sheet populated by the
runclubs-races-scraper, filters to 10 km+, and renders a self-contained
HTML page matching the runclubs.se design system.

Usage:
    python generate_kommande_lopp.py              # writes kommande-lopp.html
    python generate_kommande_lopp.py path/to/out.html
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

log = logging.getLogger(__name__)

# Distance category boundaries (km)
_DIST_BUCKETS = [
    ("10k",         9.5,  10.49),
    ("11-20k",     10.5,  20.99),
    ("Halvmaraton", 21.0,  22.49),
    ("30k",        22.5,  35.0),
    ("Maraton",    40.0,  43.5),
]

# County → display region
_COUNTY_REGION = {
    "stockholms":       "Stockholm",
    "västra götalands": "Göteborg",
    "skåne":            "Malmö",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_km(distance_str: str) -> float | None:
    if not distance_str:
        return None
    m = re.search(r"([\d.,]+)\s*km", distance_str, re.IGNORECASE)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except ValueError:
        return None


def _dist_category(km: float) -> str | None:
    for label, lo, hi in _DIST_BUCKETS:
        if lo <= km <= hi:
            return label
    return None


def _map_region(row: dict) -> str | None:
    # If scraper already resolved the region, use it directly
    region = (row.get("region") or "").strip()
    if region in ("Stockholm", "Göteborg", "Malmö"):
        return region

    # Fall back to county mapping
    county = (row.get("county") or "").lower().strip()
    for key, r in _COUNTY_REGION.items():
        if key in county:
            return r

    # City-based fallback
    city = (row.get("city") or "").lower().strip()
    if "stockholm" in city:
        return "Stockholm"
    if any(x in city for x in ("göteborg", "gothenburg", "mölndal")):
        return "Göteborg"
    if any(x in city for x in ("malmö", "lund", "helsingborg", "kristianstad")):
        return "Malmö"
    return None


# ── Google Sheets ─────────────────────────────────────────────────────────────

def _sheet_client() -> gspread.Client:
    raw = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    creds = Credentials.from_service_account_info(
        json.loads(raw),
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    return gspread.authorize(creds)


def fetch_races(sheet_id: str) -> list[dict]:
    gc = _sheet_client()
    sh = gc.open_by_key(sheet_id)
    ws = sh.get_worksheet_by_id(114178703)
    records = ws.get_all_records()
    log.info("Fetched %d rows from sheet", len(records))
    return records


# ── Filter & enrich ───────────────────────────────────────────────────────────

def prepare_races(records: list[dict]) -> list[dict]:
    today = date.today()
    races: list[dict] = []

    for r in records:
        # Skip past events
        raw_date = (r.get("date") or "").strip()
        try:
            race_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError:
            continue
        if race_date < today:
            continue

        # Distance filtering — keep ≥ 10 km or unknown
        km = _parse_km(r.get("distance") or "")
        if km is not None and km < 9.5:
            continue

        # Use dist_cat from sheet if present, otherwise derive
        dist_cat = (r.get("dist_cat") or "").strip() or (
            _dist_category(km) if km is not None else None
        )

        region = _map_region(r)
        if not region:
            continue

        races.append({
            "name":     (r.get("name") or "").strip(),
            "date":     raw_date,
            "city":     (r.get("city") or "").strip(),
            "region":   region,
            "distance": (r.get("distance") or "").strip(),
            "dist_cat": dist_cat,
            "link":     (r.get("link") or "").strip(),
        })

    races.sort(key=lambda x: x["date"])
    log.info("%d races remain after filtering", len(races))
    return races


# ── HTML generation ───────────────────────────────────────────────────────────

def render_html(races: list[dict], generated_at: str) -> str:
    races_json = json.dumps(races, ensure_ascii=False)

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
  <title>Kommande Lopp — Swedish Run Clubs</title>
  <meta name="description" content="Hitta kommande löptävlingar i Sverige — Stockholm, Göteborg och Malmö. 10 km, halvmaraton, maraton och mer.">
  <meta property="og:title" content="Kommande Lopp — Swedish Run Clubs">
  <meta property="og:description" content="Kommande löptävlingar i Sverige — 10 km, halvmaraton och maraton.">
  <meta property="og:type" content="website">
  <meta property="og:url" content="https://runclubs.se/loppkalender">
  <link rel="canonical" href="https://runclubs.se/loppkalender">
  <link href="https://fonts.googleapis.com/css2?family=Archivo+Black&family=Oswald:wght@500;700&family=DM+Sans:wght@400;500;600&display=swap" rel="stylesheet">
  <link rel="icon" href="/favicon.ico" sizes="any">
  <link rel="icon" href="/favicon.svg" type="image/svg+xml">
  <style>
    *, *::before, *::after {{ margin: 0; padding: 0; box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{ font-family: 'DM Sans', sans-serif; color: #1C2A45; background: #FDFAF9; -webkit-font-smoothing: antialiased; }}

    /* ── SKIP LINK ── */
    .skip-link {{
      position: absolute; top: -100%; left: 1rem;
      background: #D4715E; color: #fff; padding: 8px 16px;
      border-radius: 0 0 6px 6px; font-size: 13px; font-weight: 500;
      z-index: 1000; text-decoration: none;
    }}
    .skip-link:focus {{ top: 0; }}

    /* ── NAV ── */
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

    /* ── PAGE HEADER ── */
    .page-header {{
      background: #1C2A45;
      padding: 4rem 2rem 3rem;
      position: relative;
      overflow: hidden;
    }}
    .page-header::before {{
      content: 'LOPP';
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

    /* ── STATS BAR ── */
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

    /* ── FILTERS ── */
    .filters-bar {{
      padding: 1.5rem 2rem;
      border-bottom: 1px solid #F0E0DC;
      display: flex; gap: 1.5rem; flex-wrap: wrap; align-items: center;
    }}
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

    /* ── MAIN LAYOUT ── */
    .events-layout {{ padding: 3rem 2rem; max-width: 1200px; margin: 0 auto; }}

    /* ── MONTH GROUP ── */
    .month-group {{ margin-bottom: 3rem; }}
    .month-heading {{ display: flex; align-items: center; gap: 1rem; margin-bottom: 1.5rem; }}
    .month-name {{
      font-family: 'Archivo Black', sans-serif;
      font-size: 11px; letter-spacing: 3px; text-transform: uppercase; color: #bbb;
    }}
    .month-line {{ flex: 1; height: 1px; background: #F0E0DC; }}
    .month-count {{ font-size: 11px; letter-spacing: 1px; text-transform: uppercase; color: #ccc; font-weight: 500; }}

    /* ── RACE CARDS GRID ── */
    .events-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
      gap: 16px;
    }}

    /* ── RACE CARD ── */
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

    /* Cards without a registration link — not clickable */
    .event-card--no-link {{
      cursor: default;
    }}
    .event-card--no-link:hover {{
      transform: none;
      box-shadow: none;
      border-color: #EFE4E0;
    }}

    .event-card-top {{ display: flex; align-items: stretch; }}

    /* ── DATE BLOCK ── */
    .event-date-block {{
      min-width: 72px;
      display: flex; flex-direction: column; align-items: center; justify-content: center;
      padding: 1.25rem 0.75rem;
      background: #1C2A45;
      gap: 2px; flex-shrink: 0;
    }}
    .event-date-block.color-sthlm {{ background: #1a3a28; }}
    .event-date-block.color-gbg   {{ background: #1a2a45; }}
    .event-date-block.color-malm  {{ background: #3d1a14; }}

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

    /* ── CARD BODY ── */
    .event-card-body {{
      padding: 1rem 1.25rem;
      flex: 1; display: flex; flex-direction: column; gap: 6px;
    }}
    .event-tags {{ display: flex; gap: 6px; flex-wrap: wrap; }}
    .event-tag {{
      font-size: 9px; font-weight: 600; letter-spacing: 1px; text-transform: uppercase;
      padding: 3px 8px; border-radius: 10px;
    }}
    .tag-sthlm    {{ background: #C6EFCE; color: #276221; }}
    .tag-gbg      {{ background: #E8EEF5; color: #3a5a8c; }}
    .tag-malm     {{ background: #F7E8E4; color: #c25a47; }}
    .tag-10k      {{ background: #E8F4FD; color: #1565C0; }}
    .tag-11-20k   {{ background: #E8F4FD; color: #1565C0; }}
    .tag-half     {{ background: #E8F8EE; color: #1a6b3a; }}
    .tag-30k      {{ background: #FFF3CD; color: #856404; }}
    .tag-marathon {{ background: #FDECEA; color: #B71C1C; }}
    .tag-dist     {{ background: #F5F0FF; color: #5B2D8E; }}

    .event-title {{
      font-family: 'Oswald', sans-serif; font-weight: 700;
      font-size: 17px; text-transform: uppercase;
      letter-spacing: 0.5px; line-height: 1.2; color: #1C2A45;
    }}
    .event-location {{
      display: flex; align-items: center; gap: 5px;
      font-size: 12px; color: #999;
    }}
    .event-location svg {{ flex-shrink: 0; }}

    .event-card-footer {{
      padding: 0.75rem 1.25rem;
      border-top: 1px solid #F5EBE8;
      display: flex; justify-content: space-between; align-items: center;
    }}
    .event-distance {{
      font-size: 12px; font-weight: 600; color: #888; letter-spacing: 0.3px;
    }}
    .event-cta {{
      font-size: 11px; font-weight: 600; letter-spacing: 1px;
      text-transform: uppercase; color: #D4715E;
      display: flex; align-items: center; gap: 4px;
      transition: gap 0.2s;
    }}
    .event-card:hover .event-cta {{ gap: 8px; }}

    /* ── EMPTY STATE ── */
    .no-events {{
      grid-column: 1 / -1; text-align: center;
      padding: 4rem 1rem; color: #bbb;
    }}
    .no-events-icon {{ font-size: 48px; display: block; margin-bottom: 1rem; filter: grayscale(1) opacity(0.3); }}
    .no-events p {{ font-size: 15px; }}

    /* ── NEWSLETTER ── */
    .newsletter {{
      background: linear-gradient(135deg, #1C2A45 0%, #2a3d5e 100%);
      color: #FDFAF9; padding: 4rem 2rem;
      display: flex; align-items: center; justify-content: space-between;
      gap: 2rem; flex-wrap: wrap;
    }}
    .newsletter-label {{
      font-size: 10px; letter-spacing: 3px; text-transform: uppercase;
      color: #EEAA96; margin-bottom: 0.75rem; font-weight: 500;
    }}
    .newsletter-title {{
      font-family: 'Archivo Black', sans-serif; font-size: 26px;
      text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 0.5rem;
    }}
    .newsletter p {{ font-size: 14px; color: rgba(255,255,255,0.5); max-width: 400px; line-height: 1.7; }}
    .newsletter-form {{ display: flex; gap: 10px; flex-wrap: wrap; }}
    .newsletter-input {{
      padding: 14px 18px; border: 1px solid rgba(255,255,255,0.15);
      border-radius: 6px; font-size: 14px; font-family: 'DM Sans', sans-serif;
      color: #FDFAF9; background: rgba(255,255,255,0.08);
      outline: none; min-width: 260px; transition: border-color 0.2s;
    }}
    .newsletter-input::placeholder {{ color: rgba(255,255,255,0.3); }}
    .newsletter-input:focus {{ border-color: #EEAA96; }}
    .newsletter-btn {{
      background: #D4715E; color: #FDFAF9;
      font-size: 13px; font-weight: 600; letter-spacing: 1px; text-transform: uppercase;
      padding: 14px 32px; border-radius: 6px; border: none;
      cursor: pointer; font-family: 'DM Sans', sans-serif;
      transition: all 0.2s; white-space: nowrap;
    }}
    .newsletter-btn:hover {{ background: #C8604A; transform: translateY(-1px); }}

    /* ── FOOTER ── */
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
    .footer-updated {{
      font-size: 11px; color: #ccc; margin-top: 4px;
    }}

    /* ── FADE IN ── */
    .fade-in {{ opacity: 0; transform: translateY(20px); transition: opacity 0.6s ease, transform 0.6s ease; }}
    .fade-in.visible {{ opacity: 1; transform: translateY(0); }}

    /* ── MOBILE ── */
    @media (max-width: 768px) {{
      nav {{ padding: 1rem 1.25rem; }}
      .nav-links {{ display: none; }}
      .nav-toggle {{ display: flex; }}

      .page-header {{ padding: 3rem 1.25rem 2.5rem; }}
      .page-header h1 {{ font-size: clamp(32px, 10vw, 52px); }}

      .stats-bar {{ padding: 1rem 1.25rem; gap: 1.25rem; }}
      .stat-divider {{ display: none; }}

      .filters-bar {{ padding: 1rem 1.25rem; gap: 1rem; }}

      .events-layout {{ padding: 2rem 1.25rem; }}
      .events-grid {{ grid-template-columns: 1fr; }}

      .newsletter {{ padding: 3rem 1.25rem; flex-direction: column; align-items: flex-start; }}
      .newsletter-title {{ font-size: 22px; }}
      .newsletter-form {{ flex-direction: column; width: 100%; }}
      .newsletter-input {{ min-width: unset; width: 100%; }}
      .newsletter-btn {{ width: 100%; text-align: center; padding: 14px; }}

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
    <a href="/" class="logo">Swedish Run Clubs</a>
    <div class="nav-links">
      <a href="stockholm">Stockholm</a>
      <a href="goteborg">Göteborg</a>
      <a href="malmo">Malmö</a>
      <a href="kommande-events">Events</a>
      <a href="loppkalender" class="active">Lopp</a>
      <a href="nyheter">Nyheter</a>
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
    <a href="kommande-events">Events</a>
    <a href="loppkalender">Lopp</a>
    <a href="nyheter">Nyheter</a>
    <a href="om-oss">Om oss</a>
  </div>

  <main id="main-content">

  <!-- PAGE HEADER -->
  <header class="page-header">
    <div class="page-header-inner">
      <div class="page-header-tag">Löparkalendern</div>
      <h1>Kommande<br>Lopp</h1>
      <p>Tävlingar från 10 km upp till maraton — Stockholm, Göteborg och Malmö. Hitta ditt nästa lopp.</p>
    </div>
  </header>

  <!-- STATS BAR -->
  <div class="stats-bar">
    <div class="stat-item">
      <div>
        <div class="stat-number" id="stat-total">—</div>
        <div class="stat-label">Lopp totalt</div>
      </div>
    </div>
    <div class="stat-divider"></div>
    <div class="stat-item">
      <div>
        <div class="stat-number" id="stat-months">—</div>
        <div class="stat-label">Månader</div>
      </div>
    </div>
    <div class="stat-divider"></div>
    <div class="stat-item">
      <div>
        <div class="stat-number">3</div>
        <div class="stat-label">Regioner</div>
      </div>
    </div>
  </div>

  <!-- FILTERS -->
  <div class="filters-bar">
    <div class="filter-group">
      <span class="filter-label">Stad</span>
      <button class="filter-pill active" data-filter="region" data-value="all">Alla</button>
      <button class="filter-pill" data-filter="region" data-value="Stockholm">Stockholm</button>
      <button class="filter-pill" data-filter="region" data-value="Göteborg">Göteborg</button>
      <button class="filter-pill" data-filter="region" data-value="Malmö">Malmö</button>
    </div>
    <div class="filter-group">
      <span class="filter-label">Distans</span>
      <button class="filter-pill active" data-filter="dist" data-value="all">Alla</button>
      <button class="filter-pill" data-filter="dist" data-value="10k">10 km</button>
      <button class="filter-pill" data-filter="dist" data-value="11-20k">11–20 km</button>
      <button class="filter-pill" data-filter="dist" data-value="Halvmaraton">Halvmaraton</button>
      <button class="filter-pill" data-filter="dist" data-value="30k">30 km</button>
      <button class="filter-pill" data-filter="dist" data-value="Maraton">Maraton</button>
    </div>
  </div>

  <!-- RACES -->
  <div class="events-layout">
    <div id="races-container"></div>
  </div>

  <!-- NEWSLETTER -->
  <section class="newsletter fade-in">
    <div class="newsletter-text">
      <div class="newsletter-label">Nyhetsbrevet</div>
      <div class="newsletter-title">Missa inget lopp</div>
      <p>Nya tävlingar, loptips och run club-nyheter direkt i din inkorg.</p>
    </div>
    <form class="newsletter-form" onsubmit="return false;">
      <input type="email" class="newsletter-input" placeholder="din@email.se" aria-label="E-postadress">
      <button class="newsletter-btn">Prenumerera</button>
    </form>
  </section>

  </main>

  <!-- FOOTER -->
  <footer>
    <div class="footer-brand">
      <span class="logo">Swedish Run Clubs</span>
      <p>Alla run clubs i Sverige — sorterade, beskrivna och enkla att hitta.</p>
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
      <a href="kontakt">Kontakt</a>
      <a href="samarbeta">Samarbeta</a>
    </div>
    <div class="footer-bottom">
      &copy; 2026 Swedish Run Clubs. Byggd med kärlek av <a href="https://amandahultin.se" style="display:inline; margin:0;">Amanda Hultin</a>.
      <div class="footer-updated">Loppdatan uppdaterades {generated_at}.</div>
    </div>
  </footer>

  <script>
    // ─── DATA ────────────────────────────────────────────────────────────────────
    const races = {races_json};

    // ─── HELPERS ─────────────────────────────────────────────────────────────────
    const SV_MONTHS       = ['Januari','Februari','Mars','April','Maj','Juni',
                              'Juli','Augusti','September','Oktober','November','December'];
    const SV_MONTHS_SHORT = ['jan','feb','mar','apr','maj','jun',
                              'jul','aug','sep','okt','nov','dec'];
    const SV_DAYS         = ['Söndag','Måndag','Tisdag','Onsdag','Torsdag','Fredag','Lördag'];

    const REGION_COLOR = {{
      'Stockholm': 'color-sthlm',
      'Göteborg':  'color-gbg',
      'Malmö':     'color-malm',
    }};
    const REGION_TAG = {{
      'Stockholm': 'tag-sthlm',
      'Göteborg':  'tag-gbg',
      'Malmö':     'tag-malm',
    }};
    const DIST_TAG = {{
      '10k':         'tag-10k',
      '11-20k':      'tag-11-20k',
      'Halvmaraton': 'tag-half',
      '30k':         'tag-30k',
      'Maraton':     'tag-marathon',
    }};

    function parseDate(str) {{
      const [y, m, d] = str.split('-').map(Number);
      return new Date(y, m - 1, d);
    }}

    // ─── STATE ───────────────────────────────────────────────────────────────────
    let activeRegion = 'all';
    let activeDist   = 'all';

    // ─── CARD BUILDER ────────────────────────────────────────────────────────────
    function cardHTML(r) {{
      const d          = parseDate(r.date);
      const dayNum     = d.getDate();
      const monthAbbr  = SV_MONTHS_SHORT[d.getMonth()];
      const dayName    = SV_DAYS[d.getDay()].slice(0, 3);
      const colorClass = REGION_COLOR[r.region] || '';
      const regionTag  = REGION_TAG[r.region]   || '';
      const distTag    = DIST_TAG[r.dist_cat]    || 'tag-dist';
      const distLabel  = r.dist_cat || r.distance || 'Okänd distans';
      const location   = r.city || r.region;
      const hasLink    = r.link && r.link.trim() !== '';

      const inner = `
          <div class="event-card-top">
            <div class="event-date-block ${{colorClass}}" aria-hidden="true">
              <div class="event-day-num">${{dayNum}}</div>
              <div class="event-month-abbr">${{monthAbbr}}</div>
              <div class="event-day-name">${{dayName}}</div>
            </div>
            <div class="event-card-body">
              <div class="event-tags">
                <span class="event-tag ${{regionTag}}">${{r.region}}</span>
                <span class="event-tag ${{distTag}}">${{distLabel}}</span>
              </div>
              <div class="event-title">${{r.name}}</div>
              <div class="event-location">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
                ${{location}}
              </div>
            </div>
          </div>
          <div class="event-card-footer">
            <span class="event-distance">${{r.distance || '—'}}</span>
            ${{hasLink ? `<span class="event-cta">Officiell sida<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M12 5l7 7-7 7"/></svg></span>` : ''}}
          </div>`;

      if (hasLink) {{
        return `<a href="${{r.link}}" target="_blank" rel="noopener" class="event-card" aria-label="${{r.name}}, ${{dayNum}} ${{monthAbbr}}">${{inner}}</a>`;
      }} else {{
        return `<div class="event-card event-card--no-link" aria-label="${{r.name}}, ${{dayNum}} ${{monthAbbr}}">${{inner}}</div>`;
      }}
    }}

    // ─── RENDER ──────────────────────────────────────────────────────────────────
    function render() {{
      const container = document.getElementById('races-container');
      container.innerHTML = '';

      const filtered = races.filter(r => {{
        const regionOk = activeRegion === 'all' || r.region === activeRegion;
        const distOk   = activeDist === 'all'   || r.dist_cat === activeDist;
        return regionOk && distOk;
      }});

      // Group by month
      const byMonth = {{}};
      filtered.forEach(r => {{
        const d = parseDate(r.date);
        const key = d.getFullYear() + '-' + d.getMonth();
        if (!byMonth[key]) byMonth[key] = {{ label: SV_MONTHS[d.getMonth()] + ' ' + d.getFullYear(), races: [] }};
        byMonth[key].races.push(r);
      }});

      const monthKeys = Object.keys(byMonth);

      if (monthKeys.length === 0) {{
        container.innerHTML = `
          <div class="no-events">
            <span class="no-events-icon">🏅</span>
            <p>Inga lopp hittades med dessa filter.</p>
          </div>`;
      }} else {{
        monthKeys.forEach(key => {{
          const group = byMonth[key];
          const section = document.createElement('div');
          section.className = 'month-group';
          const count = group.races.length;
          section.innerHTML = `
            <div class="month-heading">
              <span class="month-name">${{group.label}}</span>
              <div class="month-line"></div>
              <span class="month-count">${{count}} lopp</span>
            </div>
            <div class="events-grid">${{group.races.map(cardHTML).join('')}}</div>
          `;
          container.appendChild(section);
        }});
      }}

      document.getElementById('stat-total').textContent  = filtered.length;
      document.getElementById('stat-months').textContent = monthKeys.length;
    }}

    // ─── FILTERS ─────────────────────────────────────────────────────────────────
    document.querySelectorAll('[data-filter]').forEach(btn => {{
      btn.addEventListener('click', function () {{
        const group = this.dataset.filter;
        const value = this.dataset.value;
        document.querySelectorAll(`[data-filter="${{group}}"]`).forEach(b => b.classList.remove('active'));
        this.classList.add('active');
        if (group === 'region') activeRegion = value;
        if (group === 'dist')   activeDist   = value;
        render();
      }});
    }});

    // ─── MOBILE MENU ─────────────────────────────────────────────────────────────
    const navToggle  = document.querySelector('.nav-toggle');
    const mobileMenu = document.querySelector('.mobile-menu');
    navToggle.addEventListener('click', function () {{
      const isOpen = mobileMenu.classList.toggle('open');
      navToggle.classList.toggle('open');
      navToggle.setAttribute('aria-expanded', isOpen);
      navToggle.setAttribute('aria-label', isOpen ? 'Stäng meny' : 'Öppna meny');
    }});

    // ─── FADE IN ─────────────────────────────────────────────────────────────────
    const observer = new IntersectionObserver(entries => {{
      entries.forEach(e => {{ if (e.isIntersecting) e.target.classList.add('visible'); }});
    }}, {{ threshold: 0 }});
    document.querySelectorAll('.fade-in').forEach(el => observer.observe(el));

    // ─── INIT ─────────────────────────────────────────────────────────────────────
    render();
  </script>
  <script src="newsletter.js"></script>
</body>
</html>
"""


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("loppkalender.html")

    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    if not sheet_id:
        log.error("GOOGLE_SHEET_ID environment variable not set")
        return 1

    records = fetch_races(sheet_id)
    races   = prepare_races(records)

    generated_at = datetime.now(timezone.utc).strftime("%-d %B %Y")
    html = render_html(races, generated_at)

    out_path.write_text(html, encoding="utf-8")
    log.info("Wrote %s (%d races)", out_path, len(races))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
