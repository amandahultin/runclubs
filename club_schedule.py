"""Recurring club runs from the club sheet ("Klubbar").

The club sheet is the single source for weekly runs on /events. Each club row
carries up to three structured slots — Pass1_dag / Pass1_tid / Pass1_plats,
Pass2_…, Pass3_… — next to the free-text Träningsdag/Tid columns, which are
only for display on the club page and never parsed here.

build_weekly_records() turns those rows into records shaped like the old
WeeklyRuns worksheet (club, day_of_week, time, location, city, title,
description, link), so expand_weekly_runs() and the Overrides tab keep working
unchanged.
"""

from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)

KLUBBAR_SHEET_ID  = "1AsJZGQ8pLDreABBPpVus94ieWjyISBaCAiI4SKeCNDo"
# The club tab is gid 0 — the same tab generate_club.py exports as CSV.
KLUBBAR_WORKSHEET_ID = 0

PASS_SLOTS = 3
PASS_FIELDS = ("dag", "tid", "plats")
PASS_COLUMNS = [f"Pass{i}_{f}" for i in range(1, PASS_SLOTS + 1) for f in PASS_FIELDS]

DAY_NAMES = ["Måndag", "Tisdag", "Onsdag", "Torsdag", "Fredag", "Lördag", "Söndag"]

TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

SITE_URL = "https://runclubs.se"

# Region → (city on /events, URL folder). The site has pages for these three.
SITE_REGIONS = {
    "stockholm":     ("Stockholm",     "stockholm"),
    "göteborg":      ("Göteborg",      "goteborg"),
    "övriga landet": ("Övriga landet", "ovriga-landet"),
}
OVRIGA = SITE_REGIONS["övriga landet"]

# A club is shown unless Status says it shouldn't be. A blank Status still
# shows (and is logged) — every club in the sheet is meant to be live.
HIDDEN_STATUSES = {"utkast", "dold", "avpublicerad", "ej publicerad", "arkiverad"}


def clean(value: object) -> str:
    """Cell value with surrounding whitespace (incl. pasted newlines) removed."""
    return str(value or "").strip()


def rows_from_values(values: list[list[str]]) -> list[dict]:
    """Turn ws.get_all_values() into dicts keyed by stripped header.

    Not get_all_records(): that refuses sheets with blank or repeated headers.
    Each dict also gets "_row", the 1-based sheet row number.
    """
    if not values:
        return []
    headers = [clean(h) for h in values[0]]
    rows = []
    for n, raw in enumerate(values[1:], start=2):
        row = {h: (raw[i] if i < len(raw) else "") for i, h in enumerate(headers) if h}
        row["_row"] = n
        rows.append(row)
    return rows


def region_info(raw_region: str, club: str) -> tuple[str, str]:
    """(city, url folder) for a Region value. Never drops a club: anything the
    site has no page for is shown under Övriga landet, with a warning."""
    key = clean(raw_region).casefold()
    if key in SITE_REGIONS:
        return SITE_REGIONS[key]
    log.warning("Klubbar: %s har Region %r som sajten inte har en sida för — visas under Övriga landet",
                club, raw_region)
    return OVRIGA


def split_short_description(text: str) -> tuple[str, str]:
    """Title and description for a weekly-run card, both from Kort beskrivning:
    the first sentence becomes the title, the rest the description."""
    text = clean(text)
    m = re.match(r"(.+?[.!?])\s+(.+)$", text, re.S)
    if not m:
        return text, ""
    return m.group(1).strip(), m.group(2).strip()


def club_link(region_folder: str, slug: str) -> str:
    # Page folders are lowercase; Cloudflare paths are case-sensitive.
    return f"{SITE_URL}/{region_folder}/{clean(slug).lower()}/"


def is_hidden(row: dict) -> bool:
    return clean(row.get("Status")).casefold() in HIDDEN_STATUSES


