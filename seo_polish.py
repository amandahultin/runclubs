"""seo_polish.py

Four targeted SEO passes across all pages:

1. HEADING ORDER   — fix H3→H2 for "Mötesplats" in club pages
2. INTERNAL LINKS  — make city name in related-section a link to city hub
3. HREFLANG        — add sv-SE + x-default <link> tags derived from canonical
4. IMAGE SEO       — add missing width/height on <img> tags that lack them

Run from repo root:
    python3 seo_polish.py

Safe to re-run (idempotent).
"""

from __future__ import annotations
import re
from pathlib import Path

ROOT     = Path(__file__).parent
BASE_URL = "https://runclubs.se"

# ─────────────────────────────────────────────────────────────────────────────
# File lists
# ─────────────────────────────────────────────────────────────────────────────

CLUB_PAGES = (
    list(ROOT.glob("stockholm/*/index.html")) +
    list(ROOT.glob("goteborg/*/index.html")) +
    list(ROOT.glob("malmo/*/index.html"))
)

# Top-level canonical pages (skip mockups, old flat club stubs, drafts)
TOP_LEVEL_PAGES = [
    ROOT / f
    for f in [
        "index.html",
        "stockholm.html", "goteborg.html", "malmo.html",
        "running-events.html",
        "stockholm-running-events.html",
        "goteborg-running-events.html",
        "malmo-running-events.html",
        "loppkalender.html",
        "nyheter.html",
        "om-oss.html",
        "kontakt.html",
        "samarbeta.html",
        "lopning-for-tjejer.html",
        "tjejer-tar-over-lopsparen.html",
        "stockholm-marathon-2026-slutsalt.html",
    ]
    if (ROOT / f).exists()
]

ALL_PAGES = TOP_LEVEL_PAGES + CLUB_PAGES

# City hub display names for internal links
CITY_DISPLAY = {"stockholm": "Stockholm", "goteborg": "Göteborg", "malmo": "Malmö"}


# ─────────────────────────────────────────────────────────────────────────────
# 1. HEADING ORDER — H3 → H2 for map section
# ─────────────────────────────────────────────────────────────────────────────

def fix_heading_order(html: str) -> str:
    """Change <h3>Mötesplats</h3> to <h2> and update its CSS selector."""
    # CSS selector
    html = html.replace(
        ".map-embed-section h3 {",
        ".map-embed-section h2 {"
    )
    # HTML tag (opening and closing)
    html = html.replace("<h3>Mötesplats</h3>", "<h2>Mötesplats</h2>")
    return html


# ─────────────────────────────────────────────────────────────────────────────
# 2. INTERNAL LINKS — city name in related section → hub link
# ─────────────────────────────────────────────────────────────────────────────

def fix_internal_links(html: str) -> str:
    """Turn plain city name in related-section label into a hub link."""
    for city, display in CITY_DISPLAY.items():
        old = f'Andra liknande löpargrupper i {display}</span>'
        new = (
            f'Andra liknande löpargrupper i '
            f'<a href="/{city}/" style="color:inherit;text-decoration:underline;'
            f'text-underline-offset:2px;">{display}</a></span>'
        )
        html = html.replace(old, new)
    return html


# ─────────────────────────────────────────────────────────────────────────────
# 3. HREFLANG — inject sv-SE + x-default after <link rel="canonical">
# ─────────────────────────────────────────────────────────────────────────────

HREFLANG_RE = re.compile(r'<link\s+rel=["\']alternate["\'][^>]+hreflang', re.IGNORECASE)
CANONICAL_RE = re.compile(r'<link\s+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\'][^>]*>', re.IGNORECASE)


def fix_hreflang(html: str) -> str:
    """Add hreflang tags if not already present, derived from canonical URL."""
    if HREFLANG_RE.search(html):
        return html  # already done

    m = CANONICAL_RE.search(html)
    if not m:
        return html  # no canonical to derive from

    url = m.group(1)
    tags = (
        f'\n  <link rel="alternate" hreflang="sv-SE" href="{url}">'
        f'\n  <link rel="alternate" hreflang="x-default" href="{url}">'
    )

    # Insert right after the canonical tag
    old = m.group(0)
    return html.replace(old, old + tags, 1)


