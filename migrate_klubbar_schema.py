"""One-off: fill the Pass1–3 schedule columns in the club sheet ("Klubbar").

Sources, highest priority first:
  1. CORRECTIONS below — schedules Amanda confirmed by hand
  2. the WeeklyRuns tab in the events sheet — what /events shows today
  3. the free-text Träningsdag/Tid columns, where they parse unambiguously

Slots that are already filled in the sheet are never overwritten.

Usage:
    python migrate_klubbar_schema.py                 # preview only, writes nothing
    python migrate_klubbar_schema.py --apply         # write the previewed changes
    python migrate_klubbar_schema.py --out-dir DIR   # where the preview files go

The preview is written to DIR/klubbar-preview.md (diff + rows to fill by hand)
and DIR/klubbar-preview.csv (every club with its proposed slots).
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import re
import sys
from pathlib import Path

from club_schedule import (
    DAY_NAMES,
    KLUBBAR_SHEET_ID,
    KLUBBAR_WORKSHEET_ID,
    PASS_COLUMNS,
    PASS_SLOTS,
    clean,
    parse_free_text,
    rows_from_values,
)
from events_common import (
    DAYS_MAP,
    EVENTS_SHEET_ID,
    _link_slug,
    _sheet_client,
    fetch_weekly_runs,
    normalize_club_name,
)

log = logging.getLogger(__name__)

# Schedules confirmed by Amanda, keyed by Slug: [(Dag, HH:MM, plats or None)].
# None keeps the location from WeeklyRuns.
CORRECTIONS = {
    "solemates-runclub":        [("Tisdag", "07:00", "Strandvägen")],
    "saucony-run-club-sverige": [("Onsdag", "06:45", None)],
}

# Cell fixes confirmed by Amanda: (column, current value, new value).
CELL_FIXES = [
    ("Region", "Luleå ", "Luleå"),
    ("Slug", "social-run-landskorna ", "social-run-landskrona"),
]

_DAY_ORDER = {d: i for i, d in enumerate(DAY_NAMES)}


def match_weekly(rows: list[dict], weekly: list[dict]) -> tuple[dict[int, list[dict]], list[dict]]:
    """{sheet row: [WeeklyRuns rows]} and the WeeklyRuns rows that matched no club.

    Matched on exact name, then on the alias-normalised name, then on the
    slug in the WeeklyRuns link.
    """
    exact = {clean(r.get("Klubbnamn")).casefold(): r["_row"] for r in rows}
    normal: dict[str, int] = {}
    for r in rows:
        normal.setdefault(normalize_club_name(clean(r.get("Klubbnamn"))).casefold(), r["_row"])
    by_slug = {clean(r.get("Slug")).casefold(): r["_row"] for r in rows if clean(r.get("Slug"))}

    matched: dict[int, list[dict]] = {}
    unmatched: list[dict] = []
    for w in weekly:
        name = clean(w.get("club"))
        row = (exact.get(name.casefold())
               or normal.get(normalize_club_name(name).casefold())
               or by_slug.get(_link_slug(w.get("link") or "")))
        if row:
            matched.setdefault(row, []).append(w)
        else:
            unmatched.append(w)
    return matched, unmatched


def _weekly_slots(ws_rows: list[dict]) -> tuple[list[tuple[str, str, str]], str]:
    slots, problems = [], []
    for w in ws_rows:
        raw_day = clean(w.get("day_of_week"))
        day = DAY_NAMES[DAYS_MAP[raw_day.lower()]] if raw_day.lower() in DAYS_MAP else raw_day
        tid = clean(w.get("time"))
        if re.fullmatch(r"\d:\d\d", tid):
            tid = "0" + tid
        if day not in _DAY_ORDER or not re.fullmatch(r"\d\d:\d\d", tid):
            problems.append(f"WeeklyRuns-rad går inte att tolka: {day!r} {tid!r}")
            continue
        slots.append((day, tid, clean(w.get("location"))))
    slots.sort(key=lambda s: (_DAY_ORDER[s[0]], s[1]))
    return slots, "; ".join(problems)


def propose(rows: list[dict], weekly: list[dict]) -> tuple[list[dict], list[dict]]:
    """One plan dict per club row, plus WeeklyRuns rows that matched no club."""
    matched, unmatched = match_weekly(rows, weekly)
    plans = []
    for r in rows:
        name = clean(r.get("Klubbnamn"))
        if not name:
            continue
        slug = clean(r.get("Slug")).casefold()
        free, free_problem = parse_free_text(r.get("Träningsdag") or "", r.get("Tid") or "")
        weekly_slots, weekly_problem = _weekly_slots(matched.get(r["_row"], []))

        notes = []
        if slug in CORRECTIONS:
            source = "korrigering"
            loc = {s[0]: s[2] for s in weekly_slots}
            slots = [(d, t, p if p is not None else loc.get(d, "")) for d, t, p in CORRECTIONS[slug]]
        elif weekly_slots:
            source = "WeeklyRuns"
            slots = weekly_slots
            if free and [(d, t) for d, t, _ in slots] != free:
                notes.append("fritexten säger " + ", ".join(f"{d} {t}" for d, t in free))
        elif free:
            source = "Träningsdag/Tid"
            slots = [(d, t, "") for d, t in free]
        else:
            source = ""
            slots = []
        if weekly_problem:
            notes.append(weekly_problem)
        if len(slots) > PASS_SLOTS:
            notes.append(f"{len(slots)} pass, bara {PASS_SLOTS} får plats")
            slots = slots[:PASS_SLOTS]

        needs_hand = not slots and free_problem != "inget schema angivet"
        plans.append({
            "row": r, "name": name, "source": source, "slots": slots,
            "notes": notes, "free_problem": free_problem if not slots else "",
            "needs_hand": needs_hand,
        })
    return plans, unmatched


def cell_changes(rows: list[dict], plans: list[dict]) -> tuple[list[tuple], list[str]]:
    """[(sheet row, column, before, after)] and notes on kept existing values."""
    changes, kept = [], []
    for p in plans:
        r = p["row"]
        proposed = {}
        for i, (d, t, pl) in enumerate(p["slots"], start=1):
            proposed.update({f"Pass{i}_dag": d, f"Pass{i}_tid": t, f"Pass{i}_plats": pl})
        for col in PASS_COLUMNS:
            before, after = r.get(col, ""), proposed.get(col, "")
            if not after or before == after:
                continue
            if clean(before):
                kept.append(f"rad {r['_row']} {p['name']}: {col} = {before!r} behålls (förslag {after!r})")
                continue
            changes.append((r["_row"], col, before, after))
    for r in rows:
        for col, old, new in CELL_FIXES:
            if r.get(col) == old:
                changes.append((r["_row"], col, old, new))
    return changes, kept


def write_preview(out_dir: Path, plans, unmatched, changes, kept, has_columns: bool) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "klubbar-preview.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Rad", "Klubbnamn", "Slug", "Källa", *PASS_COLUMNS, "Not"])
        for p in plans:
            cells = []
            for i in range(PASS_SLOTS):
                cells.extend(p["slots"][i] if i < len(p["slots"]) else ("", "", ""))
            w.writerow([p["row"]["_row"], p["name"], clean(p["row"].get("Slug")), p["source"],
                        *cells, "; ".join(p["notes"] + ([p["free_problem"]] if p["free_problem"] else []))])

    md = ["# Förhandsvisning: schemakolumner i Klubbar", ""]
    if not has_columns:
        md += [f"Kolumnerna {', '.join(PASS_COLUMNS)} läggs till sist i arket. "
               "Dag får en dropdown (Måndag–Söndag), tid formateras som text med validering HH:MM.", ""]
    md += [f"## Ändringar ({len(changes)} celler)", "", "| Rad | Kolumn | Före | Efter |", "|---|---|---|---|"]
    md += [f"| {row} | {col} | `{before!r}` | `{after!r}` |" for row, col, before, after in changes]

    md += ["", "## Pass per klubb", "", "| Rad | Klubb | Källa | Pass | Not |", "|---|---|---|---|---|"]
    for p in plans:
        if p["slots"]:
            passes = "<br>".join(f"{d} {t}" + (f" · {pl}" if pl else "") for d, t, pl in p["slots"])
            md.append(f"| {p['row']['_row']} | {p['name']} | {p['source']} | {passes} | {'; '.join(p['notes'])} |")

    md += ["", "## Behöver fyllas i för hand", ""]
    md += [f"- rad {p['row']['_row']} **{p['name']}**: {p['free_problem']}" for p in plans if p["needs_hand"]]
    md += ["", "## Inget schema alls i arket", ""]
    md += [f"- rad {p['row']['_row']} {p['name']}" for p in plans
           if not p["slots"] and not p["needs_hand"]]
    if kept:
        md += ["", "## Redan ifyllt — skrivs inte över", ""] + [f"- {k}" for k in kept]
    md += ["", "## WeeklyRuns-rader utan klubb i Klubbar", ""]
    md += [f"- {clean(w.get('club'))} ({clean(w.get('day_of_week'))} {clean(w.get('time'))}, {clean(w.get('link'))})"
           for w in unmatched] or ["- inga"]
    path = out_dir / "klubbar-preview.md"
    path.write_text("\n".join(md) + "\n", encoding="utf-8")
    return path


def _col_letter(n: int) -> str:
    s = ""
    while n:
        n, rem = divmod(n - 1, 26)
        s = chr(65 + rem) + s
    return s


def apply(sh, ws, headers: list[str], changes: list[tuple]) -> None:
    headers = list(headers)
    missing = [c for c in PASS_COLUMNS if c not in headers]
    if missing:
        last = max((i for i, h in enumerate(headers) if h), default=-1)
        headers = headers[:last + 1] + missing
        if ws.col_count < len(headers):
            ws.add_cols(len(headers) - ws.col_count)
        start = last + 2
        ws.update(range_name=f"{_col_letter(start)}1:{_col_letter(start + len(missing) - 1)}1",
                  values=[missing], value_input_option="RAW")
        log.info("Lade till kolumnerna %s", ", ".join(missing))

    col_index = {h: i + 1 for i, h in enumerate(headers)}
    requests = []
    for col in PASS_COLUMNS:
        c = col_index[col] - 1
        rng = {"sheetId": ws.id, "startRowIndex": 1, "endRowIndex": ws.row_count,
               "startColumnIndex": c, "endColumnIndex": c + 1}
        if col.endswith("_dag"):
            rule = {"condition": {"type": "ONE_OF_LIST",
                                  "values": [{"userEnteredValue": d} for d in DAY_NAMES]},
                    "strict": True, "showCustomUi": True}
        elif col.endswith("_tid"):
            requests.append({"repeatCell": {
                "range": rng, "fields": "userEnteredFormat.numberFormat",
                "cell": {"userEnteredFormat": {"numberFormat": {"type": "TEXT"}}}}})
            ref = f"{_col_letter(c + 1)}2"
            rule = {"condition": {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue":
                        f'=OR(ISBLANK({ref}),REGEXMATCH(TO_TEXT({ref}),"^([01][0-9]|2[0-3]):[0-5][0-9]$"))'}]},
                    "strict": True, "inputMessage": "Tid i formatet HH:MM, t.ex. 18:30"}
        else:
            continue
        requests.append({"setDataValidation": {"range": rng, "rule": rule}})
    sh.batch_update({"requests": requests})
    log.info("Satte dropdown och tidsvalidering")

    data = [{"range": f"{_col_letter(col_index[col])}{row}", "values": [[after]]}
            for row, col, _, after in changes]
    if data:
        ws.batch_update(data, value_input_option="RAW")
    log.info("Skrev %d celler", len(data))


def main() -> int:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write the changes to the sheet")
    ap.add_argument("--out-dir", default="klubbar-preview")
    args = ap.parse_args()

    sh = _sheet_client().open_by_key(KLUBBAR_SHEET_ID)
    ws = sh.get_worksheet_by_id(KLUBBAR_WORKSHEET_ID)
    log.info("Klubbflik: %r", ws.title)
    values = ws.get_all_values()
    headers = [clean(h) for h in values[0]]
    rows = rows_from_values(values)
    weekly = fetch_weekly_runs(os.environ.get("GOOGLE_SHEET_ID") or EVENTS_SHEET_ID)

    plans, unmatched = propose(rows, weekly)
    changes, kept = cell_changes(rows, plans)
    path = write_preview(Path(args.out_dir), plans, unmatched, changes, kept,
                         has_columns=all(c in headers for c in PASS_COLUMNS))
    print(path.read_text(encoding="utf-8"))

    if args.apply:
        apply(sh, ws, headers, changes)
    else:
        log.info("Förhandsläge — inget skrivet till arket")
    return 0


if __name__ == "__main__":
    sys.exit(main())
