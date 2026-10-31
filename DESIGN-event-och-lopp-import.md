# Event & lopp — gemensam import och datamodell

Designskiss, 2026-10-31. Beslutad riktning: **klubbevent och loppkalendern designas tillsammans** — ett importramverk och en datakärna, men separata sidor.

> **Status, 2026-10-31.** Ursprungligen var allt detta köat bakom struktur-/URL-migreringen. Det gäller inte längre fullt ut:
>
> - **Lopp har startat.** Villkoret "vänta på omstruktureringen" är avskrivet för loppens del, och lopp ägs end-to-end på ett ställe — både importen och sidan.
> - **Eventdatan är på väg till Supabase** i en parallell session ("Flytta datainsamlingen till Supabase"), som håller sig till klubbar/event. Det betyder att §6 delvis redan är beslutat och pågående på event-sidan — stäm av mot den sessionen innan lagret designas om här.
> - **Omstruktureringen har inte landat** (108 .html ligger kvar i repo-roten, inga stadskataloger utöver `stockholm/`, `goteborg/`, `ovriga-landet/`).
>
> Skissen är därmed målbilden att växa mot, inte en plan som ligger på is. Det som fortfarande bör inväntas är sidplacering och URL:er (§7), inte datamodellen.

---

## 1. Varför de hör ihop

De två pipelinena har redan identisk form — extern källa → Google Sheet → generator-script → statisk HTML — men har byggts var för sig, och event-sidan har hunnit lösa problem som loppsidan kommer att stöta på.

| | **Event** | **Lopp** |
|---|---|---|
| Källa | Strava + kuraterade flikar | `runclubs-races-scraper` |
| Ark | Sheet `EVENTS_SHEET_ID`, 4 flikar: `Events`, `WeeklyRuns`, `Overrides`, `SpecialEvents` | Sheet `RACES_SHEET_ID`, flik-id `114178703` |
| Generator | [generate_running_events.py](generate_running_events.py) (2043 rader) + [events_common.py](events_common.py) (598) | [generate_kommande_lopp.py](generate_kommande_lopp.py) (1065) |
| Sidor | `events.html` → [split_city_events.py](split_city_events.py) → stad-sidor + `index.html` | `loppkalender.html` |
| Schema | `SportsEvent` via [inject_rich_schemas.py](inject_rich_schemas.py) | `SportsEvent` inline i generatorn |
| Körning | [running-events-sync.yml](.github/workflows/running-events-sync.yml), 4×/dygn | [races-sync.yml](.github/workflows/races-sync.yml), måndagar |
| Interaktion | likes + klick via [supabase/event_interactions.sql](supabase/event_interactions.sql) | ingen |

> **Driftsfälla att känna till:** `races-sync.yml` kör varje vecka och lyckas alltid, så CI ser grönt ut och sidan visar ett färskt "Loppdatan uppdaterades" — men den renderar bara om det som redan ligger i arket. Det som *fyller* arket, `scrape-races.yml` i **mikaelsto/runclubs-races-scraper**, är `workflow_dispatch` only. Loppdatan kan alltså åldras i månader utan att något larmar. Ett eget schemaläggningsfel, men också ett argument för §5: en import som upsertar mot ett lager med `fetched_at` gör staleness synlig i stället för tyst.

### Det event-sidan har och loppsidan saknar

Allt detta ligger i [events_common.py](events_common.py) och är generiskt — inget av det är egentligen event-specifikt:

- **Namnnormalisering** — `normalize_club_name()` + `CLUB_NAME_ALIASES` (`events_common.py:40`). Strava stavar klubbar annorlunda än arken; aliasen ger en klubb ett namn, en filterpill, en dedupe-nyckel. Loppsidan har ingen motsvarighet för arrangörsnamn.
- **Stadsupplösning** — `resolve_city()` (`events_common.py:180`): nyckelord i platsfältet, folding av å/ä/ö, ordgräns så `Lundagatan` inte blir Lund, utlandsfilter (`is_abroad()`, inkl. flaggemoji), fallback till klubbens hemstad. Loppsidan har `_map_region()` (`generate_kommande_lopp.py:96`) som bara tittar på tre strängar i tre kolumner.
- **Dedupe över källor** — `SOURCE_PRIORITY = ("strava", "special", "weekly_run")` (`events_common.py:362`): när flera källor beskriver samma klubbs pass samma dag vinner den med riktig titel, bild och länk. Så fort loppen får en andra källa behövs exakt detta.
- **Robust hämtning** — `_with_retry()` med backoff på 429/5xx, `WorksheetNotFound` som tolereras. Loppens `fetch_races()` (`generate_kommande_lopp.py:131`) har ingen retry alls — ett 429 fäller hela måndagskörningen.
- **Tolerant datum/tid** — `combine_date_time()`, `_parse_time()` som klarar `8.30`, `18:00:00`.