# ─────────────────────────────────────────────────────────────────────────────
# 4. IMAGE SEO — add width/height to <img> tags that lack them
# ─────────────────────────────────────────────────────────────────────────────

# Images we know the dimensions of — keyed by src substring
KNOWN_DIMS: dict[str, tuple[int, int]] = {
    # News card images on homepage (CSS: aspect-ratio 16/9, rendered ~800px wide)
    "tjejer-och-run-clubs":           (800, 450),
    "run-clubs-stockholm-marathon":   (800, 450),
    "goteborg-run-clubs":             (800, 450),
    # Stockholm city page: run-collective card
    "runcollective.club.card":        (400, 220),
    # Unsplash club cards all use ?w=400&h=220
}

IMG_RE = re.compile(
    r'<img\b([^>]*?)(?<!\bwidth)(?<!\bheight)\s*(width|height)=["\'][^"\']*["\']|'
    r'<img\b([^>]*?)>',
    re.DOTALL
)

def _needs_dims(img_tag: str) -> bool:
    """True if this <img> is missing width or height."""
    return "width=" not in img_tag or "height=" not in img_tag

def _get_dims_for(src: str) -> tuple[int, int] | None:
    """Return (w, h) for known src substrings, or parse from Unsplash URL."""
    for key, dims in KNOWN_DIMS.items():
        if key in src:
            return dims
    # Unsplash: ?w=NNN&h=NNN
    m = re.search(r'[?&]w=(\d+).*?[?&]h=(\d+)', src)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r'[?&]h=(\d+).*?[?&]w=(\d+)', src)
    if m:
        return int(m.group(2)), int(m.group(1))
    return None

def fix_images(html: str) -> str:
    """Add width and height attributes to <img> tags that are missing them."""
    def patch_img(m: re.Match) -> str:
        tag = m.group(0)
        if not _needs_dims(tag):
            return tag
        # Extract src
        src_m = re.search(r'\bsrc=["\']([^"\']*)["\']', tag)
        if not src_m:
            return tag
        dims = _get_dims_for(src_m.group(1))
        if not dims:
            return tag
        w, h = dims
        # Inject before closing >
        additions = ""
        if "width=" not in tag:
            additions += f' width="{w}"'
        if "height=" not in tag:
            additions += f' height="{h}"'
        return tag[:-1] + additions + ">"

    return re.sub(r'<img\b[^>]*>', patch_img, html, flags=re.DOTALL)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def process(path: Path, is_club: bool) -> tuple[str, int]:
    html  = path.read_text(encoding="utf-8")
    orig  = html
    steps = 0

    if is_club:
        h2 = fix_heading_order(html)
        if h2 != html:
            html = h2
            steps += 1

        h3 = fix_internal_links(html)
        if h3 != html:
            html = h3
            steps += 1

    h4 = fix_hreflang(html)
    if h4 != html:
        html = h4
        steps += 1

    h5 = fix_images(html)
    if h5 != html:
        html = h5
        steps += 1

    if html != orig:
        path.write_text(html, encoding="utf-8")
    return ("ok" if html != orig else "skip"), steps


def main() -> None:
    print("\n── SEO polish pass ─────────────────────────────────────────")

    total_files = total_steps = 0

    print("\n  Club pages:")
    for p in sorted(CLUB_PAGES):
        status, steps = process(p, is_club=True)
        rel = p.relative_to(ROOT)
        icon = "✓" if status == "ok" else "·"
        print(f"    {icon} {rel}  ({steps} changes)")
        if status == "ok":
            total_files += 1
            total_steps += steps

    print("\n  Top-level pages:")
    for p in sorted(TOP_LEVEL_PAGES):
        status, steps = process(p, is_club=False)
        rel = p.relative_to(ROOT)
        icon = "✓" if status == "ok" else "·"
        print(f"    {icon} {rel}  ({steps} changes)")
        if status == "ok":
            total_files += 1
            total_steps += steps

    print(f"\nDone. {total_files} files updated, {total_steps} total changes.\n")


if __name__ == "__main__":
    main()
