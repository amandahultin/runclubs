"""migrate_club_urls.py

Migrates club pages from flat /slug URLs to city-scoped /city/slug/ structure.

For each club:
  1. Creates {city}/{slug}/index.html with transformed HTML
     - All relative asset/page URLs made absolute
     - canonical, og:url, JSON-LD urls updated
     - BreadcrumbList updated
     - Embedded Google Maps iframe added
  2. Adds 301 redirect from old URL in _redirects
  3. Updates internal links on city pages

Run from repo root:
    python3 migrate_club_urls.py

Safe to re-run (idempotent).
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from urllib.parse import quote

ROOT     = Path(__file__).parent
BASE_URL = "https://runclubs.se"

# ── City → clubs mapping ──────────────────────────────────────────────────────

CITY_CLUBS: dict[str, list[str]] = {
    "stockholm": [
        "stockholm-run-club", "dopest-runners", "rtc", "triple-threshold-rc",
        "burgers-n-brew-run-crew", "zlk-zinken-lopklubb", "soderloparna-stockholm",
        "runday", "run-collective-stockholm", "mikkeller-running-club-sthlm",
        "running-around-club", "mellqvist-run-club", "slowrunners-sthlm",
        "svedjans-lopsallskap", "andmorerunning", "hogdalen-run-club",
        "pulse-pacers", "solemates-runclub", "saucony-run-club-sverige",
        "stadium-run-club", "tjejmilen-runclub",
    ],
    "goteborg": [
        "goteborg-running-club", "sweden-runners-goteborg", "aero-boys-club",
        "east-run-club", "slowrunners-goteborg", "she-runs-club",
        "core-run-club", "ess-runners-club",
    ],
    "malmo": [
        "mrc-malmo", "sweden-runners-malmo",
    ],
}

# Reverse map: slug → city
SLUG_TO_CITY: dict[str, str] = {
    slug: city
    for city, slugs in CITY_CLUBS.items()
    for slug in slugs
}

# New canonical URL for a club slug
def new_url(slug: str) -> str:
    city = SLUG_TO_CITY.get(slug, "")
    return f"{BASE_URL}/{city}/{slug}/" if city else f"{BASE_URL}/{slug}"

def new_path(slug: str) -> str:
    city = SLUG_TO_CITY.get(slug, "")
    return f"/{city}/{slug}/" if city else f"/{slug}"

# Top-level non-club pages (relative links to keep as absolute but non-city-scoped)
TOP_LEVEL = {
    "stockholm", "goteborg", "malmo", "nyheter", "running-events",
    "stockholm-running-events", "goteborg-running-events", "malmo-running-events",
    "loppkalender", "om-oss", "kontakt", "samarbeta", "lopning-for-tjejer",
    "tjejer-tar-over-lopsparen", "stockholm-marathon-2026-slutsalt",
}

ASSET_RE = re.compile(
    r'\.(jpg|jpeg|webp|png|gif|svg|ico|woff2|woff|js|css)$', re.IGNORECASE
)


# ── HTML transformation ───────────────────────────────────────────────────────

def abs_href(href: str) -> str:
    """Convert a relative href to an absolute path."""
    if not href or href.startswith(('http', '/', '#', 'mailto:', 'tel:')):
        return href
    # Asset file?
    if ASSET_RE.search(href):
        return "/" + href
    slug = href.split("?")[0].split("#")[0].rstrip("/")
    if slug in SLUG_TO_CITY:
        return new_path(slug)
    if slug in TOP_LEVEL:
        return "/" + slug
    # Unknown — leave as-is
    return href

def abs_src(src: str) -> str:
    """Convert a relative src to an absolute path."""
    if not src or src.startswith(('http', '/', 'data:')):
        return src
    return "/" + src

def transform_html(html: str, slug: str) -> str:
    city    = SLUG_TO_CITY[slug]
    old_url = f"{BASE_URL}/{slug}"
    n_url   = new_url(slug)
    n_path  = new_path(slug)

    # 1. canonical + og:url
    html = html.replace(
        f'rel="canonical" href="{old_url}"',
        f'rel="canonical" href="{n_url}"'
    )
    html = html.replace(
        f'content="{old_url}"',
        f'content="{n_url}"'
    )

    # 2. JSON-LD url fields
    html = html.replace(f'"{old_url}"', f'"{n_url}"')

    # 3. BreadcrumbList — update the club's own ListItem url
    html = re.sub(
        r'("item":\s*")' + re.escape(old_url) + r'"',
        r'\g<1>' + n_url + '"',
        html
    )

    # 4. Make all relative hrefs absolute
    def fix_href(m: re.Match) -> str:
        q    = m.group(1)          # quote char
        href = m.group(2)
        return f'href={q}{abs_href(href)}{q}'
    html = re.sub(r'href=(["\'])([^"\']*)\1', fix_href, html)

    # 5. Make all relative srcs absolute
    def fix_src(m: re.Match) -> str:
        q   = m.group(1)
        src = m.group(2)
        return f'src={q}{abs_src(src)}{q}'
    html = re.sub(r'src=(["\'])([^"\']*)\1', fix_src, html)

    # 6. srcset (comma-separated list of URL [descriptor] pairs)
    def fix_srcset(m: re.Match) -> str:
        q      = m.group(1)
        srcset = m.group(2)
        parts  = []
        for entry in srcset.split(","):
            entry   = entry.strip()
            pieces  = entry.split()
            pieces[0] = abs_src(pieces[0])
            parts.append(" ".join(pieces))
        return f'srcset={q}{", ".join(parts)}{q}'
    html = re.sub(r'srcset=(["\'])([^"\']*)\1', fix_srcset, html)

    # 7. CSS url() references
    html = re.sub(
        r"url\('([^/'\"#][^']*)'\)",
        lambda m: f"url('/{m.group(1)}')" if not m.group(1).startswith(('http','/','/')) else m.group(0),
        html
    )

    return html


# ── Embedded map ─────────────────────────────────────────────────────────────

MAP_CSS = """
    /* ── MAP ─────────────────────────────── */
    .map-embed-section { padding: 0 2.5rem 3rem; max-width: 1200px; margin: 0 auto; }
    .map-embed-section h2 { font-size: 14px; letter-spacing: 1px; text-transform: uppercase;
      color: #aaa; font-weight: 500; margin-bottom: 1rem; }
    .map-embed { width: 100%; max-width: 780px; height: 280px; border: 0; border-radius: 12px;
      filter: grayscale(20%); }
    @media (max-width: 600px) { .map-embed-section { padding: 0 1.25rem 2rem; }
      .map-embed { height: 200px; } }
"""

def build_map_section(address: str, city: str) -> str:
    q = quote(f"{address}, {city}, Sverige")
    src = f"https://maps.google.com/maps?q={q}&output=embed&hl=sv"
    return (
        f'\n  <section class="map-embed-section">\n'
        f'    <h3>Mötesplats</h3>\n'
        f'    <iframe class="map-embed" src="{src}" '
        f'loading="lazy" referrerpolicy="no-referrer-when-downgrade" '
        f'title="Karta över mötesplatsen" aria-label="Karta"></iframe>\n'
        f'  </section>\n'
    )

def extract_address(html: str) -> tuple[str, str]:
    """Return (streetAddress, addressLocality) from JSON-LD."""
    m_street = re.search(r'"streetAddress"\s*:\s*"([^"]+)"', html)
    m_city   = re.search(r'"addressLocality"\s*:\s*"([^"]+)"', html)
    street   = m_street.group(1) if m_street else ""
    city     = m_city.group(1)   if m_city   else ""
    return street, city

def inject_map(html: str, slug: str) -> str:
    if 'class="map-embed"' in html:
        return html  # already has embedded map

    street, city = extract_address(html)
    address = street if street and street.lower() not in ("stockholm","göteborg","malmö","") else city
    if not address:
        return html

    # Add CSS
    html = html.replace("  </style>", MAP_CSS + "  </style>", 1)

    # Find the map link button (exists on all club pages) and inject iframe after its section
    map_section = build_map_section(address, city)
    # Inject before the related clubs section or before </main>
    if '<!-- RELATED' in html:
        html = html.replace('<!-- RELATED', map_section + '  <!-- RELATED', 1)
    elif 'class="related-section' in html:
        html = html.replace('class="related-section', map_section + '  <section class="related-section', 1)
    else:
        html = html.replace('  </main>', map_section + '  </main>', 1)

    return html


# ── _redirects update ─────────────────────────────────────────────────────────

def update_redirects(slug: str) -> None:
    redirects_path = ROOT / "_redirects"
    old   = f"/{slug}"
    new   = new_path(slug)
    line  = f"{old} {new} 301\n"

    text = redirects_path.read_text(encoding="utf-8") if redirects_path.exists() else ""
    if line in text or f"{old} " in text:
        return  # already present
    redirects_path.write_text(text + line, encoding="utf-8")


# ── City page link update ────────────────────────────────────────────────────

def update_city_page_links() -> None:
    """Update href="slug" to href="/city/slug/" in city pages."""
    for city, slugs in CITY_CLUBS.items():
        path = ROOT / f"{city}.html"
        if not path.exists():
            continue
        html = path.read_text(encoding="utf-8")
        changed = False
        for slug in slugs:
            old = f'href="{slug}"'
            new = f'href="/{city}/{slug}/"'
            if old in html:
                html    = html.replace(old, new)
                changed = True
        if changed:
            path.write_text(html, encoding="utf-8")
            print(f"  ✓ Updated club links in {city}.html")


# ── Sitemap update ────────────────────────────────────────────────────────────

def update_sitemap() -> None:
    """Replace old flat club URLs with new city-scoped URLs in sitemap.xml."""
    path = ROOT / "sitemap.xml"
    if not path.exists():
        return
    xml = path.read_text(encoding="utf-8")
    for slug, city in SLUG_TO_CITY.items():
        old_loc = f"<loc>{BASE_URL}/{slug}</loc>"
        new_loc = f"<loc>{BASE_URL}/{city}/{slug}/</loc>"
        xml     = xml.replace(old_loc, new_loc)
    path.write_text(xml, encoding="utf-8")
    print("  ✓ sitemap.xml updated")


# ── Main migration ────────────────────────────────────────────────────────────

def migrate_club(slug: str) -> str:
    city     = SLUG_TO_CITY[slug]
    src_path = ROOT / f"{slug}.html"
    dst_dir  = ROOT / city / slug
    dst_path = dst_dir / "index.html"

    if not src_path.exists():
        return f"skip — {slug}.html not found"

    dst_dir.mkdir(parents=True, exist_ok=True)

    html = src_path.read_text(encoding="utf-8")
    html = transform_html(html, slug)
    html = inject_map(html, slug)
    dst_path.write_text(html, encoding="utf-8")

    update_redirects(slug)

    return f"ok → /{city}/{slug}/"


def main() -> None:
    print("\n── Migrating club pages to city-scoped URLs ────────────────")
    ok = skipped = 0
    for city, slugs in CITY_CLUBS.items():
        for slug in slugs:
            status = migrate_club(slug)
            icon   = "✓" if status.startswith("ok") else "·"
            print(f"  {icon} {slug}: {status}")
            if status.startswith("ok"):
                ok += 1
            else:
                skipped += 1

    print(f"\n── Updating city page links ────────────────────────────────")
    update_city_page_links()

    print(f"\n── Updating sitemap.xml ────────────────────────────────────")
    update_sitemap()

    print(f"\nDone. {ok} pages migrated, {skipped} skipped.\n")
    print("Next steps:")
    print("  1. git add + commit the new city subdirectories and updated files")
    print("  2. Submit new URLs in Google Search Console")
    print("  3. Monitor 301 redirect coverage in GSC Coverage report\n")


if __name__ == "__main__":
    main()
