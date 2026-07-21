"""generate_club.py

Reads new-club rows from the "Nya klubbar" Google Sheet (CSV export) and
generates everything needed to add each club to runclubs.se:

  1. {region}/{slug}/index.html   -- the club page (from templates/club_page_template.html)
  2. A club-card block inserted into the region's city page (stockholm.html /
     goteborg.html / ovriga-landet.html)
  3. A root-level {slug}.html redirect stub (meta-refresh + JS replace)
  4. A "/​{slug} /{region}/{slug}/ 301" line appended to _redirects
  5. The three hardcoded club-count numbers (index.html city tile, city page
     hero-stat "Klubbar", city page results-count) + om-oss.html site total
  6. The new slug added to CITY_CLUBS in inject_rich_schemas.py, so the next
     scheduled run picks the club up into the city's ItemList schema

Idempotent: a row whose target page already exists is skipped, so it's safe
to re-run against the same sheet after adding more rows. sitemap.xml is NOT
touched here -- it regenerates automatically via the git pre-commit hook the
next time these changes are committed.

Not yet handled (skipped with a message): "Utan ort" = Ja (nationwide clubs
with no single city -- these still need a hand-built flat page, see
strawberry-run-club.html for the pattern).

Usage:
    python3 generate_club.py --dry-run                # preview, writes nothing
    python3 generate_club.py                            # generate + write
    python3 generate_club.py --force                    # regenerate existing pages too
    python3 generate_club.py --csv-file rows.csv         # read a local CSV instead of the sheet
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import urllib.request
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).parent
TEMPLATE_PATH = ROOT / "templates" / "club_page_template.html"
SHEET_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1AsJZGQ8pLDreABBPpVus94ieWjyISBaCAiI4SKeCNDo/export?format=csv&gid=0"
)

REGIONS = {
    "stockholm": {
        "label": "Stockholm",
        "city_page": ROOT / "stockholm.html",
        "match_names": {"stockholm"},
    },
    "goteborg": {
        "label": "Göteborg",
        "city_page": ROOT / "goteborg.html",
        "match_names": {"goteborg", "göteborg"},
    },
    "ovriga-landet": {
        "label": "Övriga landet",
        "city_page": ROOT / "ovriga-landet.html",
        "match_names": {"ovriga landet", "övriga landet"},
    },
}

INDEX_HTML = ROOT / "index.html"
OM_OSS_HTML = ROOT / "om-oss.html"
REDIRECTS_FILE = ROOT / "_redirects"
RICH_SCHEMAS_FILE = ROOT / "inject_rich_schemas.py"

SV_MONTHS = [
    "januari", "februari", "mars", "april", "maj", "juni",
    "juli", "augusti", "september", "oktober", "november", "december",
]


def normalize_url(url: str) -> str:
    url = url.strip()
    if url and not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    return url


def slugify(text: str) -> str:
    text = text.strip().lower()
    for a, b in [("å", "a"), ("ä", "a"), ("ö", "o"), ("é", "e"), ("ü", "u")]:
        text = text.replace(a, b)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def region_key_from_label(raw: str) -> str | None:
    norm = raw.strip().lower()
    for key, cfg in REGIONS.items():
        if norm in cfg["match_names"]:
            return key
    return None


def fetch_csv_rows(csv_url: str | None, csv_file: str | None) -> list[dict]:
    if csv_file:
        text = Path(csv_file).read_text(encoding="utf-8")
    else:
        with urllib.request.urlopen(csv_url) as resp:
            text = resp.read().decode("utf-8")
    return list(csv.DictReader(io.StringIO(text)))


def today_iso_and_sv() -> tuple[str, str]:
    # No wall-clock access here by design (called from a workflow-safe
    # context in some setups) -- but generate_club.py runs interactively,
    # so plain datetime is fine.
    import datetime
    d = datetime.date.today()
    return d.isoformat(), f"{d.day} {SV_MONTHS[d.month - 1]} {d.year}"


def build_same_as(instagram: str, strava: str, facebook: str) -> str:
    urls = [u for u in (instagram, strava, facebook) if u]
    return json.dumps(urls, ensure_ascii=False, indent=4).replace("\n", "\n  ")


def build_social_links_html(instagram: str, strava: str, facebook: str) -> str:
    blocks = []
    if instagram:
        blocks.append(f'''<a href="{instagram}" target="_blank" rel="noopener" class="instagram-cta">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 100 12.324 6.162 6.162 0 000-12.324zM12 16a4 4 0 110-8 4 4 0 010 8zm6.406-11.845a1.44 1.44 0 100 2.881 1.44 1.44 0 000-2.881z"/></svg>
          Följ på Instagram
          <span class="ig-arrow">&#8594;</span>
        </a>''')
    if strava:
        blocks.append(f'''<a href="{strava}" target="_blank" rel="noopener" class="strava-cta">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M15.387 17.944l-2.089-4.116h-3.065L15.387 24l5.15-10.172h-3.066m-7.008-5.599l2.836 5.598h4.172L10.463 0l-7 13.828h4.169"/></svg>
          Följ på Strava
          <span class="strava-arrow">&#8594;</span>
        </a>''')
    if facebook:
        blocks.append(f'''<a href="{facebook}" target="_blank" rel="noopener" class="facebook-cta">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M22 12a10 10 0 1 0-11.5 9.87v-6.98H7.9V12h2.6V9.8c0-2.56 1.52-3.98 3.87-3.98 1.12 0 2.3.2 2.3.2v2.5h-1.3c-1.28 0-1.68.8-1.68 1.62V12h2.85l-.46 2.89h-2.39v6.98A10 10 0 0 0 22 12z"/></svg>
          Följ på Facebook
          <span class="fb-arrow">&#8594;</span>
        </a>''')
    return "\n        ".join(blocks)


def split_leading_icon(item: str) -> tuple[str, str]:
    """If the item starts with an emoji/symbol token (e.g. "⏱️ Tidsbaserade
    pass"), use it as the icon and strip it from the display text -- matches
    the site convention of one icon living in the icon slot, not duplicated
    in the text. Falls back to a plain bullet for icon-less text."""
    m = re.match(r"^(\S+)\s+(.*)$", item)
    if m and not re.match(r"^\w+$", m.group(1), re.UNICODE):
        return m.group(1), m.group(2)
    return "•", item


def build_highlights_html(raw: str) -> str:
    items = [h.strip() for h in re.split(r"[;\n]", raw) if h.strip()]
    if not items:
        items = ["Följ klubben på Instagram för senaste infon"]
    icon_classes = ["coral", "blue", "green", "purple"]
    lines = []
    for i, item in enumerate(items):
        icon, text = split_leading_icon(item)
        icon_cls = icon_classes[i % len(icon_classes)]
        lines.append(
            f'          <li>\n'
            f'            <span class="highlight-icon {icon_cls}">{icon}</span>\n'
            f'            {text}\n'
            f'          </li>'
        )
    return "\n".join(lines)


def build_body_image_html(image_path: str, club_name: str) -> str:
    if not image_path:
        return ""
    alt = f"Löpare från {club_name} i action"
    return f'<img class="article-image" src="{image_path}" alt="{alt}" loading="lazy" decoding="async">'


def build_long_description_html(raw: str, body_image_html: str = "") -> str:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]
    if not paragraphs:
        return (
            "<p>Mer info om klubben kommer inom kort — under tiden är bästa "
            "sättet att hänga med att följa gruppen på Instagram eller "
            "Strava.</p>"
        )
    blocks = [f"<p>{paragraphs[0]}</p>"]
    if body_image_html:
        blocks.append(body_image_html)
    blocks.extend(f"<p>{p}</p>" for p in paragraphs[1:])
    return "\n\n      ".join(blocks)


def build_nav_link(href: str, label: str, active_key: str, current_region: str) -> str:
    active = ' class="active"' if active_key == current_region else ""
    return f'<a href="{href}"{active}>{label}</a>'


def build_hero_logo_block(logo_url: str) -> str:
    if not logo_url:
        return ""
    return (
        '<div class="hero-logo" aria-hidden="true">\n'
        f'      <img src="{logo_url}" alt="" loading="eager" decoding="async">\n'
        '    </div>'
    )


def schedule_summary(day: str, time: str) -> str:
    if day and time:
        return f"{day.capitalize()} {time}"
    if day:
        return day.capitalize()
    return "Se Instagram"


def build_club_page(row: dict, region_key: str) -> tuple[str, str]:
    """Returns (rendered_html, target_path_str)."""
    club_name = row["Klubbnamn"].strip()
    slug = (row.get("Slug") or "").strip() or slugify(club_name)
    city = row["Stad"].strip()
    short_description = row["Kort beskrivning"].strip()
    instagram = normalize_url(row.get("Instagram-URL", ""))
    strava = normalize_url(row.get("Strava-URL", ""))
    facebook = normalize_url(row.get("Facebook-URL", ""))
    hero_image = row["Hero-bild URL"].strip()
    logo_url = row.get("Logga URL", "").strip()
    schedule_day = row.get("Träningsdag", "").strip()
    schedule_time = row.get("Tid", "").strip()
    cost = row.get("Kostnad", "").strip() or "Se Instagram"
    niva = row.get("Nivå", "").strip() or "Nybörjare, Mellannivå, Avancerad"
    highlights_raw = row.get("Höjdpunkter", "").strip()
    long_description_raw = row.get("Lång beskrivning", "").strip()
    body_image_path = row.get("Bild i text", "").strip()
    hero_image_position = row.get("Hero-bild position", "").strip() or "center"

    region_label = REGIONS[region_key]["label"]
    region_url = f"https://runclubs.se/{region_key}"
    canonical_url = f"https://runclubs.se/{region_key}/{slug}/"
    date_iso, date_sv = today_iso_and_sv()

    club_name_words = club_name.split()
    club_short_name = club_name_words[0] if club_name_words else club_name

    tokens = {
        "TITLE": f"{club_name} {city} — Löparklubb i {city} | Runclubs.se",
        "META_DESCRIPTION": f"{club_name} i {city} — {short_description}",
        "SHORT_DESCRIPTION": short_description,
        "JSONLD_DESCRIPTION": short_description,
        "HERO_IMAGE_URL": hero_image,
        "HERO_IMAGE_POSITION": hero_image_position,
        "CANONICAL_URL": canonical_url,
        "CITY_URLENC": quote(f"{city}, Sverige"),
        "REGION_URL": region_url,
        "REGION_LABEL": region_label,
        "CLUB_NAME": club_name,
        "CLUB_NAME_URLENC": quote(club_name),
        "CLUB_SHORT_NAME": club_short_name,
        "CITY": city,
        "DATE_ISO": date_iso,
        "DATE_SV": date_sv,
        "SAME_AS_JSON": build_same_as(instagram, strava, facebook),
        "SOCIAL_LINKS_HTML": build_social_links_html(instagram, strava, facebook),
        "HIGHLIGHTS_HTML": build_highlights_html(highlights_raw),
        "LONG_DESCRIPTION_HTML": build_long_description_html(
            long_description_raw, build_body_image_html(body_image_path, club_name)
        ),
        "HERO_LOGO_BLOCK": build_hero_logo_block(logo_url),
        "SCHEDULE_DAY": schedule_day or "Se Instagram",
        "SCHEDULE_TIME": schedule_time or "Se Instagram",
        "COST": cost,
        "BREADCRUMB_REGION_LINK": f'<a href="/{region_key}">{region_label}</a><span class="sep">/</span>',
        "NAV_STOCKHOLM": build_nav_link("/stockholm", "Stockholm", "stockholm", region_key),
        "NAV_GOTEBORG": build_nav_link("/goteborg", "Göteborg", "goteborg", region_key),
        "NAV_OVRIGA": build_nav_link("/ovriga-landet", "Övriga landet", "ovriga-landet", region_key),
        "FOOTER_CITY_LINKS": (
            '<a href="/stockholm">Stockholm</a>\n      '
            '<a href="/goteborg">Göteborg</a>\n    '
            '<a href="/ovriga-landet">Övriga landet</a>'
        ),
    }

    html = TEMPLATE_PATH.read_text(encoding="utf-8")
    for key, value in tokens.items():
        html = html.replace("{{" + key + "}}", value)

    leftover = re.findall(r"\{\{[A-Z_]+\}\}", html)
    if leftover:
        raise ValueError(f"Untokenized placeholders left in output for {slug}: {sorted(set(leftover))}")

    target = ROOT / region_key / slug / "index.html"
    return html, str(target)


def build_card_image_html(club_name: str, hero_image: str, kort_bild: str) -> str:
    if kort_bild.strip().lower() == "foto" and hero_image:
        thumb = hero_image
        if "images.unsplash.com" in thumb:
            thumb = re.sub(r"w=\d+&h=\d+", "w=400&h=220", thumb)
        alt = f"Löpare från {club_name}"
        return (
            '<div class="card-image card-image--branded">\n'
            f'          <img src="{thumb}" alt="{alt}" loading="lazy" decoding="async" width="400" height="220">\n'
            '        </div>'
        )
    initial = club_name[0].upper() if club_name else "?"
    return (
        '<div class="card-image card-image--placeholder">\n'
        f'          <span class="placeholder-initial">{initial}</span>\n'
        f'          <span class="placeholder-tag">{club_name}</span>\n'
        '        </div>'
    )


def build_card_html(row: dict, region_key: str) -> str:
    club_name = row["Klubbnamn"].strip()
    slug = (row.get("Slug") or "").strip() or slugify(club_name)
    city = row["Stad"].strip()
    short_description = row["Kort beskrivning"].strip()
    schedule_day = row.get("Träningsdag", "").strip()
    schedule_time = row.get("Tid", "").strip()
    niva_raw = row.get("Nivå", "").strip()
    tags_raw = row.get("Typ/taggar", "").strip()
    hero_image = row.get("Hero-bild URL", "").strip()
    kort_bild = row.get("Kort-bild", "").strip()
    date_iso, _ = today_iso_and_sv()

    niva_attr = " ".join(slugify(n) for n in re.split(r"[;,]", niva_raw) if n.strip()) \
        or "nybörjare mellannivå avancerad"
    tags = [t.strip()[:1].upper() + t.strip()[1:] for t in re.split(r"[;,]", tags_raw) if t.strip()]
    typ_attr = " ".join(t.lower() for t in tags)
    dag_attr = slugify(schedule_day)[:3] if schedule_day else ""

    tags_html = "\n            ".join(
        f'<span class="card-tag tag-typ">{t}</span>' for t in tags
    ) or '<span class="card-tag tag-typ">Social</span>'

    if region_key == "ovriga-landet":
        location_attr = f'data-stad="{city.lower()}"'
        meta_prefix = city
    else:
        stadsdel = row.get("Stadsdel", "").strip() or city
        location_attr = f'data-stadsdel="{slugify(stadsdel)}"'
        meta_prefix = stadsdel

    meta = f"{meta_prefix} · {schedule_summary(schedule_day, schedule_time)}"
    card_image_html = build_card_image_html(club_name, hero_image, kort_bild)

    return f'''
      <a href="/{region_key}/{slug}/" class="club-card" data-niva="{niva_attr}" data-typ="{typ_attr}" data-dag="{dag_attr}" {location_attr}>
        {card_image_html}
        <div class="card-body">
          <div class="card-tags">
            {tags_html}
          </div>
          <div class="card-name">{club_name}</div>
          <div class="card-desc">{short_description}</div>
          <div class="card-meta">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
            {meta}
          </div>
          <div class="card-updated">Uppdaterad {date_iso}</div>
        </div>
      </a>
'''


def insert_card(city_page: Path, card_html: str) -> None:
    text = city_page.read_text(encoding="utf-8")
    anchor = '<div class="clubs-grid" id="clubs-grid">'
    if anchor not in text:
        raise ValueError(f"Could not find clubs-grid anchor in {city_page}")
    text = text.replace(anchor, anchor + card_html, 1)
    city_page.write_text(text, encoding="utf-8")


def write_redirect_stub(region_key: str, slug: str) -> None:
    stub_path = ROOT / f"{slug}.html"
    real_url = f"/{region_key}/{slug}/"
    stub_path.write_text(
        "<!DOCTYPE html>\n"
        '<html lang="sv">\n'
        "<head>\n"
        '<meta charset="UTF-8">\n'
        f'<meta http-equiv="refresh" content="0;url={real_url}">\n'
        f'<link rel="canonical" href="https://runclubs.se{real_url}">\n'
        "<title>Flyttad sida</title>\n"
        "</head>\n"
        "<body>\n"
        f'<script>window.location.replace("{real_url}");</script>\n'
        f'<p>Den här sidan har flyttat. <a href="{real_url}">Klicka här</a> om du inte skickas vidare automatiskt.</p>\n'
        '  <script src="/tracker.js" defer></script>\n'
        "</body>\n"
        "</html>\n",
        encoding="utf-8",
    )


def append_redirect(region_key: str, slug: str) -> None:
    line = f"/{slug} /{region_key}/{slug}/ 301\n"
    text = REDIRECTS_FILE.read_text(encoding="utf-8") if REDIRECTS_FILE.exists() else ""
    if line in text or f"/{slug} " in text:
        return
    REDIRECTS_FILE.write_text(text + line, encoding="utf-8")


def bump_index_city_count(region_key: str) -> None:
    label = REGIONS[region_key]["label"]
    text = INDEX_HTML.read_text(encoding="utf-8")
    pattern = re.compile(
        r'(<div class="city-name">' + re.escape(label) + r'</div>\s*<div class="city-count">\s*)(\d+)(\s*klubbar listade)'
    )
    new_text, n = pattern.subn(lambda m: m.group(1) + str(int(m.group(2)) + 1) + m.group(3), text)
    if n != 1:
        print(f"  WARNING: index.html city-count for {label} matched {n}x (expected 1) -- not updated")
        return
    INDEX_HTML.write_text(new_text, encoding="utf-8")


def bump_city_hero_stat(region_key: str) -> None:
    city_page = REGIONS[region_key]["city_page"]
    text = city_page.read_text(encoding="utf-8")
    pattern = re.compile(
        r'(<div class="hero-stat-number">)(\d+)(</div>\s*<div class="hero-stat-label">Klubbar</div>)'
    )
    new_text, n = pattern.subn(lambda m: m.group(1) + str(int(m.group(2)) + 1) + m.group(3), text)
    if n != 1:
        print(f"  WARNING: {city_page.name} hero-stat 'Klubbar' matched {n}x (expected 1) -- not updated")
        return
    text = new_text
    pattern2 = re.compile(r'(<span class="results-count">)(\d+)(</span>)')
    text, n2 = pattern2.subn(lambda m: m.group(1) + str(int(m.group(2)) + 1) + m.group(3), text, count=1)
    if n2 != 1:
        print(f"  WARNING: {city_page.name} results-count matched {n2}x (expected 1) -- not updated")
    city_page.write_text(text, encoding="utf-8")


def bump_om_oss_total() -> None:
    if not OM_OSS_HTML.exists():
        return
    text = OM_OSS_HTML.read_text(encoding="utf-8")
    pattern = re.compile(
        r'(<div class="info-strip-label">Klubbar</div>\s*<div class="info-strip-value">)(\d+)( run clubs</div>)'
    )
    new_text, n = pattern.subn(lambda m: m.group(1) + str(int(m.group(2)) + 1) + m.group(3), text, count=1)
    if n != 1:
        print(f"  WARNING: om-oss.html site-wide total matched {n}x (expected 1) -- not updated")
        return
    OM_OSS_HTML.write_text(new_text, encoding="utf-8")


def register_in_city_clubs(region_key: str, slug: str) -> None:
    if not RICH_SCHEMAS_FILE.exists():
        return
    text = RICH_SCHEMAS_FILE.read_text(encoding="utf-8")
    if f'"{slug}"' in text:
        return  # already registered
    anchor = f'"{region_key}": [\n'
    if anchor not in text:
        print(f"  WARNING: could not find CITY_CLUBS[\"{region_key}\"] in inject_rich_schemas.py")
        return
    text = text.replace(anchor, anchor + f'        "{slug}",\n', 1)
    RICH_SCHEMAS_FILE.write_text(text, encoding="utf-8")


def process_row(row: dict, dry_run: bool, force: bool) -> str:
    club_name = (row.get("Klubbnamn") or "").strip()
    if not club_name:
        return "skip: empty row"

    if (row.get("Utan ort") or "").strip().lower() in ("ja", "yes", "true"):
        return f"skip: {club_name} -- nationwide ('Utan ort') clubs aren't automated yet, build by hand"

    region_raw = (row.get("Region") or "").strip()
    region_key = region_key_from_label(region_raw)
    if not region_key:
        return f"skip: {club_name} -- unrecognized Region {region_raw!r} (expected Stockholm/Göteborg/Övriga landet)"

    if not (row.get("Hero-bild URL") or "").strip():
        return f"skip: {club_name} -- no Hero-bild URL, add one (verify it shows running before adding!)"
    if not (row.get("Kort beskrivning") or "").strip():
        return f"skip: {club_name} -- no Kort beskrivning"
    if not (row.get("Stad") or "").strip():
        return f"skip: {club_name} -- no Stad"

    slug = (row.get("Slug") or "").strip() or slugify(club_name)
    target = ROOT / region_key / slug / "index.html"
    if target.exists() and not force:
        return f"skip: {club_name} -- {target.relative_to(ROOT)} already exists (use --force to regenerate)"

    html, target_path = build_club_page(row, region_key)
    card_html = build_card_html(row, region_key)

    if dry_run:
        return f"WOULD CREATE: {club_name} -> {target_path} + card in {REGIONS[region_key]['city_page'].name} + redirects + counts"

    Path(target_path).parent.mkdir(parents=True, exist_ok=True)
    Path(target_path).write_text(html, encoding="utf-8")
    insert_card(REGIONS[region_key]["city_page"], card_html)
    write_redirect_stub(region_key, slug)
    append_redirect(region_key, slug)
    bump_index_city_count(region_key)
    bump_city_hero_stat(region_key)
    bump_om_oss_total()
    register_in_city_clubs(region_key, slug)

    return f"CREATED: {club_name} -> {target_path}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv-file", help="Read rows from a local CSV instead of the sheet")
    parser.add_argument("--csv-url", default=SHEET_CSV_URL)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="Regenerate even if the page already exists")
    args = parser.parse_args()

    rows = fetch_csv_rows(None if args.csv_file else args.csv_url, args.csv_file)
    print(f"Read {len(rows)} row(s) from {'local CSV' if args.csv_file else 'Google Sheet'}\n")

    for row in rows:
        try:
            result = process_row(row, args.dry_run, args.force)
        except Exception as exc:
            result = f"ERROR: {row.get('Klubbnamn', '?')} -- {exc}"
        print(result)


if __name__ == "__main__":
    main()
