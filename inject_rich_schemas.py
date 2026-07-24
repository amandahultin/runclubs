"""inject_rich_schemas.py

Injects four types of schema.org JSON-LD:
  1. ItemList (SportsActivityLocation) on /stockholm, /goteborg, /ovriga-landet
  2. SportsEvent (next 14 days) on /events
  3. NewsArticle on each article page
  4. FAQPage on city pages and /om-oss

Run from repo root:
    python3 inject_rich_schemas.py

Also called from running-events-sync.yml after generate_running_events.py
so SportsEvent data stays fresh daily.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT     = Path(__file__).parent
BASE_URL = "https://runclubs.se"
STOCKHOLM = ZoneInfo("Europe/Stockholm")


# ── Helpers ──────────────────────────────────────────────────────────────────

def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")

def write(p: Path, html: str) -> None:
    p.write_text(html, encoding="utf-8")

def inject_before_head_close(html: str, schema: dict | list) -> str:
    blob = json.dumps(schema, ensure_ascii=False, indent=2)
    tag  = f'\n  <script type="application/ld+json">\n{blob}\n  </script>'
    return html.replace("</head>", tag + "\n</head>", 1)

def has_type(html: str, schema_type: str) -> bool:
    return f'"@type": "{schema_type}"' in html or f'"@type":"{schema_type}"' in html

def load_club_index() -> dict[str, dict]:
    """Read every club HTML file and extract its existing SportsOrganization JSON-LD.

    Club pages live either as a root-level stub (legacy) or as
    <city>/<slug>/index.html (current convention, e.g. ovriga-landet/rusa-running-club/).
    The stub files are redirect-only and carry no JSON-LD, so subdirectory
    pages must be scanned too or every club added since the URL migration
    silently falls back to generic name/url/image/address below.
    """
    import glob
    data = {}
    patterns = [
        str(ROOT / "*.html"),
        str(ROOT / "*" / "*" / "index.html"),
    ]
    fpaths = [p for pattern in patterns for p in glob.glob(pattern)]
    for fpath in fpaths:
        html = open(fpath, encoding="utf-8").read()
        blocks = re.findall(
            r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL
        )
        for block in blocks:
            try:
                d = json.loads(block)
                if d.get("@type") in ("SportsOrganization", "SportsActivityLocation", "SportsClub"):
                    path = Path(fpath)
                    slug = path.parent.name if path.name == "index.html" else path.stem
                    data[slug] = {
                        "name":    d.get("name", slug),
                        "url":     d.get("url",  f"{BASE_URL}/{slug}"),
                        "image":   d.get("image", f"{BASE_URL}/hero.jpg"),
                        "address": d.get("address", {}),
                    }
            except Exception:
                pass
    return data


# ── 1. ItemList on city pages ─────────────────────────────────────────────────

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
        "billdals-park-run",
        "we-run-west",
        "goteborg-running-club", "sweden-runners-goteborg", "aero-boys-club",
        "east-run-club", "slowrunners-goteborg", "she-runs-club",
        "core-run-club", "ess-runners-club",
    ],
    "ovriga-landet": [
        "orebro-runclub",
        "mrc-malmo", "sweden-runners-malmo", "motvind-run-club-varberg",
        "rusa-running-club", "uppsala-lopklubb-for-tjejer", "social-run-lund",
        "fun-run-malmo", "lund-run-club", "ett-steg-i-taget-alingsas",
        "running-for-breakfast-vasteras", "running-for-breakfast-eskilstuna",
        "running-for-breakfast-norrkoping",
    ],
}

# Fallback PostalAddress.addressLocality when a club's own schema isn't found.
# "ovriga-landet" now spans many cities (Malmö, Varberg, Uppsala, Lund,
# Alingsås, Västerås, Eskilstuna, Norrköping...) so there is no single
# accurate fallback city — this only fires if load_club_index() fails to
# find a club's own address, which should be rare now that it scans
# subdirectory pages too.
CITY_NAMES = {
    "stockholm": "Stockholm",
    "goteborg":  "Göteborg",
    "ovriga-landet": "Malmö",
}

# Display label for the hub page itself (ItemList name/description) — distinct
# from CITY_NAMES, which is real per-club geodata, not a page label.
HUB_LABEL = {
    "stockholm": "Stockholm",
    "goteborg":  "Göteborg",
    "ovriga-landet": "övriga landet",
}

def build_item_list(city_slug: str, club_index: dict) -> dict:
    city_name = CITY_NAMES[city_slug]
    items = []
    for pos, slug in enumerate(CITY_CLUBS[city_slug], start=1):
        club = club_index.get(slug, {})
        name    = club.get("name", slug)
        url     = club.get("url", f"{BASE_URL}/{slug}")
        image   = club.get("image", f"{BASE_URL}/hero.jpg")
        address = club.get("address", {
            "@type": "PostalAddress",
            "addressLocality": city_name,
            "addressCountry": "SE",
        })
        item = {
            "@type": "ListItem",
            "position": pos,
            "item": {
                "@type": "SportsActivityLocation",
                "name":  name,
                "url":   url,
                "image": image,
                "address": address,
            },
        }
        items.append(item)

    hub_label = HUB_LABEL[city_slug]
    return {
        "@context": "https://schema.org",
        "@type":    "ItemList",
        "name":     f"Löpargrupper i {hub_label}",
        "description": f"Alla run clubs och löpargrupper i {hub_label}",
        "numberOfItems": len(items),
        "itemListElement": items,
    }

def inject_item_lists(club_index: dict) -> None:
    for city_slug in CITY_CLUBS:
        path = ROOT / f"{city_slug}.html"
        if not path.exists():
            print(f"  ⚠ {city_slug}.html not found")
            continue
        html = read(path)
        if has_type(html, "ItemList"):
            # Replace existing ItemList to keep it fresh
            html = re.sub(
                r'<script type="application/ld\+json">\s*\{[^<]*"@type":\s*"ItemList"[^<]*\}\s*</script>',
                "", html, flags=re.DOTALL
            )
        schema = build_item_list(city_slug, club_index)
        write(path, inject_before_head_close(html, schema))
        print(f"  ✓ ItemList → {city_slug}.html ({len(CITY_CLUBS[city_slug])} clubs)")


# ── 2. SportsEvent on /events ────────────────────────────────────────

CITY_GEO = {
    "Stockholm": {"@type": "GeoCoordinates", "latitude": 59.3293, "longitude": 18.0686},
    "Göteborg":  {"@type": "GeoCoordinates", "latitude": 57.7089, "longitude": 11.9746},
    "Malmö":     {"@type": "GeoCoordinates", "latitude": 55.6049, "longitude": 13.0038},
}

def parse_location(location_str: str, city: str) -> dict:
    """Build a Place from the event location string."""
    loc = (location_str or "").strip()
    place: dict = {
        "@type": "Place",
        "name":  loc or city,
        "address": {
            "@type": "PostalAddress",
            "streetAddress":   loc,
            "addressLocality": city,
            "addressCountry":  "SE",
        },
    }
    if city in CITY_GEO:
        place["geo"] = CITY_GEO[city]
    return place

def load_events_from_running_events() -> list[dict]:
    path = ROOT / "events.html"
    if not path.exists():
        return []
    text = read(path)
    m = re.search(r"const events = (\[[\s\S]*?\]);", text)
    if not m:
        return []
    return json.loads(m.group(1))

def build_sports_events(events: list[dict], days: int = 14) -> list[dict]:
    now   = datetime.now(STOCKHOLM)
    cutoff = now + timedelta(days=days)
    result = []
    seen: set[str] = set()

    for ev in events:
        date_str = ev.get("date", "")
        if not date_str:
            continue
        try:
            dt = datetime.fromisoformat(date_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=STOCKHOLM)
        except ValueError:
            continue

        if dt < now or dt > cutoff:
            continue

        key = f"{ev.get('club')}|{date_str}"
        if key in seen:
            continue
        seen.add(key)

        city     = ev.get("city", "Stockholm")
        location = parse_location(ev.get("location", ""), city)
        end_dt   = dt + timedelta(hours=2)  # reasonable default duration

        schema_ev: dict = {
            "@type":               "SportsEvent",
            "name":                ev.get("title") or ev.get("club", ""),
            "startDate":           dt.isoformat(),
            "endDate":             end_dt.isoformat(),
            "eventStatus":         "https://schema.org/EventScheduled",
            "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
            "location":            location,
            "organizer": {
                "@type": "SportsTeam",
                "name":  ev.get("club", ""),
                "url":   ev.get("club_page") or f"{BASE_URL}/events",
            },
            "isAccessibleForFree": True,
            "inLanguage": "sv",
        }
        if ev.get("description"):
            schema_ev["description"] = ev["description"][:500]
        if ev.get("link"):
            schema_ev["url"] = ev["link"]
        if ev.get("image_url"):
            schema_ev["image"] = ev["image_url"]

        result.append(schema_ev)

    return result

def inject_sports_events() -> None:
    path = ROOT / "events.html"
    if not path.exists():
        print("  ⚠ events.html not found")
        return

    events_raw = load_events_from_running_events()
    sports_events = build_sports_events(events_raw)

    if not sports_events:
        print("  ⚠ No upcoming events found for SportsEvent schema")
        return

    html = read(path)
    # Remove previous SportsEvent block(s) to stay idempotent
    html = re.sub(
        r'\n  <script type="application/ld\+json">\s*\{[^<]*"@type":\s*"ItemList"[\s\S]*?</script>',
        "", html
    )
    html = re.sub(
        r'\n  <script type="application/ld\+json">\s*\[[^<]*"@type":\s*"SportsEvent"[\s\S]*?</script>',
        "", html
    )

    graph = {"@context": "https://schema.org", "@graph": sports_events}
    write(path, inject_before_head_close(html, graph))
    print(f"  ✓ SportsEvent → events.html ({len(sports_events)} events, next 14 days)")


# ── 3. NewsArticle on article pages ──────────────────────────────────────────

ARTICLES = [
    {
        "file":          "tjejer-tar-over-lopsparen.html",
        "headline":      "Tjejer tar över löpspåren — och gör det tillsammans",
        "datePublished": "2026-04-01",
        "dateModified":  "2026-04-30",
        "image":         f"{BASE_URL}/tjejer-och-run-clubs.jpg",
        "image_width":   1200,
        "image_height":  800,
        "description":   "Aldrig har så många tjejer sprungit i grupp. Vi tittar på trenden som förändrar run clubs i Sverige.",
    },
    {
        "file":          "stockholm-marathon-2026-slutsalt.html",
        "headline":      "Stockholm Marathon 2026 slutsålt — på rekordtid",
        "datePublished": "2025-11-01",
        "dateModified":  "2025-11-01",
        "image":         f"{BASE_URL}/run-clubs-stockholm-marathon.jpeg",
        "image_width":   1200,
        "image_height":  800,
        "description":   "Adidas Stockholm Marathon 2026 är slutsålt på rekordtid — aldrig tidigare har loppet sålts ut så snabbt.",
    },
    {
        "file":          "lopning-for-tjejer.html",
        "headline":      "Löpning för tjejer — löpargrupper och sällskap",
        "datePublished": "2026-04-30",
        "dateModified":  "2026-04-30",
        "image":         f"{BASE_URL}/stockholm-run-clubs.jpeg",
        "image_width":   1200,
        "image_height":  800,
        "description":   "Hitta löpargrupper för tjejer i Stockholm, Göteborg och Malmö. Alla nivåer välkomna.",
    },
]

AUTHOR = {
    "@type": "Person",
    "name":  "Amanda Hultin",
    "url":   "https://amandahultin.se",
}
PUBLISHER = {
    "@type": "Organization",
    "name":  "Runclubs.se",
    "url":   BASE_URL,
    "logo": {
        "@type":  "ImageObject",
        "url":    f"{BASE_URL}/favicon.svg",
        "width":  512,
        "height": 512,
    },
}

def inject_news_articles() -> None:
    for art in ARTICLES:
        path = ROOT / art["file"]
        if not path.exists():
            print(f"  ⚠ {art['file']} not found")
            continue
        html = read(path)
        if has_type(html, "NewsArticle"):
            print(f"  · NewsArticle already present in {art['file']}")
            continue

        schema = {
            "@context":      "https://schema.org",
            "@type":         "NewsArticle",
            "headline":      art["headline"],
            "datePublished": art["datePublished"],
            "dateModified":  art["dateModified"],
            "description":   art["description"],
            "image": {
                "@type":  "ImageObject",
                "url":    art["image"],
                "width":  art["image_width"],
                "height": art["image_height"],
            },
            "author":    AUTHOR,
            "publisher": PUBLISHER,
            "mainEntityOfPage": {
                "@type": "WebPage",
                "@id":   f"{BASE_URL}/{path.stem}",
            },
            "inLanguage": "sv",
        }
        write(path, inject_before_head_close(html, schema))
        print(f"  ✓ NewsArticle → {art['file']}")


# ── 4. FAQPage on city pages and /om-oss ─────────────────────────────────────

CITY_FAQS = {
    "stockholm": [
        ("Vad kostar det att vara med i en run club i Stockholm?",
         "De flesta run clubs i Stockholm är helt gratis att delta i. Vissa clubs erbjuder betalda träningsprogram eller premium-pass, men grundkonceptet är öppet för alla."),
        ("Vilken nivå krävs för att vara med?",
         "De flesta löpargrupper i Stockholm välkomnar alla nivåer — från nybörjare till erfarna löpare. Många clubs har anpassade pass för olika tempo och distanser."),
        ("När och var samlas run clubs i Stockholm?",
         "Stockholms run clubs samlas på olika platser och tider beroende på club. Vanliga mötesplatser är Hagaparken, Djurgården, Östermalm och Södermalm. Kolla respektive clubs sida för aktuella tider."),
        ("Hur hittar jag rätt run club för mig i Stockholm?",
         "På Runclubs.se kan du filtrera Stockholms run clubs efter dag, nivå och stadsdel. Välj de kriterier som passar dig och hitta ditt crew direkt."),
        ("Kan jag ta med en vän som aldrig sprungit förut?",
         "Ja! De flesta run clubs välkomnar nybörjare och uppmuntrar till att ta med vänner. Social löpning är kärnan i run club-kulturen."),
    ],
    "goteborg": [
        ("Vad kostar det att vara med i en run club i Göteborg?",
         "De allra flesta run clubs i Göteborg är gratis att delta i. Du behöver bara dyka upp och vara redo att springa."),
        ("Vilken nivå krävs för att vara med i Göteborgs run clubs?",
         "Göteborgs run clubs är öppna för alla nivåer. Oavsett om du är nybörjare eller rutinerad löpare finns det en grupp som passar dig."),
        ("När samlas run clubs i Göteborg?",
         "Göteborg har run clubs som samlas på vardagar och helger. Kolla in varje clubs sida på Runclubs.se för aktuella tider och mötesplatser."),
        ("Hur hittar jag en löpargrupp i Göteborg?",
         "Runclubs.se listar alla kända run clubs i Göteborg med tider, startplatser och nivå. Bläddra bland clubs och hitta din matchning."),
        ("Finns det run clubs i Göteborg som fokuserar på tjejer?",
         "Ja, flera run clubs i Göteborg har pass riktade mot tjejer eller mixed grupper med inkluderande miljö. Se filtret på Göteborgs-sidan."),
    ],
    "ovriga-landet": [
        ("Vad kostar det att springa med en run club i övriga landet?",
         "Run clubs utanför Stockholm och Göteborg är gratis att delta i. Du anmäler dig enkelt via Strava eller Instagram och dyker upp på startplatsen."),
        ("Vilken nivå krävs för run clubs i övriga landet?",
         "Run clubs i övriga landet tar emot alla — nybörjare som vill komma igång och erfarna löpare som vill ha sällskap."),
        ("Var samlas run clubs i övriga landet?",
         "Mötesplatsen varierar per stad och club — i Malmö samlas många kring Stortorget och Pildammsparken. Se varje clubs sida för exakt startplats."),
        ("Hur ofta kör run clubs i övriga landet sina pass?",
         "De flesta run clubs kör återkommande veckopass. Frekvensen varierar — en till tre gånger i veckan är vanligt."),
    ],
    "om-oss": [
        ("Vad är Runclubs.se?",
         "Runclubs.se är Sveriges samlade guide till run clubs och löpargrupper. Vi listar clubs i Stockholm, Göteborg och övriga landet med tider, startplatser och nivå så att du enkelt hittar rätt grupp."),
        ("Hur lägger jag till min run club på Runclubs.se?",
         "Maila oss på amanda@runclubs.se med information om din club — namn, startplats, tider och kontaktlänkar. Vi lägger upp er gratis."),
        ("Är det gratis att använda Runclubs.se?",
         "Ja, Runclubs.se är helt gratis för löpare att använda. Vi tar inte heller betalt av clubs för att listas."),
        ("Hur ofta uppdateras eventinformationen?",
         "Eventdata uppdateras automatiskt varje morgon från Strava och vårt eget kalkylblad. Du ser alltid de senaste passen."),
        ("Täcker ni fler städer än Stockholm, Göteborg och övriga landet?",
         "I nuläget fokuserar vi på Sveriges tre största städer. Fler städer är på väg — hör av dig om du vill se din stad på sajten."),
    ],
}

def build_faq(slug: str) -> dict:
    faqs = CITY_FAQS.get(slug, [])
    return {
        "@context": "https://schema.org",
        "@type":    "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name":  q,
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text":  a,
                },
            }
            for q, a in faqs
        ],
    }

def inject_faqs() -> None:
    for slug in list(CITY_FAQS.keys()):
        path = ROOT / f"{slug}.html"
        if not path.exists():
            print(f"  ⚠ {slug}.html not found")
            continue
        html = read(path)
        if has_type(html, "FAQPage"):
            print(f"  · FAQPage already present in {slug}.html")
            continue
        schema = build_faq(slug)
        write(path, inject_before_head_close(html, schema))
        print(f"  ✓ FAQPage → {slug}.html ({len(CITY_FAQS[slug])} Q&As)")


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    print("\n── ItemList (city pages) ───────────────────────────────────")
    club_index = load_club_index()
    inject_item_lists(club_index)

    print("\n── SportsEvent (events) ────────────────────────────────────")
    inject_sports_events()

    print("\n── NewsArticle (articles) ──────────────────────────────────")
    inject_news_articles()

    print("\n── FAQPage (city pages + om-oss) ───────────────────────────")
    inject_faqs()

    print("\nDone.\n")


if __name__ == "__main__":
    main()