### Det loppsidan har och eventsidan saknar

- **Distansbuckets** — `_DIST_BUCKETS` + `_parse_km_list()` (`generate_kommande_lopp.py:30`), inkl. flerdistanslopp (`"5,10,21,1km"` → `[5.0, 10.0, 21.1]`).
- **Län → region** och `CITY_GEO` för schemats `GeoCoordinates`.
- **Längre tidshorisont** — loppen sträcker sig ett år fram, med fönster för schemat (`_SCHEMA_WINDOW_DAYS = 183`, max 60). Eventen har `LOOKAHEAD_DAYS = 30`.

---

## 2. Målbild

```
  Källadaptrar            Normalisering            Lager          Rendering
┌────────────────┐      ┌──────────────────┐   ┌───────────┐   ┌──────────────┐
│ strava         │      │ namn-alias       │   │           │   │ /events      │
│ instagram      │ ───▶ │ plats → stad     │──▶│ occurrence│──▶│ stadssidor   │
│ races-scraper  │      │ datum/tid/tz     │   │   core    │   │ /loppkalender│
│ manuellt/CMS   │      │ distans → bucket │   │ + profil  │   │ /index (SSR) │
└────────────────┘      │ dedupe/prioritet │   └───────────┘   │ instagram-   │
                        └──────────────────┘         │         │   bilder     │
                                                     ▼         └──────────────┘
                                              /admin granskning
                                              /analytics klick
```

Fyra lager, med en tydlig gräns mellan dem:

1. **Adapter** — vet allt om *en* källa, inget om sajten. Returnerar råa poster.
2. **Normalisering** — vet allt om sajtens begrepp (städer, klubbnamn, distanser), inget om källorna.
3. **Lager** — en tabell med typdiskriminator, sanning för både sidor och `/admin`.
4. **Rendering** — läser lagret, vet inget om källor.

Idag är alla fyra sammanblandade i generator-scripten.

---

## 3. Datamodell

En kärna för "något som händer, en dag, på en plats", plus typspecifika fält. **Inte** en bred tabell med nullbara kolumner för båda — och inte två orelaterade tabeller.

```sql
-- Kärnan: delad av event och lopp
create table occurrence (
  id            text primary key,      -- stabil, se §4
  type          text not null check (type in ('event','race')),
  title         text not null,
  starts_at     timestamptz not null,  -- alltid tz-medveten, Europe/Stockholm in
  ends_at       timestamptz,
  location      text,                  -- råtext som källan gav den
  city          text,                  -- kanonisk: Stockholm | Göteborg | Malmö | Övriga landet
  url           text,                  -- utgående länk (klickräknas)
  image_url     text,
  description   text,
  source        text not null,         -- strava | instagram | races_scraper | weekly_run | special | manual
  source_id     text,                  -- källans eget id, för idempotent upsert
  status        text not null default 'published',  -- published | hidden | pending_review
  fetched_at    timestamptz not null,
  unique (source, source_id)
);

-- Profil: klubbevent
create table occurrence_event (
  id            text primary key references occurrence(id) on delete cascade,
  club          text not null,         -- normaliserat namn
  recurrence    text,                  -- null för engångs, annars veckoregel
  engagement    int                    -- Strava-deltagare
);

-- Profil: lopp
create table occurrence_race (
  id            text primary key references occurrence(id) on delete cascade,
  organizer     text,
  distance_raw  text,                  -- "5,10,21,1km" som källan gav den
  distances_m   int[],                 -- parsade, sorterade
  dist_cats     text[],                -- 10k | 11-20k | Halvmaraton | 30k | Maraton | Ultra
  region        text,                  -- loppens egen indelning (inkl. Malmö)
  signup_url    text,
  signup_deadline date,
  price_sek     int
);
```

