"""Generate stockholm-running-events.html from the running-clubs events Google Sheet.

Reads all rows from the Events worksheet (populated by mikaelsto/runclubs-events-feed),
filters to Stockholm upcoming events, and renders a self-contained HTML page matching
the runclubs.se design system.

Usage:
    python generate_stockholm_events.py                    # writes stockholm-running-events.html
    python generate_stockholm_events.py path/to/out.html   # custom output path
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

log = logging.getLogger(__name__)

EVENTS_SHEET_ID = "1DjQO84D3ihq-1VMOYZI6Q7WqC3mAdL-l0fRhZrwOFG4"
WORKSHEET_NAME  = "Events"

HEADERS = [
    "source", "club", "title", "date", "location",
    "description", "link", "image_url", "engagement", "fetched_at",
]

STOCKHOLM_KEYWORDS = {"stockholm"}


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
    log.info("Fetched %d rows from sheet", len(records))
    return records


def _parse_date(raw: str) -> datetime | None:
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.strip(), fmt)
        except (ValueError, AttributeError):
            continue
    return None


def prepare_events(records: list[dict]) -> list[dict]:
    today = datetime.now(timezone.utc).date()
    events: list[dict] = []

    for r in records:
        loc = (r.get("location") or "").lower()
        if not any(kw in loc for kw in STOCKHOLM_KEYWORDS):
            continue

        raw_date = (r.get("date") or "").strip()
        dt = _parse_date(raw_date)
        if dt is not None and dt.date() < today:
            continue

        events.append({
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

    events.sort(key=lambda x: (x["date"] or "9999", x["club"]))
    log.info("%d Stockholm upcoming events after filtering", len(events))
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
  <title>Stockholms Löparevent — Swedish Run Clubs</title>
  <meta name="description" content="Kommande grupplöpningar och events från Stockholms run clubs — Strava-events, Instagram-posts och tävlingar.">
  <meta property="og:title" content="Stockholms Löparevent — Swedish Run Clubs">
  <meta property="og:description" content="Kommande grupplöpningar och events från Stockholms run clubs.">
  <meta property="og:type" content="website">
  <meta property="og:url" content="https://runclubs.se/stockholm-running-events">
  <meta property="og:image" content="https://runclubs.se/stockholm-run-clubs.jpeg">
  <link rel="canonical" href="https://runclubs.se/stockholm-running-events">
  <link href="https://fonts.googleapis.com/css2?family=Archivo+Black&family=Oswald:wght@500;700&family=DM+Sans:wght@400;500;600&display=swap" rel="stylesheet">
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

    .events-layout {{ padding: 3rem 2rem; max-width: 1200px; margin: 0 auto; }}

    .date-group {{ margin-bottom: 3rem; }}
    .date-heading {{ display: flex; align-items: center; gap: 1rem; margin-bottom: 1.5rem; }}
    .date-name {{
      font-family: 'Archivo Black', sans-serif;
      font-size: 11px; letter-spacing: 3px; text-transform: uppercase; color: #bbb;
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
    .source-instagram {{ background: #C13584; color: #fff; }}
    .source-other     {{ background: #4a90d9; color: #fff; }}
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
      <a href="stockholm-running-events" class="active">Events</a>
      <a href="loppkalender">Lopp</a>
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
    <a href="stockholm-running-events">Events</a>
    <a href="loppkalender">Lopp</a>
    <a href="nyheter">Nyheter</a>
    <a href="om-oss">Om oss</a>
  </div>

  <main id="main-content">

  <header class="page-header">
    <div class="page-header-inner">
      <div class="page-header-tag">Stockholms run clubs</div>
      <h1>Kommande<br>Events</h1>
      <p>Grupplöpningar, intervaller och events från Stockholms run clubs — direkt från Strava och Instagram.</p>
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
        <div class="stat-label">Uppdateras varje vecka</div>
      </div>
    </div>
  </div>

  <div class="filters-bar">
    <div class="filter-group">
      <span class="filter-label">Källa</span>
      <button class="filter-pill active" data-filter="source" data-value="all">Alla</button>
      <button class="filter-pill" data-filter="source" data-value="strava">Strava</button>
      <button class="filter-pill" data-filter="source" data-value="instagram">Instagram</button>
    </div>
  </div>

  <div class="events-layout">
    <div id="events-container"></div>
  </div>

  <section class="newsletter fade-in">
    <div class="newsletter-text">
      <div class="newsletter-label">Nyhetsbrevet</div>
      <div class="newsletter-title">Missa inget event</div>
      <p>Nya grupplöp, events och run club-nyheter direkt i din inkorg.</p>
    </div>
    <form class="newsletter-form" onsubmit="return false;">
      <input type="email" class="newsletter-input" placeholder="din@email.se" aria-label="E-postadress">
      <button class="newsletter-btn">Prenumerera</button>
    </form>
  </section>

  </main>

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
      <div class="footer-updated">Eventdata uppdaterades {generated_at}.</div>
    </div>
  </footer>

  <script>
    const events = {events_json};

    const SV_MONTHS_SHORT = ['jan','feb','mar','apr','maj','jun','jul','aug','sep','okt','nov','dec'];
    const SV_DAYS         = ['Söndag','Måndag','Tisdag','Onsdag','Torsdag','Fredag','Lördag'];
    const SV_MONTHS       = ['Januari','Februari','Mars','April','Maj','Juni','Juli','Augusti','September','Oktober','November','December'];

    let activeSource = 'all';

    function parseDate(str) {{
      if (!str) return null;
      const d = new Date(str);
      return isNaN(d.getTime()) ? null : d;
    }}

    function sourceBadge(source) {{
      const cls   = source === 'strava' ? 'source-strava' : source === 'instagram' ? 'source-instagram' : 'source-other';
      const label = source === 'strava' ? 'Strava' : source === 'instagram' ? 'Instagram' : source;
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

      const ctaHTML = ev.link
        ? `<span class="event-cta">Se mer <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M12 5l7 7-7 7"/></svg></span>`
        : '';

      const inner = `
        ${{imageHTML}}
        <div class="event-card-top">
          ${{dateBlockHTML}}
          <div class="event-card-body">
            <div class="event-source-row">
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

      if (ev.link) {{
        return `<a href="${{ev.link}}" target="_blank" rel="noopener" class="event-card" aria-label="${{ev.title}}">${{inner}}</a>`;
      }} else {{
        return `<div class="event-card event-card--no-link" aria-label="${{ev.title}}">${{inner}}</div>`;
      }}
    }}

    function render() {{
      const container = document.getElementById('events-container');
      container.innerHTML = '';

      const filtered = events.filter(ev => activeSource === 'all' || ev.source === activeSource);

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

    const observer = new IntersectionObserver(entries => {{
      entries.forEach(e => {{ if (e.isIntersecting) e.target.classList.add('visible'); }});
    }}, {{ threshold: 0 }});
    document.querySelectorAll('.fade-in').forEach(el => observer.observe(el));

    render();
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

    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("stockholm-running-events.html")
    sheet_id = os.environ.get("GOOGLE_SHEET_ID") or EVENTS_SHEET_ID

    records = fetch_events(sheet_id)
    events  = prepare_events(records)

    generated_at = datetime.now(timezone.utc).strftime("%-d %B %Y")
    html_out = render_html(events, generated_at)

    out_path.write_text(html_out, encoding="utf-8")
    log.info("Wrote %s (%d events)", out_path, len(events))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
