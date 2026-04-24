"""Generate sitemap.xml from all public HTML files in the project.

Run directly:  python generate_sitemap.py
Also called automatically by the pre-commit git hook.
"""

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
}

# Priority rules: slug → (priority, changefreq)
PRIORITY = {
    "index":                    (1.0,  "weekly"),
    "stockholm":                (0.95, "weekly"),
    "goteborg":                 (0.95, "weekly"),
    "malmo":                    (0.95, "weekly"),
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


def slug_to_url(slug: str) -> str:
    return f"{BASE_URL}/" if slug == "index" else f"{BASE_URL}/{slug}"


def build_sitemap(root: Path) -> str:
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
        "Eventsidor":        ["stockholm-running-events", "loppkalender", "nyheter"],
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
    <loc>{slug_to_url(slug)}</loc>
    <lastmod>{TODAY}</lastmod>
    <changefreq>{freq}</changefreq>
    <priority>{pri}</priority>
  </url>""")

    # Club pages — everything not yet listed
    club_slugs = [s for s in slugs if s not in ordered]
    if club_slugs:
        # Group by city heuristic (just alphabetical for now)
        sthlm = [s for s in club_slugs if s not in
                 {"goteborg-running-club","sweden-runners-goteborg","slowrunners-goteborg","ess-runners-club",
                  "mrc-malmo","sweden-runners-malmo"}]
        gbg   = [s for s in club_slugs if s in
                 {"goteborg-running-club","sweden-runners-goteborg","slowrunners-goteborg","ess-runners-club"}]
        malmo = [s for s in club_slugs if s in {"mrc-malmo","sweden-runners-malmo"}]

        for label, group in [("Klubbsidor Stockholm", sthlm),
                              ("Klubbsidor Göteborg",  gbg),
                              ("Klubbsidor Malmö",     malmo)]:
            if group:
                lines.append(f"\n  <!-- {label} -->")
                for slug in sorted(group):
                    pri, freq = PRIORITY.get(slug, DEFAULT_PRIORITY)
                    lines.append(f'  <url><loc>{slug_to_url(slug)}</loc><lastmod>{TODAY}</lastmod><priority>{pri}</priority></url>')

    lines.append("\n</urlset>")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    root = Path(__file__).parent
    sitemap = build_sitemap(root)
    out = root / "sitemap.xml"
    out.write_text(sitemap, encoding="utf-8")
    print(f"Wrote {out} ({sitemap.count('<url>')} URLs)")