**Noter om modellen**

- `city` vs `region`: eventen har fyra städer, loppen fyra regioner där Malmö är egen. Håll `occurrence.city` som sajtens kanoniska stad och låt `occurrence_race.region` vara loppsidans egen vy. Att tvinga ihop dem nu ger en konvertering på fel ställe.
- `starts_at` som `timestamptz`: idag bär eventen ISO-strängar utan zon som tolkas som `Europe/Stockholm` sent i kedjan (`events_common.py:229`) och loppen rena datum. Normalisera vid ingång, en gång.
- `source_id` + `unique (source, source_id)` gör importen idempotent — kör om utan dubbletter. Det finns inte idag; i dag är hela arket sanningen och sidan byggs om från scratch varje gång.
- `status` är det `/admin` behöver för att kunna dölja eller godkänna utan att röra källan. Idag görs det med `Overrides`-fliken, som bara finns för event.

---

## 4. Stabila id:n — det här måste lösas först

`event_id()` i `generate_running_events.py:466` hashar `source | klubb | datum | länk`:

```python
key = "|".join((
    ev.get("source") or "",
    club_match_key(ev.get("club") or ""),
    (ev.get("date") or "")[:10],
    ev.get("link") or ev.get("title") or "",
))
return hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]
```

`source` ingår i nyckeln — men dedupen i `events_common.py` byter medvetet ut vilken källa som vinner för samma klubb och dag. **När ett Strava-pass dyker upp för ett pass som tidigare kom från `weekly_run` byter kortet id, och dess likes och klick i `event_interactions` blir orphans.** Samma sak om Strava ändrar `link`.

I den nya modellen: id:t hör till *tillfället*, inte till källan som råkade beskriva det. Förslag:

- `id = sha1(type | identitet | datum)[:10]`, där identitet är normaliserad klubb för event och normaliserat loppnamn för lopp. Ingen `source`, ingen `link`.
- Loppen får därmed id:n för första gången, vilket är förutsättningen för att klickräkna dem med samma mekanism som eventen.
- Vid migrering: behåll nuvarande `event_id` som `legacy_id` på raden, så historiken i `event_interactions` kan knytas om i stället för att tappas. Gör den omknytningen *innan* id-bytet går live.

---

## 5. Importramverk

Ett adapter-interface, en gemensam körning:

```python
class Source(Protocol):
    name: str                      # "strava", "races_scraper", …
    def fetch(self) -> list[dict]: ...          # rått, oförändrat
    def to_occurrence(self, row: dict) -> Occurrence | None: ...   # None = skippa
```

Pipelinen blir då densamma för alla källor, och är det enda stället som ändras när en femte källa tillkommer:

```
fetch → to_occurrence → normalisera (namn, stad, tid, distans)
      → is_abroad-filter → dedupe på (identitet, datum) via SOURCE_PRIORITY
      → upsert på (source, source_id) → status från /admin-overrides
```

`events_common.py` är i praktiken redan 70 % av normaliseringslagret. Arbetet är att **lyfta ut** det ur event-sammanhanget, inte skriva det på nytt: alias, stadsupplösning, utlandsfilter, datumparsning och dedupe flyttar till ett delat `occurrences/`-paket, och den HTML-producerande koden (`card_html()`, `feed_card_html()`, `render_events_section()`) stannar i renderingslagret.

---

## 6. Var datan bor

Idag är två Google Sheets sanningen, och sajten byggs om från dem. [supabase/event_interactions.sql](supabase/event_interactions.sql) finns redan — Supabase är alltså redan i bilden, men bara för likes och klick.

**Rekommendation:** flytta sanningen till Supabase och låt scrapers skriva dit, med Sheets kvar enbart som manuellt inmatningsgränssnitt tills `/admin` ersätter det.

Varför det hänger samman med resten av kön:

