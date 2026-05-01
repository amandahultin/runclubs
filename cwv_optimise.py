"""cwv_optimise.py

Core Web Vitals pass — targets LCP < 1.2 s and TBT < 200 ms.

Changes applied to every HTML file that contains the GTM snippet:

1. GTM deferred  — inline snippet replaced with DOMContentLoaded +
   1 s setTimeout so gtm.js loads after LCP has painted.

2. Cookiebot cd.js deferred — moved from <head> to end of <body>
   with `defer`; already async but the <head> placement triggers an
   early third-party DNS lookup.

3. Google Fonts trimmed — 5 families → 2 (Archivo Black + DM Sans).
   Dropped: Inter italic 900, Oswald 500/700, Playfair Display 400.
   CSS font-family refs updated to fallbacks that are already loaded:
     Inter italic 900  → Archivo Black (faux italic via font-style)
     Playfair Display  → Georgia, serif
     Oswald            → DM Sans 700 / 600

Run from repo root:
    python3 cwv_optimise.py

Safe to re-run (idempotent).
"""

from __future__ import annotations
import re
from pathlib import Path

ROOT = Path(__file__).parent

# ── Patterns to identify & skip already-patched files ────────────────────────

GTM_OLD = '<!-- Google Tag Manager -->\n<script>(function(w,d,s,l,i)'
GTM_NEW_MARKER = '<!-- Google Tag Manager (deferred) -->'

COOKIEBOT_OLD_START = '<script\n  id="CookieDeclaration"'
COOKIEBOT_NEW_MARKER = 'id="CookieDeclaration"'   # present in both; check body position

# ── Replacement strings ───────────────────────────────────────────────────────

GTM_OLD_BLOCK = (
    '<!-- Google Tag Manager -->\n'
    '<script>(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({\'gtm.start\':\n'
    'new Date().getTime(),event:\'gtm.js\'});var f=d.getElementsByTagName(s)[0],\n'
    'j=d.createElement(s),dl=l!=\'dataLayer\'?\'&l=\'+l:\'\';j.async=true;j.src=\n'
    '\'https://www.googletagmanager.com/gtm.js?id=\'+i+dl;f.parentNode.insertBefore(j,f);\n'
    '})(window,document,\'script\',\'dataLayer\',\'GTM-TPSCMPZT\');</script>\n'
    '<!-- End Google Tag Manager -->'
)

GTM_NEW_BLOCK = (
    '<!-- Google Tag Manager (deferred) -->\n'
    '<script>\n'
    'window.dataLayer=window.dataLayer||[];\n'
    'window.dataLayer.push({\'gtm.start\':new Date().getTime(),event:\'gtm.js\'});\n'
    'document.addEventListener(\'DOMContentLoaded\',function(){\n'
    '  setTimeout(function(){\n'
    '    var s=document.createElement(\'script\');\n'
    '    s.async=true;\n'
    '    s.src=\'https://www.googletagmanager.com/gtm.js?id=GTM-TPSCMPZT\';\n'
    '    document.head.appendChild(s);\n'
    '  },1000);\n'
    '});\n'
    '</script>\n'
    '<!-- End Google Tag Manager -->'
)

# Cookiebot cd.js — old block to strip from <head>
COOKIEBOT_HEAD_BLOCK = (
    '<script\n'
    '  id="CookieDeclaration"\n'
    '  src="https://consent.cookiebot.com/c82ce3af-bded-4069-9aea-22493d3d7e2d/cd.js"\n'
    '  type="text/javascript"\n'
    '  async\n'
    '></script>\n'
)

# Cookiebot cd.js — compact deferred tag to append before </body>
COOKIEBOT_BODY_TAG = (
    '<script id="CookieDeclaration" '
    'src="https://consent.cookiebot.com/c82ce3af-bded-4069-9aea-22493d3d7e2d/cd.js" '
    'defer></script>\n'
)

# Google Fonts URL — old (5 families) → new (2 families)
FONTS_OLD = (
    'https://fonts.googleapis.com/css2?family=Archivo+Black'
    '&family=Inter:ital,wght@1,900'
    '&family=Oswald:wght@500;700'
    '&family=DM+Sans:wght@400;500;600'
    '&family=Playfair+Display:wght@400'
    '&display=swap'
)
FONTS_NEW = (
    'https://fonts.googleapis.com/css2?family=Archivo+Black'
    '&family=DM+Sans:wght@400;500;600'
    '&display=swap'
)

# Also handle variant orderings on some pages (DM Sans weight variant)
FONTS_OLD_ALT = (
    'https://fonts.googleapis.com/css2?family=Archivo+Black'
    '&family=Inter:ital,wght@1,900'
    '&family=Oswald:wght@500;700'
    '&family=DM+Sans:wght@400;500'
    '&family=Playfair+Display:wght@400'
    '&display=swap'
)

