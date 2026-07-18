"""Generate sitemap.xml from all public HTML files in the project.

Run directly:  python generate_sitemap.py
Also called automatically by the pre-commit git hook.
"""

from __future__ import annotations

from pathlib import Path
from datetime import date
from xml.sax.saxutils import escape as xml_escape

from filter_combos import all_combos

BASE_URL = "https://runclubs.se"
TODAY = date.today().isoformat()

# Filter-combination pages (niva/typ/stadsdel) — see filter_combos.py
FILTER_PAGE_PRIORITY = 0.3
FILTER_PAGE_CHANGEFREQ = "monthly"

# Pages to skip (templates, mockups, drafts)
SKIP = {
    "index-feminine", "index-feminine-v2",
    "mockup-botanik", "mockup-korall", "mockup-lila", "mockup-solsken",
    "placeholder-preview", "klubb",
    "yo-running-club",
    "saucony-run-club",
}

# Priority rules: slug → (priority, changefreq)
PRIORITY = {
    "index":                    (1.0,  "weekly"),
    "stockholm":                (0.95, "weekly"),
    "goteborg":                 (0.95, "weekly"),
    "ovriga-landet":            (0.95, "weekly"),
    "events":                   (0.90, "daily"),
    "nyheter":                  (0.75, "weekly"),
    "loppkalender":             (0.75, "weekly"),
    "stockholm-running-events": (0.75, "daily"),
    "tjejer-tar-over-lopsparen":       (0.65, "monthly"),
    "stockholm-marathon-2026-slutsalt":(0.65, "monthly"),
    "lopning-for-tjejer":              (0.65, "monthly"),
    "om-oss":                   (0.5,  "monthly"),
    "samarbeta":                (0.5,  "monthly"),
    "kontakt":                  (0.4,  "monthly"),
}
DEFAULT_PRIORITY = (0.6, "monthly")


def parse_redirects(root: Path) -> dict[str, str]:
    """Return {source_path: destination_path} for 301 rules in _redirects."""
    rules: dict[str, str] = {}
    path = root / "_redirects"
    if not path.exists():
        return rules
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split()
        if len(parts) >= 3 and parts[2] == "301" and parts[0].startswith("/"):
            rules[parts[0]] = parts[1]
    return rules


def canonical_url(slug: str, redirects: dict[str, str]) -> str:
    src = "/" if slug == "index" else f"/{slug}"
    dst = redirects.get(src, src)
    return f"{BASE_URL}{dst}"


def city_of(url: str) -> str | None:
    path = url.removeprefix(BASE_URL)
    for city in ("stockholm", "goteborg", "ovriga-landet"):
        if path.startswith(f"/{city}/"):
            return city
    return None


def build_sitemap(root: Path) -> str:
    redirects = parse_redirects(root)
    slugs = sorted(
        p.stem for p in root.glob("*.html")
        if p.stem not in SKIP
    )

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']

    # Ordered sections for readability
    sections = {
        "Startsida":         ["index"],
        "Stadssidor":        ["stockholm", "goteborg", "ovriga-landet"],
        "Eventsidor":        ["events", "stockholm-running-events", "loppkalender", "nyheter"],
        "Artiklar":          ["tjejer-tar-over-lopsparen", "stockholm-marathon-2026-slutsalt", "lopning-for-tjejer"],
        "Om sajten":         ["om-oss", "samarbeta", "kontakt"],
    }

    ordered = []
    for label, group in sections.items():
        present = [s for s in group if s in slugs]
        if present:
            lines.append(f"\n  <!-- {label} -->")
            for slug in present:
                ordered.append(slug)
                pri, freq = PRIORITY.get(slug, DEFAULT_PRIORITY)
                lines.append(f"""  <url>
    <loc>{canonical_url(slug, redirects)}</loc>
    <lastmod>{TODAY}</lastmod>
    <changefreq>{freq}</changefreq>
    <priority>{pri}</priority>
  </url>""")

    # Club pages — everything not yet listed, grouped by destination city.
    club_slugs = [s for s in slugs if s not in ordered]
    by_city: dict[str | None, list[tuple[str, str]]] = {"stockholm": [], "goteborg": [], "ovriga-landet": [], None: []}
    for slug in club_slugs:
        url = canonical_url(slug, redirects)
        by_city[city_of(url)].append((slug, url))

    combos_by_city: dict[str, list] = {"stockholm": [], "goteborg": [], "ovriga-landet": []}
    for combo in all_combos(root):
        combos_by_city[combo.city].append(combo)

    for city, club_label, filter_label in [
        ("stockholm", "Klubbsidor Stockholm", "Filtersidor Stockholm"),
        ("goteborg", "Klubbsidor Göteborg", "Filtersidor Göteborg"),
        ("ovriga-landet", "Klubbsidor Övriga landet", "Filtersidor Övriga landet"),
        (None, "Klubbsidor (övrigt)", None),
    ]:
        group = by_city[city]
        if group:
            # Dedupe entries that resolve to the same destination URL (e.g. two
            # legacy slugs redirecting to the same club page).
            seen_urls: set[str] = set()
            deduped = []
            for slug, url in sorted(group):
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                deduped.append((slug, url))

            lines.append(f"\n  <!-- {club_label} -->")
            for slug, url in deduped:
                pri, freq = PRIORITY.get(slug, DEFAULT_PRIORITY)
                lines.append(f'  <url><loc>{url}</loc><lastmod>{TODAY}</lastmod><priority>{pri}</priority></url>')

        if city and combos_by_city[city]:
            lines.append(f"\n  <!-- {filter_label} -->")
            for combo in combos_by_city[city]:
                lines.append(
                    f'  <url><loc>{xml_escape(combo.url)}</loc><lastmod>{TODAY}</lastmod>'
                    f'<changefreq>{FILTER_PAGE_CHANGEFREQ}</changefreq>'
                    f'<priority>{FILTER_PAGE_PRIORITY}</priority></url>'
                )

    lines.append("\n</urlset>")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    root = Path(__file__).parent
    sitemap = build_sitemap(root)
    out = root / "sitemap.xml"
    out.write_text(sitemap, encoding="utf-8")
    print(f"Wrote {out} ({sitemap.count('<url>')} URLs)")
