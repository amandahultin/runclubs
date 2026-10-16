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
KLUBBAR_WORKSHEET = "Klubbar"

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


# ── Free-text parsing (one-off migration only) ────────────────────────────────

_DAY_TOKEN = re.compile(r"\b(mån|tis|ons|tors?|fre|lör|sön)(?:dag(?:ar|en)?)?\b", re.I)
_DAY_INDEX = {"mån": 0, "tis": 1, "ons": 2, "tor": 3, "tors": 3, "fre": 4, "lör": 5, "sön": 6}
# A start time; the end of a range ("18:00–19:00") is skipped.
_TIME_TOKEN = re.compile(r"(?<![–\-\d:.])(\d{1,2})[:.](\d{2})(?!\d)")
_FILLER = re.compile(r"(?:\b(?:och|kl|samt)\b|[&,/+()\s.:–\-\d])", re.I)


def _days(text: str) -> list[int]:
    return [_DAY_INDEX[m.group(1).lower()] for m in _DAY_TOKEN.finditer(text)]


def _times(text: str) -> list[str]:
    out = []
    for m in _TIME_TOKEN.finditer(text):
        h, mi = int(m.group(1)), int(m.group(2))
        if h < 24 and mi < 60:
            out.append(f"{h:02d}:{mi:02d}")
    return out


def _leftover(text: str) -> str:
    return _FILLER.sub("", _DAY_TOKEN.sub("", text)).strip()


def parse_free_text(day_text: str, time_text: str) -> tuple[list[tuple[str, str]], str]:
    """Best-effort ([(Dag, HH:MM)], problem) from Träningsdag/Tid.

    problem is "" when the text was understood completely; otherwise it says
    why the row needs filling in by hand (and the slot list may be partial).
    """
    day_text, time_text = clean(day_text), clean(time_text)
    if not day_text and not time_text:
        return [], "inget schema angivet"
    if _leftover(day_text):
        return [], f"Träningsdag går inte att tolka: {day_text!r}"
    if _leftover(time_text):
        return [], f"Tid går inte att tolka: {time_text!r}"

    days = sorted(set(_days(day_text)))
    if not days:
        return [], f"ingen veckodag i Träningsdag: {day_text!r}"

    # Times tied to days within the Tid text itself ("Tis & Tor 18:30 / Sön 10:00").
    by_day: dict[int, list[str]] = {}
    loose: list[str] = []
    for seg in re.split(r"[/,]", time_text):
        seg_days, seg_times = _days(seg), _times(seg)
        if seg_days:
            for d in seg_days:
                by_day.setdefault(d, []).extend(seg_times)
        else:
            loose.extend(seg_times)

    slots: list[tuple[str, str]] = []
    if by_day:
        if loose:
            return [], f"Tid blandar dagar och lösa tider: {time_text!r}"
        for d in days:
            times = by_day.get(d, [])
            if len(times) != 1:
                return [], f"{DAY_NAMES[d]} har {len(times)} tider i {time_text!r}"
            slots.append((DAY_NAMES[d], times[0]))
    elif not loose:
        return [], "veckodag men ingen tid"
    elif len(loose) == 1:
        slots = [(DAY_NAMES[d], loose[0]) for d in days]
    elif len(loose) == len(days):
        # Positional: "Ons & Lör" / "18:00 / 09:00". Pair in the written order.
        written = list(dict.fromkeys(_days(day_text)))
        slots = [(DAY_NAMES[d], t) for d, t in zip(written, loose)]
    else:
        return [], f"{len(days)} dagar men {len(loose)} tider: {day_text!r} / {time_text!r}"

    if len(slots) > PASS_SLOTS:
        return slots[:PASS_SLOTS], f"fler än {PASS_SLOTS} pass"
    return slots, ""
