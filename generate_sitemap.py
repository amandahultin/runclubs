"""Generate sitemap.xml from all public HTML files in the project.

Run directly:  python generate_sitemap.py
Also called automatically by the pre-commit git hook.
"""

from __future__ import annotations

from pathlib import Path
from datetime import date

BASE_URL = "https://runclubs.se"
TODAY = date.today().isoformat()

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
    "malmo":                    (0.95, "weekly"),
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
    for city in ("stockholm", "goteborg", "malmo"):
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
        "Stadssidor":        ["stockholm", "goteborg", "malmo"],
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
    by_city: dict[str | None, list[tuple[str, str]]] = {"stockholm": [], "goteborg": [], "malmo": [], None: []}
    for slug in club_slugs:
        url = canonical_url(slug, redirects)
        by_city[city_of(url)].append((slug, url))

    for city, label in [("stockholm", "Klubbsidor Stockholm"),
                        ("goteborg",  "Klubbsidor Göteborg"),
                        ("malmo",     "Klubbsidor Malmö"),
                        (None,        "Klubbsidor (övrigt)")]:
        group = by_city[city]
        if group:
            lines.append(f"\n  <!-- {label} -->")
            for slug, url in sorted(group):
                pri, freq = PRIORITY.get(slug, DEFAULT_PRIORITY)
                lines.append(f'  <url><loc>{url}</loc><lastmod>{TODAY}</lastmod><priority>{pri}</priority></url>')

    lines.append("\n</urlset>")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    root = Path(__file__).parent
    sitemap = build_sitemap(root)
    out = root / "sitemap.xml"
    out.write_text(sitemap, encoding="utf-8")
    print(f"Wrote {out} ({sitemap.count('<url>')} URLs)")
