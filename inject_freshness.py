"""inject_freshness.py

Adds "senast uppdaterad" freshness signals to club pages and city pages:

Club pages (29 migrated pages):
  • Visible: new info-strip item — "Uppdaterad / 1 maj 2026" with calendar icon
  • Structured: dateModified injected into SportsOrganization JSON-LD

City pages (stockholm.html, goteborg.html, malmo.html):
  • Visible: small <time> line between hero and events teaser
  • Structured: dateModified injected into CollectionPage JSON-LD

Run from repo root:
    python3 inject_freshness.py

Safe to re-run (idempotent).
"""

from __future__ import annotations
from pathlib import Path
import re, datetime

ROOT = Path(__file__).parent

# ── Date strings ──────────────────────────────────────────────────────────────

ISO_DATE   = "2026-05-01"
MONTHS_SV  = ["januari","februari","mars","april","maj","juni",
               "juli","augusti","september","oktober","november","december"]
d          = datetime.date.fromisoformat(ISO_DATE)
DISPLAY_SV = f"{d.day} {MONTHS_SV[d.month-1]} {d.year}"   # "1 maj 2026"


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

STRIP_ITEM = (
    f'\n    <div class="info-strip-item">\n'
    f'      <div class="info-strip-icon">{CALENDAR_ICON}</div>\n'
    f'      <div>\n'
    f'        <div class="info-strip-label">Uppdaterad</div>\n'
    f'        <div class="info-strip-value">'
    f'<time datetime="{ISO_DATE}">{DISPLAY_SV}</time>'
    f'</div>\n'
    f'      </div>\n'
    f'    </div>'
)

# Anchor: the last </div> that closes the info-strip wrapper
# The strip ends with the last info-strip-item then </div>
STRIP_CLOSE = '  </div>\n\n  \n\n  <style>'   # unique enough on club pages
STRIP_CLOSE_ALT = '  </div>\n\n  <style>'


def patch_club(html: str) -> tuple[str, list[str]]:
    changes: list[str] = []

    # Idempotency
    if f'datetime="{ISO_DATE}"' in html:
        return html, []

    # 1. Add info-strip item before the closing </div> of the strip
    # The strip's closing div is right before the <style> block that follows
    for anchor in (STRIP_CLOSE, STRIP_CLOSE_ALT):
        if anchor in html:
            html = html.replace(anchor, STRIP_ITEM + '\n  </div>\n\n  \n\n  <style>', 1)
            changes.append("info-strip: Uppdaterad item added")
            break
    else:
        # Fallback: find end of info-strip by locating the </div> just before <style>
        html = re.sub(
            r'(  </div>)\s*(<style>)',
            lambda m: STRIP_ITEM + '\n  </div>\n\n  <style>',
            html, count=1
        )
        if STRIP_ITEM in html:
            changes.append("info-strip: Uppdaterad item added (fallback)")

    # 2. dateModified in SportsOrganization JSON-LD
    if '"sameAs"' in html:
        html = html.replace(
            '"sameAs"',
            f'"dateModified": "{ISO_DATE}",\n  "sameAs"',
            1
        )
        changes.append("JSON-LD: dateModified added")
    elif '"sport": "Running"' in html:
        html = html.replace(
            '"sport": "Running"',
            f'"sport": "Running",\n  "dateModified": "{ISO_DATE}"',
            1
        )
        changes.append("JSON-LD: dateModified added (fallback)")

    return html, changes


# ── City pages ────────────────────────────────────────────────────────────────

# Small updated line injected between </header> and <!-- EVENTS TEASER -->
CITY_TIME_HTML = (
    f'\n  <p class="city-updated">Senast uppdaterad: '
    f'<time datetime="{ISO_DATE}">{DISPLAY_SV}</time></p>\n'
)

CITY_TIME_CSS = (
    '\n    .city-updated { text-align: center; font-size: 11px; letter-spacing: 0.5px; '
    'color: #aaa; padding: 0.75rem 0 0; margin: 0; }\n'
)


def patch_city(html: str) -> tuple[str, list[str]]:
    changes: list[str] = []

    if f'datetime="{ISO_DATE}"' in html:
        return html, []

    # 1. Inject CSS before </style> (first style block)
    if CITY_TIME_CSS.strip() not in html:
        html = html.replace('  </style>', CITY_TIME_CSS + '  </style>', 1)
        changes.append("CSS: .city-updated added")

    # 2. Inject time element between </header> and <!-- EVENTS TEASER -->
    anchor = '\n  <!-- EVENTS TEASER -->'
    if anchor in html:
        html = html.replace(anchor, CITY_TIME_HTML + '\n  <!-- EVENTS TEASER -->', 1)
        changes.append("HTML: <time> injected above events teaser")
    elif '\n  <!-- INTRO -->\n\n  <!-- EVENTS TEASER -->' in html:
        html = html.replace(
            '\n  <!-- INTRO -->\n\n  <!-- EVENTS TEASER -->',
            CITY_TIME_HTML + '\n  <!-- EVENTS TEASER -->',
            1
        )
        changes.append("HTML: <time> injected (intro anchor)")

    # 3. dateModified in CollectionPage JSON-LD
    if '"CollectionPage"' in html and f'"dateModified"' not in html:
        html = html.replace(
            '"isPartOf"',
            f'"dateModified": "{ISO_DATE}",\n    "isPartOf"',
            1
        )
        changes.append("JSON-LD: dateModified added to CollectionPage")

    return html, changes


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"\n── Injecting freshness date: {DISPLAY_SV} ({ISO_DATE}) ────────────")

    club_pages = (
        list(ROOT.glob("stockholm/*/index.html")) +
        list(ROOT.glob("goteborg/*/index.html")) +
        list(ROOT.glob("malmo/*/index.html"))
    )
    city_pages = [ROOT / f for f in ("stockholm.html", "goteborg.html", "malmo.html")]

    total = 0

    print("\n  Club pages:")
    for path in sorted(club_pages):
        html = path.read_text(encoding="utf-8")
        new_html, changes = patch_club(html)
        if changes:
            path.write_text(new_html, encoding="utf-8")
            print(f"    ✓ {path.relative_to(ROOT)}")
            total += 1
        else:
            print(f"    · {path.relative_to(ROOT)} (skipped)")

    print("\n  City pages:")
    for path in city_pages:
        html = path.read_text(encoding="utf-8")
        new_html, changes = patch_city(html)
        if changes:
            path.write_text(new_html, encoding="utf-8")
            print(f"    ✓ {path.relative_to(ROOT)}")
            for c in changes:
                print(f"        · {c}")
            total += 1
        else:
            print(f"    · {path.relative_to(ROOT)} (skipped)")

    print(f"\nDone. {total} files updated.\n")


if __name__ == "__main__":
    main()