# CSS font-family replacements
CSS_FONT_SWAPS = [
    # Inter italic 900 → Archivo Black (faux italic; same weight, already loaded)
    (
        "font-family: 'Inter', sans-serif; font-weight: 900; font-style: italic;",
        "font-family: 'Archivo Black', sans-serif; font-style: italic;"
    ),
    # Playfair Display → Georgia system serif
    (
        "font-family: 'Playfair Display', serif; font-weight: 400; letter-spacing: -0.02em;",
        "font-family: Georgia, 'Times New Roman', serif; font-weight: 400; letter-spacing: -0.02em;"
    ),
    (
        "font-family: 'Playfair Display', serif; font-size: 0.45em; font-weight: 400;",
        "font-family: Georgia, 'Times New Roman', serif; font-size: 0.45em; font-weight: 400;"
    ),
    # Playfair Display without extra props
    (
        "font-family: 'Playfair Display', serif;",
        "font-family: Georgia, 'Times New Roman', serif;"
    ),
    # Oswald 700 → DM Sans 700
    (
        "font-family: 'Oswald', sans-serif; font-weight: 700;",
        "font-family: 'DM Sans', sans-serif; font-weight: 700;"
    ),
    # Oswald 500 → DM Sans 600
    (
        "font-family: 'Oswald', sans-serif; font-weight: 500;",
        "font-family: 'DM Sans', sans-serif; font-weight: 600;"
    ),
    # Oswald without explicit weight
    (
        "font-family: 'Oswald', sans-serif;",
        "font-family: 'DM Sans', sans-serif; font-weight: 700;"
    ),
]


# ── Per-file transform ────────────────────────────────────────────────────────

def transform(html: str) -> tuple[str, list[str]]:
    if GTM_OLD_BLOCK not in html:
        return html, []   # file doesn't have GTM at all — skip

    changes: list[str] = []
    already_deferred = GTM_NEW_MARKER in html

    # 1. Defer GTM
    if not already_deferred:
        html = html.replace(GTM_OLD_BLOCK, GTM_NEW_BLOCK, 1)
        changes.append("GTM deferred")

    # 2. Remove Cookiebot cd.js (Cookie Declaration widget — causes a visible
    #    "domain not authorised" error unless a <div id="CookieDeclaration">
    #    container exists on the page and the domain is registered in Cookiebot).
    #    The consent *banner* is loaded separately via GTM and is unaffected.
    if COOKIEBOT_HEAD_BLOCK in html:
        html = html.replace(COOKIEBOT_HEAD_BLOCK, '', 1)
        changes.append("Cookiebot cd.js removed")
    if COOKIEBOT_BODY_TAG in html:
        html = html.replace(COOKIEBOT_BODY_TAG, '', 1)
        changes.append("Cookiebot cd.js (body) removed")

    # 3. Trim Google Fonts request
    if FONTS_OLD in html:
        html = html.replace(FONTS_OLD, FONTS_NEW, 1)
        changes.append("Google Fonts trimmed (5→2 families)")
    elif FONTS_OLD_ALT in html:
        html = html.replace(FONTS_OLD_ALT, FONTS_NEW, 1)
        changes.append("Google Fonts trimmed (5→2 families, alt)")

    # 4. CSS font-family fallbacks
    for old, new in CSS_FONT_SWAPS:
        if old in html:
            n = html.count(old)
            html = html.replace(old, new)
            changes.append(f"font swap ×{n}: {old[:45].strip()!r}…")

    return html, changes


# ── Main ──────────────────────────────────────────────────────────────────────

def main(targets: list[Path] | None = None) -> None:
    """Apply CWV transforms.

    targets: specific files to process. When None, processes all HTML
             files in the repo (excluding drafts/mockups).
             Can also be driven from the CLI: python3 cwv_optimise.py a.html b.html
    """
    print("\n── Core Web Vitals pass ────────────────────────────────────")

    if targets is not None:
        files = [p for p in targets if p.exists()]
    else:
        skip = {'mockup-botanik', 'mockup-korall', 'mockup-lila', 'mockup-solsken',
                'index-feminine', 'index-feminine-v2', 'placeholder-preview', 'klubb'}
        files = [
            p for p in sorted(ROOT.rglob("*.html"))
            if p.stem not in skip and 'node_modules' not in str(p)
        ]

    updated = skipped = 0
    for path in files:
        html = path.read_text(encoding="utf-8")
        new_html, changes = transform(html)
        if changes:
            path.write_text(new_html, encoding="utf-8")
            rel = path.relative_to(ROOT)
            print(f"  ✓ {rel}")
            for c in changes:
                print(f"      · {c}")
            updated += 1
        else:
            skipped += 1

    print(f"\nDone. {updated} files updated, {skipped} skipped.\n")


if __name__ == "__main__":
    import sys
    cli_targets = [Path(a) for a in sys.argv[1:]] if sys.argv[1:] else None
    main(cli_targets)
