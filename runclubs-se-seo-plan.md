# runclubs.se — SEO & Indexing Action Plan

A prioritized, step-by-step plan to bring runclubs.se up to current Google indexing and Core Web Vitals standards. Steps are ordered so that earlier work unblocks or amplifies later work.

> Note: This plan was produced without direct access to runclubs.se or the linked PageSpeed Insights reports (network allowlist blocked the fetches). Steps marked **(verify)** should be checked against the live site before doing the work.

---

## Phase 1 — Foundations (Day 1)

These are the prerequisites for everything else. Do not skip.

1. **Verify ownership in Google Search Console** for both `https://runclubs.se` and `https://www.runclubs.se` (and the http variants). Use a DNS TXT record so the verification persists across hosting changes.
2. **Set the canonical host** (with-www or apex — pick one) and 301-redirect all other variants to it. Confirm only the canonical version is indexable.
3. **Confirm HTTPS everywhere.** No mixed content, HSTS header set, valid certificate, no redirect chains.
4. **Connect Bing Webmaster Tools** as well — relevant in Sweden (Edge default search).
5. **Install / verify GA4 + Search Console linking** so you can correlate search queries with on-site behavior.
6. **Set up Google Business Profile** if applicable (for any physical "club hub" or location).

## Phase 2 — Crawlability & Indexing (Days 1–2)

7. **Audit `robots.txt`.** Make sure it does not block `/`, CSS, JS, or images. Reference the canonical sitemap URL.
8. **Generate and submit an XML sitemap** at `/sitemap.xml`. Include only canonical, indexable URLs (clubs, cities, events). Submit via Search Console.
9. **Add canonical tags** (`<link rel="canonical">`) on every page, pointing to the preferred URL. Critical for paginated club lists, filter URLs, and city pages with similar content.
10. **Audit URL structure.** Use clean, lowercase, hyphenated, descriptive Swedish slugs — e.g. `/loparklubbar/stockholm/sodermalm/` — not query strings or IDs. **(verify)**
11. **Run Search Console's URL Inspection** on the homepage, a city page, and a club page. Confirm Google can render them; fix any "Discovered – not indexed" or "Crawled – not indexed" issues.
12. **Fix soft 404s and redirect chains.** Each redirect should be a single 301 hop.
13. **Pagination & faceted navigation:** if club lists paginate, give each page a self-canonical and unique title; if filters create infinite URL combinations, block them in robots.txt or use `rel="nofollow"` on filter links.

## Phase 3 — On-Page SEO (Week 1)

14. **Write unique `<title>` tags** for every template (homepage, city, club, event, blog post). Pattern suggestion: `Löparklubbar i {Stad} | runclubs.se` for city pages; `{Klubbnamn} – {Stad} löparklubb | runclubs.se` for club pages. Keep under ~60 characters.
15. **Write unique meta descriptions** (~150–160 chars) that include the search intent ("Hitta löparklubbar i…") and a soft CTA.
16. **Heading hierarchy:** exactly one `<h1>` per page, then `<h2>`/`<h3>` in nested order. The H1 should match the search intent of the page.
17. **Body copy:** every city/club page needs at least 150–300 words of unique, useful Swedish prose — meeting times, pace levels, distance, who it's for, contact info. Thin pages are the most common reason directory sites underperform.
18. **Internal linking:** from the homepage and from each city page, link to the top clubs; from each club page, link back to its city and to nearby clubs. Use descriptive anchor text in Swedish ("löparklubbar i Göteborg") rather than "läs mer".
19. **Image SEO:** every image needs a descriptive `alt` (not "image1.jpg"), a meaningful filename, lazy-loading (`loading="lazy"`) on below-the-fold images, and modern format (WebP or AVIF).
20. **Avoid duplicate content** between city pages — vary intro copy, club selection, and metadata.

## Phase 4 — Structured Data (Week 1–2)

21. **`Organization` schema** on the homepage with logo, sameAs links to social profiles.
22. **`WebSite` schema with `SearchAction`** — enables the sitelinks search box in Google.
23. **`SportsClub` or `LocalBusiness` (Organization subtype) schema** on each club page with `name`, `address` (PostalAddress), `geo`, `url`, `image`, `sport: "Running"`.
24. **`Event` schema** for upcoming runs / group sessions — `name`, `startDate`, `location`, `eventStatus`, `eventAttendanceMode`. This is high-leverage; events get rich results in Google.
25. **`BreadcrumbList` schema** on city/club pages.
26. **Validate everything** with the Rich Results Test and the Schema.org validator. Re-run after every template change.

## Phase 5 — Core Web Vitals & PageSpeed (Week 2)

The standard 75th-percentile thresholds are LCP < 2.5s, INP < 200ms, CLS < 0.1. Target these on both mobile and desktop.