- `/admin` behöver kunna redigera och dölja en post. Mot ett Google Sheet betyder det att CMS:et skriver i ett kalkylark; mot Supabase är det ett vanligt formulär mot en tabell med `status`.
- `/analytics` ska visa utgående klick för både event och lopp. Klicken ligger redan i Supabase; ligger även posterna där blir det en join i stället för en matchning mot ett ark.
- Nyhetsbrevet (beehiiv) och loppkalendern vill ha samma veckovisa urval. Ett lager att fråga, inte två ark att slå ihop.

**Detta är beslutet som allt annat hänger på**, eftersom det avgör om de genererade sidorna läser från ark eller databas. För event är det redan påbörjat i den parallella Supabase-sessionen; poängen här är att loppen ska in i *samma* tabeller, inte i en parallell variant.

Vad som behålls oavsett: generatorerna fortsätter producera **statisk HTML med datan inlinad** och klientfiltrering. Det är det som gör sidorna snabba och indexerbara, och det ska inte bytas mot runtime-hämtning.

---

## 7. Sidorna förblir separata

`/events` och stadssidorna svarar på *"vad händer i veckan nära mig"*. `/loppkalender` svarar på *"vilket lopp ska jag anmäla mig till om fyra månader"*. Olika filter (klubb/dag/stad vs distans/månad/region), olika tidshorisont (30 dagar vs ett år), olika sökintention, olika sidor i sitemap.

Det som delas är **kort- och filterkomponenter** samt schemagenereringen — i dag är kortmarkup och filter-JS skrivet två gånger, och `generate_kommande_lopp.py:231` konstaterar själv att det är "same shape `inject_rich_schemas.py` uses for /events".

En gemensam vy är däremot rimlig på sikt: "allt som händer den här veckan" över båda typerna, t.ex. på startsidan eller i nyhetsbrevet. Det blir triviellt med en delad kärna och omöjligt med två pipelines.

---

## 8. Ordning när det startar

1. Besluta lagret (Supabase vs Sheets), §6. Delvis redan igång för event i den parallella Supabase-sessionen — **stäm av där först** så loppen landar i samma tabeller i stället för en andra variant.
2. Lyft `events_common.py` till ett källagnostiskt normaliseringspaket. Ren refaktorering, oförändrad output — verifiera genom att regenerera `events.html` och diffa mot committad fil.
3. Inför `occurrence`-modellen och skriv Strava-adaptern mot den. Eventen fortsätter rendera som idag.
4. Knyt om `event_interactions` till de nya id:na (§4), **innan** id-bytet går live.
5. Flytta race-importen till samma ramverk. Loppen får retry, aliasnormalisering och id:n; distansbuckets flyttar till normaliseringslagret.
6. Klickräkning på loppen — samma RPC-funktioner, nu att `event_id` finns för dem.
7. Delade kort-/filterkomponenter mellan de två sidorna.
8. `/admin` mot `status` och manuell redigering; `/analytics` mot klicken.

Steg 2–4 kan göras utan att loppsidan rörs, och steg 5 utan att eventsidan rörs. Ingen big bang.

---

## 9. Öppna frågor

- **Malmö.** Loppen har Malmö som egen region, eventen lägger det i Övriga landet. Ska Malmö bli en egen stad för event också? Det påverkar `STOCKHOLM_KEYWORDS`-grannarna, stadssidorna och sitemap.
- **Återkommande pass.** `WeeklyRuns` är en regel, inte ett tillfälle. Ska regeln lagras och tillfällen expanderas vid rendering (som idag, `expand_weekly_runs()` i `generate_running_events.py:185`), eller materialiseras som rader? Materialiserat blir det redigerbart i `/admin`, men måste rullas framåt.
- **Fler eventkällor än Strava.** Instagram-flödet finns redan ([sync_instagram_feed.py](sync_instagram_feed.py)). Är det en femte adapter, eller bara bildkälla?
- **Arrangörer som entitet.** Lopp har arrangörer som återkommer år efter år. Egen tabell, likt klubbarna, eller bara ett textfält?

---

## Relaterat

Allt nedan ligger också i kö bakom omstruktureringen och rör samma yta:

- `/admin` CMS + `/analytics` bakom en delad inloggning — granskningskön och klickvyn i §6.
- Nyhetsbrev (beehiiv) — veckoutskicket vill läsa samma lager.
- Gemensam header/footer — `loppkalender.html` och `events.html` är två av sidorna med handkopierad markup.
