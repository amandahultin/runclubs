"""inject_freshness.py

Stamps every club page and city page with today's date — both as a
visible element and as dateModified in the JSON-LD structured data.

Club pages:
  • Info-strip item  "Uppdaterad / <today>" (calendar icon)
  • SportsOrganization JSON-LD  "dateModified": "<today>"

City pages:
  • Small <time> line between hero and events teaser
  • CollectionPage JSON-LD  "dateModified": "<today>"

First run: adds the elements from scratch.
Subsequent runs: replaces the existing date — never double-adds.

Run manually:
    python3 inject_freshness.py

Run automatically via .github/workflows/freshness.yml at 03:00 UTC.
"""

from __future__ import annotations
from pathlib import Path
import re, datetime

ROOT = Path(__file__).parent

# ── Date strings (always today in UTC) ───────────────────────────────────────

_today     = datetime.date.today()
ISO_DATE   = _today.isoformat()                       # "2026-05-02"
MONTHS_SV  = ["januari","februari","mars","april","maj","juni",
               "juli","augusti","september","oktober","november","december"]
DISPLAY_SV = f"{_today.day} {MONTHS_SV[_today.month-1]} {_today.year}"  # "2 maj 2026"

# ── Regex patterns that match any previously written date ────────────────────

# Matches <time datetime="YYYY-MM-DD">any text</time>
_TIME_RE = re.compile(r'<time datetime="\d{4}-\d{2}-\d{2}">[^<]*</time>')

# Matches "dateModified": "YYYY-MM-DD"
_DMOD_RE = re.compile(r'"dateModified":\s*"\d{4}-\d{2}-\d{2}"')

NEW_TIME = f'<time datetime="{ISO_DATE}">{DISPLAY_SV}</time>'
NEW_DMOD = f'"dateModified": "{ISO_DATE}"'


def _replace_dates(html: str) -> tuple[str, int]:
    """Replace any existing <time> and dateModified values. Returns (html, count)."""
    html, n1 = _TIME_RE.subn(NEW_TIME, html)
    html, n2 = _DMOD_RE.subn(NEW_DMOD, html)
    return html, n1 + n2


# ── Club pages ────────────────────────────────────────────────────────────────

CALENDAR_ICON = (
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" '
    'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
    'stroke-linejoin="round">'
    '<rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>'
    '<line x1="16" y1="2" x2="16" y2="6"/>'
    '<line x1="8" y1="2" x2="8" y2="6"/>'
    '<line x1="3" y1="10" x2="21" y2="10"/>'
    '</svg>'
)

_STRIP_ITEM = (
    f'\n    <div class="info-strip-item">\n'
    f'      <div class="info-strip-icon">{CALENDAR_ICON}</div>\n'
    f'      <div>\n'
    f'        <div class="info-strip-label">Uppdaterad</div>\n'
    f'        <div class="info-strip-value">{NEW_TIME}</div>\n'
    f'      </div>\n'
    f'    </div>'
)

_STRIP_ANCHORS = ('  </div>\n\n  \n\n  <style>', '  </div>\n\n  <style>')


def patch_club(html: str) -> tuple[str, list[str]]:
    changes: list[str] = []

    already_has_stamp = 'class="info-strip-label">Uppdaterad' in html

    if already_has_stamp:
        # UPDATE path — replace date in existing elements
        new_html, count = _replace_dates(html)
        if new_html == html:
            return html, []   # already today's date — nothing to do
        changes.append(f"updated date → {ISO_DATE}")
        return new_html, changes

    # FIRST-RUN path — inject from scratch

    # 1. Info-strip item
    for anchor in _STRIP_ANCHORS:
        if anchor in html:
            replacement = _STRIP_ITEM + '\n  </div>\n\n  \n\n  <style>'
            html = html.replace(anchor, replacement, 1)
            changes.append("info-strip: Uppdaterad item added")
            break

    # 2. dateModified in SportsOrganization JSON-LD
    if _DMOD_RE.search(html):
        # dateModified already present — replace in place (handles missed strip case)
        html, _ = _DMOD_RE.subn(NEW_DMOD, html)
        changes.append("JSON-LD: dateModified replaced (no strip)")
    elif '"sameAs"' in html:
        html = html.replace('"sameAs"',
                            f'"dateModified": "{ISO_DATE}",\n  "sameAs"', 1)
        changes.append("JSON-LD: dateModified added")
    elif '"sport": "Running"' in html:
        html = html.replace('"sport": "Running"',
                            f'"sport": "Running",\n  "dateModified": "{ISO_DATE}"', 1)
        changes.append("JSON-LD: dateModified added (fallback)")

    return html, changes


# ── City pages ────────────────────────────────────────────────────────────────

_CITY_CSS = (
    '\n    .city-updated { text-align: center; font-size: 11px; letter-spacing: 0.5px; '
    'color: #aaa; padding: 0.75rem 0 0; margin: 0; }\n'
)


def patch_city(html: str) -> tuple[str, list[str]]:
    changes: list[str] = []

    already_has_stamp = 'class="city-updated"' in html

    if already_has_stamp:
        # UPDATE path
        new_html, count = _replace_dates(html)
        if new_html == html:
            return html, []
        changes.append(f"updated date → {ISO_DATE}")
        return new_html, changes

    # FIRST-RUN path

    # 1. CSS (only once)
    if _CITY_CSS.strip() not in html:
        html = html.replace('  </style>', _CITY_CSS + '  </style>', 1)
        changes.append("CSS: .city-updated added")

    # 2. <time> element before events teaser
    city_time_html = (
        f'\n  <p class="city-updated">Senast uppdaterad: {NEW_TIME}</p>\n'
    )
    anchor = '\n  <!-- EVENTS TEASER -->'
    if anchor in html:
        html = html.replace(anchor, city_time_html + '\n  <!-- EVENTS TEASER -->', 1)
        changes.append("HTML: <time> injected")

    # 3. dateModified in CollectionPage JSON-LD
    if '"CollectionPage"' in html and '"dateModified"' not in html:
        html = html.replace('"isPartOf"',
                            f'"dateModified": "{ISO_DATE}",\n    "isPartOf"', 1)
        changes.append("JSON-LD: dateModified added")

    return html, changes


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"\n── Freshness stamp: {DISPLAY_SV} ({ISO_DATE}) ──────────────────────")

    club_pages = (
        list(ROOT.glob("stockholm/*/index.html")) +
        list(ROOT.glob("goteborg/*/index.html")) +
        list(ROOT.glob("ovriga-landet/*/index.html"))
    )
    city_pages = [ROOT / f for f in ("stockholm.html", "goteborg.html", "ovriga-landet.html")]

    total = 0

    print("\n  Club pages:")
    for path in sorted(club_pages):
        html      = path.read_text(encoding="utf-8")
        new_html, changes = patch_club(html)
        if changes:
            path.write_text(new_html, encoding="utf-8")
            print(f"    ✓ {path.relative_to(ROOT)}  ({', '.join(changes)})")
            total += 1
        else:
            print(f"    · {path.relative_to(ROOT)}  (already up to date)")

    print("\n  City pages:")
    for path in city_pages:
        html      = path.read_text(encoding="utf-8")
        new_html, changes = patch_city(html)
        if changes:
            path.write_text(new_html, encoding="utf-8")
            print(f"    ✓ {path.relative_to(ROOT)}  ({', '.join(changes)})")
            total += 1
        else:
            print(f"    · {path.relative_to(ROOT)}  (already up to date)")

    print(f"\nDone. {total} files updated.\n")


if __name__ == "__main__":
    main()