27. **Identify and optimize the LCP element.** Usually a hero image or H1. Pre-load it (`<link rel="preload" as="image" fetchpriority="high">`), serve modern formats, and make sure no JS or CSS is blocking it.
28. **Eliminate render-blocking resources.** Inline critical CSS for above-the-fold; defer / async non-critical JS. Avoid synchronous third-party scripts in `<head>`.
29. **Compress and resize images.** Serve responsive sizes via `srcset`. Convert PNG/JPG to WebP/AVIF. Strip EXIF metadata.
30. **Lazy-load below-the-fold images and iframes** with `loading="lazy"`. Never lazy-load the LCP element.
31. **Reduce JavaScript:** code-split, tree-shake, remove unused libraries, defer analytics until after LCP. Audit any heavy widgets (maps, social embeds) — load on interaction.
32. **Reserve space for ads, embeds, and images** with explicit `width`/`height` or `aspect-ratio` to keep CLS < 0.1.
33. **Cache and CDN:** set long `Cache-Control` headers on static assets, use a CDN (Cloudflare/Bunny/Fastly) — especially for users outside Sweden.
34. **HTTP/2 or HTTP/3** at the server level; enable Brotli compression.
35. **Re-test in PageSpeed Insights** for both form factors and confirm field data ("Origin Summary") improves over the next 28 days — that's the rolling window CrUX uses.

## Phase 6 — Mobile & Accessibility (Week 2)

36. **Mobile-first check:** the mobile version is what Google indexes. All content, links, and structured data on desktop must also be present on mobile.
37. **Tap targets** ≥ 48×48 px, no horizontal scroll, legible base font size (≥ 16px).
38. **Run Lighthouse Accessibility audit** — fix contrast, missing labels, ARIA. Accessibility correlates with rankings via better engagement signals.

## Phase 7 — Local & Language Signals (Week 2–3)

39. **Set HTML `lang="sv"`** (or per-page if multilingual).
40. **`hreflang` tags** if you ever publish English versions; otherwise skip.
41. **Use Swedish characters (å, ä, ö) correctly** in titles, headings, URLs (or transliterate consistently — pick one and don't mix).
42. **Geo-targeting in Search Console**: set country target to Sweden (the .se ccTLD already signals this, but confirm).
43. **NAP consistency:** name, address, phone for each club must match across the site, Google Business Profile, and any partner directories.

## Phase 8 — Content & Authority (Week 3+)

44. **Build city hub pages** for the top Swedish cities (Stockholm, Göteborg, Malmö, Uppsala, Linköping, Umeå, etc.) — each a genuine guide, not a thin index.
45. **Publish editorial content**: "Bästa löparrundor i Stockholm", "Hur du väljer löparklubb", race calendars. This drives long-tail traffic and earns links.
46. **Earn backlinks** from Swedish running media (Runner's World Sweden), event organizers (Stockholm Marathon, Göteborgsvarvet), local press, and partner clubs that you list — ask for a reciprocal link.
47. **Encourage clubs you list to link back** with a snippet/badge ("Listed on runclubs.se").
48. **Refresh content quarterly** — Google rewards freshness, and club details (meet times, contacts) drift fast.

## Phase 9 — Monitoring (Ongoing)

49. **Weekly:** check Search Console for new "Coverage" errors, manual actions, security issues, and Core Web Vitals report regressions.
50. **Monthly:** review top queries, top pages, and CTR. Optimize titles/descriptions for any high-impression / low-CTR pages.
51. **Quarterly:** full re-crawl with Screaming Frog (free up to 500 URLs) or Sitebulb. Compare against last quarter.
52. **Set up alerts** in Search Console for indexing drops and CWV regressions.

---

## Quick wins to do first (in order)
1. Verify in Search Console + submit sitemap.
2. Run URL Inspection on home + 1 city + 1 club page; fix anything not indexable.
3. Add unique titles/meta descriptions across templates.
4. Add `Organization`, `WebSite`, `Event`, and `SportsClub` structured data.
5. Convert hero images to WebP, preload the LCP image, defer non-critical JS.
6. Re-test in PageSpeed Insights and Search Console after 14 days.

## Reference docs
- [Google SEO Starter Guide](https://developers.google.com/search/docs/fundamentals/seo-starter-guide)
- [Google Search Essentials](https://developers.google.com/search/docs/essentials)
- [Web.dev — Core Web Vitals](https://web.dev/articles/vitals)
- [Understanding Core Web Vitals & Search](https://developers.google.com/search/docs/appearance/core-web-vitals)
- [PageSpeed Insights](https://pagespeed.web.dev/)
- Webmaster Checklist: https://g.co/WebmasterChecklist