def _dupe_key(text: str) -> str:
    """Loose key so "Rusa Running Club" and "rusa.running.club", or
    "Social Run Lund" and "Social Run Club Lund", count as the same club."""
    words = re.findall(r"[a-zåäö0-9]+", clean(text).casefold())
    return "".join(w for w in words if w not in {"club", "klubb"})


def validate(rows: list[dict]) -> None:
    """Log a warning for every data problem worth fixing in the sheet."""
    names: dict[str, list[int]] = {}
    slugs: dict[str, list[int]] = {}
    for r in rows:
        name = clean(r.get("Klubbnamn"))
        if not name:
            continue
        where = f"rad {r['_row']} ({name})"
        if not clean(r.get("Status")):
            log.warning("Klubbar: %s saknar Status", where)
        raw_slug = r.get("Slug") or ""
        if raw_slug != raw_slug.strip() or re.search(r"\s", raw_slug.strip()):
            log.warning("Klubbar: %s har whitespace i Slug: %r", where, raw_slug)
        elif raw_slug and not re.fullmatch(r"[a-z0-9-]+", raw_slug):
            log.warning("Klubbar: %s har Slug med versaler eller specialtecken: %r", where, raw_slug)
        if clean(r.get("Region")).casefold() not in SITE_REGIONS:
            log.warning("Klubbar: %s har Region %r utanför Stockholm/Göteborg/Övriga landet",
                        where, r.get("Region"))
        for i in range(1, PASS_SLOTS + 1):
            day = clean(r.get(f"Pass{i}_dag"))
            tid = clean(r.get(f"Pass{i}_tid"))
            if day and day.capitalize() not in DAY_NAMES:
                log.warning("Klubbar: %s Pass%d_dag okänd dag: %r", where, i, day)
            if tid and not TIME_RE.match(tid):
                log.warning("Klubbar: %s Pass%d_tid ogiltig tid (HH:MM): %r", where, i, tid)
            if bool(day) != bool(tid):
                log.warning("Klubbar: %s Pass%d har bara dag eller bara tid", where, i)
        names.setdefault(_dupe_key(name), []).append((r["_row"], name))
        if clean(raw_slug):
            slugs.setdefault(_dupe_key(raw_slug), []).append((r["_row"], clean(raw_slug)))
    for kind, seen in (("klubbnamn", names), ("slug", slugs)):
        for hits in seen.values():
            if len(hits) > 1:
                log.warning("Klubbar: möjlig dubblett (%s): %s", kind,
                            ", ".join(f"rad {n} {v!r}" for n, v in hits))


def build_weekly_records(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """(weekly records in WeeklyRuns shape, one info dict per shown club).

    The info dicts (club, city, link, slug) feed the club-page and club-city
    lookups that Strava and Special Events cards use.
    """
    validate(rows)
    records: list[dict] = []
    clubs: list[dict] = []
    for r in rows:
        name = clean(r.get("Klubbnamn"))
        if not name or is_hidden(r):
            continue
        city, folder = region_info(r.get("Region") or "", name)
        slug = clean(r.get("Slug"))
        link = club_link(folder, slug) if slug else ""
        clubs.append({"club": name, "city": city, "link": link, "slug": slug})

        title, description = split_short_description(r.get("Kort beskrivning") or "")
        fallback_place = clean(r.get("Stadsdel")) or clean(r.get("Stad"))
        for i in range(1, PASS_SLOTS + 1):
            day = clean(r.get(f"Pass{i}_dag"))
            tid = clean(r.get(f"Pass{i}_tid"))
            if not day and not tid:
                continue
            if day.capitalize() not in DAY_NAMES or not TIME_RE.match(tid):
                continue  # already warned in validate()
            records.append({
                "club":        name,
                "day_of_week": day.lower(),
                "time":        tid,
                "location":    clean(r.get(f"Pass{i}_plats")) or fallback_place,
                "city":        city,
                "title":       title,
                "description": description,
                "link":        link,
            })
    log.info("Klubbar: %d klubbar visas, %d återkommande pass", len(clubs), len(records))
    return records, clubs
