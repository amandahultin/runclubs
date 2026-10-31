# Event & lopp — gemensam import och datamodell

> **Avskriven 2026-10-31, samma dag som den skrevs.** Skissens huvudförslag — en gemensam
> `occurrence`-tabell med typdiskriminator för event och lopp — är inte vägen framåt. Schemat
> var redan installerat och fyllt i **`runclubs-next`** när skissen skrevs, och det modellen
> där valt gäller. Det här repot avvecklas; leta inte sanningen här.
>
> Dokumentet är kortat till vad som faktiskt gäller, i stället för att lämnas kvar som en
> andra sanning.

## Vad som gäller i stället

Riktig källa: `/Users/mikael/Documents/runclubs-next`, `supabase/migrations/20261031_0001_init.sql`.

- **Separata tabeller**, ingen gemensam kärna: `public.events` och `public.races`.
- **Dubblettnycklar är länk och namn+datum**, inte `(source, source_id)`: `events.link` är unik,
  `races` har `unique (name, race_date)`. Källorna levererar inget stabilt `source_id` — det var
  skissens felaktiga antagande.
- **`events.source` är en enum** (`strava`, `eventbrite`, `facebook`, `instagram`, `manual`) plus
  `is_special`. Den skiljer *källor*, inte event från lopp.
- **`events.legacy_id`** bär de gilla/klick som redan finns och kan inte bytas ut.
- **Fasta pass är inte rader i `events`.** De ligger i `public.weekly_runs` och räknas fram per
  tillfälle i `src/lib/events.ts`.
- **Datainsamlingen är redan flyttad:** `sync/sync_events.py` → `public.events`,
  `sync/sync_races.py` → `public.races`, samma scheman som förut plus Vercel deploy-hook.

Malmö, som stod som öppen fråga här, är avgjord: `public.cities` har `malmo` som slug.

## Vad som höll av skissen

**Sidorna förblir separata** — `/events` och stadssidorna svarar på "vad händer nära mig i veckan",
loppkalendern på "vilket lopp ska jag anmäla mig till". Olika filter, tidshorisont och sökintention.
Det är också vad `runclubs-next` gör.

## Vad som inte höll

Skissen hävdade att `event_id()` i gamla `generate_running_events.py` orphanar gilla/klick: `source`
ingår i hashen, och `drop_duplicate_cards()` byter medvetet ut vilken källa som vinner för samma
klubb och dag. **Det är sant om gamla sajten men följer inte med till `runclubs-next`:**

- `sync_events.py` kör inte `drop_duplicate_cards` — Strava- och special-rader skrivs båda.
- `src/lib/event-id.ts` behåller exakt gamla formeln med `weekly_run` hårdkodad som källa, just för
  att de 868 av 1 807 interaktionerna som hänger på beräknade id ska överleva. Verifierad mot
  interaktionshistoriken.

Båda id:na finns alltså samtidigt och renderas båda. Gilla/klick tappas inte.

**Det som återstår är dubbelvisning** — två kort för samma pass när ett Strava-event och ett fast
pass sammanfaller för samma klubb och dag. Det är ett renderingsproblem i `runclubs-next`, inte ett
datamodellproblem, och det enda i den här skissen som fortfarande är olöst.
