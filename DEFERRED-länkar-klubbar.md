# Avvaktande länkuppdateringar

Du valde att vänta med att uppdatera sociala länkar tills du bestämt hur de ska visas på sajten (direkt via kortklick, separat ikon, eller på egna klubbsidor som byggs senare). Här ligger länkarna sparade så inget glöms bort.

---

## Stockholm

### Söderlöparna Stockholm
- **Har ingen Instagram** — använd Facebook-gruppen
- Facebook: https://www.facebook.com/groups/1049496151763769/
- Plats idag: kort på `stockholm.html` (länkar till generiska `klubb.html`)

### Runday
- Lägg till Facebook i länkningen: https://www.facebook.com/RundaySweden
- Plats idag: kort på `stockholm.html` (länkar till generiska `klubb.html`)

### YMR Track Club
- Instagram: https://www.instagram.com/ymrstockholm/
- Plats idag: kort på `stockholm.html` (länkar till generiska `klubb.html`)

### Mikkeller Running Club (Stockholm)
- Instagram: https://www.instagram.com/mrc_sthlm/
- Plats idag: kort på `stockholm.html` (länkar till generiska `klubb.html`)

### Burgers 'N' Brew Run Crew
- Instagram: https://www.instagram.com/bnbrc_/
- Strava: https://www.strava.com/clubs/bnbrc
- Plats idag: kort på `stockholm.html` (länkar till generiska `klubb.html`)

### Svedjans Löpsällskap *(ny)*
- Instagram: https://www.instagram.com/svedjanslopsallskap/
- Strava: https://www.strava.com/clubs/1549670
- Plats idag: kort på `stockholm.html` (länkar till generiska `klubb.html`)

### &morerunning *(ny)*
- Instagram: https://www.instagram.com/andmorerunning/
- Plats idag: kort på `stockholm.html` (länkar till generiska `klubb.html`)

### Löpning för tjejer *(ny)*
- **Facebook-grupp (ingen Instagram):** https://www.facebook.com/groups/785873753043427/
- Plats idag: kort på `stockholm.html` (länkar till generiska `klubb.html`)

### Högdalen Run Club *(ny)*
- Instagram: https://www.instagram.com/hogdalenrunclub/
- Strava: https://www.strava.com/clubs/1162127
- Plats idag: kort på `stockholm.html` (länkar till generiska `klubb.html`)

### Pulse Pacers *(ny)*
- Instagram: https://www.instagram.com/pulse.pacers/
- Strava: https://www.strava.com/clubs/pulsepacers
- Plats idag: kort på `stockholm.html` (länkar till generiska `klubb.html`)

### Solmates Runclub *(ny)*
- Instagram: https://www.instagram.com/solematessthlm/
- Strava: https://www.strava.com/clubs/1377613
- Plats idag: kort på `stockholm.html` (länkar till generiska `klubb.html`)

---

## Göteborg

### She Runs Club *(ny)*
- Instagram: https://www.instagram.com/she.runs.club/
- Strava: https://www.strava.com/clubs/sherunsclub
- Plats idag: kort på `goteborg.html` (länkar till generiska `klubb.html`)

### Core Run Club *(ny)*
- Instagram: https://www.instagram.com/corerunclubgbg/
- Strava: https://www.strava.com/clubs/1921810
- Plats idag: kort på `goteborg.html` (länkar till generiska `klubb.html`)

### ESS Runners Club *(ny)*
- Instagram: https://www.instagram.com/essrunnersclub/
- Strava: https://www.strava.com/clubs/1597269
- Plats idag: kort på `goteborg.html` (länkar till generiska `klubb.html`)

### Måndagsklubben_gbg *(ny)*
- Instagram: https://www.instagram.com/mandagsklubben_gbg/
- Strava: https://www.strava.com/clubs/1184888
- Plats idag: kort på `goteborg.html` (länkar till generiska `klubb.html`)

---

## Malmö

### MRC Malmö (Mikkeller Running Club Malmö)
- Instagram: https://www.instagram.com/mrc_malmo/
- Plats idag: **egen sida** — `mrc-malmo.html`
- **Detta är en trivialfix**: det finns redan ett Instagram-fält på sidan. Leta efter `<a href="https://www.instagram.com/` på `mrc-malmo.html` och byt ut URL:en till den nya. En enda rad behöver ändras.

---

## Rekommenderade designval när du kommer tillbaka till detta

**Alt A — Kortet leder direkt till sociala kanalen** (snabbaste UX-vinsten)
Istället för `<a href="klubb" class="club-card">` → `<a href="https://instagram.com/..." target="_blank" rel="noopener" class="club-card">`. Lägg till en liten IG/FB-logo i hörnet av kortet så användaren förstår vart det leder.

**Alt B — Egen klubbsida med Instagram-CTA** (som `yo-running-club.html`)
Bygger varje klubb en egen sida (tar tid men är det som ger SEO-fördelar). Instagram-länken läggs in där som en CTA-knapp i samma stil som på existerande klubbsidor.

**Alt C — Liten social-ikon på kortet, huvudklick går kvar till klubb.html**
Behåll kortets huvudklick till klubb.html tills vidare, men lägg till en liten Instagram/Facebook-ikon i kortets hörn som öppnar sociala kanalen i ny flik.

Av de tre är **Alt A** den som ger mest nytta per arbetsinsats *innan* du hinner bygga egna klubbsidor — sen kan du successivt uppgradera varje kort till Alt B när klubben börjar engagera sig.
