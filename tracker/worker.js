export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === '/track') return handleTrack(request, env);
    if (url.pathname === '/dashboard') return handleDashboard(request, env);

    return new Response('Not Found', { status: 404 });
  },
};

// ── /track ────────────────────────────────────────────────────────────────────

async function handleTrack(request, env) {
  if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors() });
  if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

  let body;
  try { body = await request.json(); } catch (_) { return new Response('Bad Request', { status: 400 }); }

  const { page, url, text, type } = body;
  if (!page || !url) return new Response('Bad Request', { status: 400 });
  if (String(page).startsWith('/dashboard')) return new Response('OK', { status: 200, headers: cors() });

  try {
    await env.DB.prepare(
      'INSERT INTO click_events (ts, page, link_url, link_text, link_type) VALUES (datetime("now"), ?, ?, ?, ?)'
    ).bind(
      String(page).slice(0, 200),
      String(url).slice(0, 500),
      String(text || '').slice(0, 100),
      String(type || 'unknown')
    ).run();
  } catch (_) {
    return new Response('Error', { status: 500 });
  }

  return new Response('OK', { status: 200, headers: cors() });
}

function cors() {
  return {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
  };
}

// ── /dashboard ────────────────────────────────────────────────────────────────

async function handleDashboard(request, env) {
  const params = new URL(request.url).searchParams;
  if (params.get('key') !== env.DASHBOARD_KEY) return new Response('Unauthorized', { status: 401 });

  const key = params.get('key');

  // ── Date range ──────────────────────────────────────────────────────────────
  // Detect current UTC offset for Europe/Stockholm (handles CET/CEST automatically)
  function stockholmOffset() {
    const now = new Date();
    const utcH = now.getUTCHours();
    const sthH = parseInt(new Intl.DateTimeFormat('sv-SE', { timeZone: 'Europe/Stockholm', hour: 'numeric', hour12: false }).format(now));
    let diff = sthH - utcH;
    if (diff < -12) diff += 24;
    if (diff > 12) diff -= 24;
    return diff; // 1 (CET) or 2 (CEST)
  }
  const offset = stockholmOffset(); // 1 or 2
  const TZ = `+${offset} hours`;

  // Convert a Stockholm-local date string to a UTC datetime string for SQL filtering
  // e.g. "2026-05-15" with offset 2 → "2026-05-14 22:00:00"
  function toUtcFilter(dateStr) {
    const d = new Date(dateStr + 'T00:00:00Z');
    d.setUTCHours(d.getUTCHours() - offset);
    return d.toISOString().slice(0, 19).replace('T', ' ');
  }

  const todayStr = new Date().toISOString().slice(0, 10);

  function daysAgo(n) {
    const d = new Date(); d.setDate(d.getDate() - n); return d.toISOString().slice(0, 10);
  }
  function nextDay(s) {
    const d = new Date(s + 'T00:00:00Z'); d.setDate(d.getDate() + 1); return d.toISOString().slice(0, 10);
  }

  let startDate = params.get('start') || daysAgo(6);
  let endDate   = params.get('end')   || todayStr;
  // clamp end to today
  if (endDate > todayStr) endDate = todayStr;
  const endExcl = nextDay(endDate);

  // Preset definitions for quick links
  const presets = [
    { label: 'Idag',     start: todayStr,    end: todayStr },
    { label: 'I går',    start: daysAgo(1),  end: daysAgo(1) },
    { label: '7 dagar',  start: daysAgo(6),  end: todayStr },
    { label: '30 dagar', start: daysAgo(29), end: todayStr },
    { label: '90 dagar', start: daysAgo(89), end: todayStr },
  ];

  const NAV_URLS = `('https://runclubs.se/','https://runclubs.se/stockholm','https://runclubs.se/goteborg','https://runclubs.se/malmo','https://runclubs.se/events','https://runclubs.se/nyheter','https://runclubs.se/loppkalender','https://runclubs.se/om-oss','https://runclubs.se/kontakt','https://runclubs.se/samarbeta')`;

  const W = `ts >= ? AND ts < ?`;
  const filterStart = toUtcFilter(startDate);
  const filterEnd   = toUtcFilter(endExcl);

  const [topLinks, byPage, totals, recentRows, topClubs, topEventCards, dailyClicks, hourlyClicks, dowClicks] = await Promise.all([
    env.DB.prepare(`SELECT link_url, link_text, link_type, COUNT(*) as clicks FROM click_events WHERE ${W} GROUP BY link_url, link_type ORDER BY clicks DESC LIMIT 30`).bind(filterStart, filterEnd).all(),
    env.DB.prepare(`SELECT page, COUNT(*) as clicks FROM click_events WHERE ${W} GROUP BY page ORDER BY clicks DESC LIMIT 20`).bind(filterStart, filterEnd).all(),
    env.DB.prepare(`SELECT link_type, COUNT(*) as clicks FROM click_events WHERE ${W} GROUP BY link_type`).bind(filterStart, filterEnd).all(),
    env.DB.prepare(`SELECT datetime(ts, '${TZ}') as ts, page, link_url, link_text, link_type FROM click_events ORDER BY id DESC LIMIT 20`).all(),
    env.DB.prepare(`SELECT link_url, COUNT(*) as clicks FROM click_events WHERE link_type='internal' AND link_url NOT IN ${NAV_URLS} AND link_url NOT LIKE '%/events%' AND link_url NOT LIKE '%-running-events%' AND link_url NOT LIKE '%/loppkalender%' AND link_url NOT LIKE '%/nyheter%' AND link_url NOT LIKE '%/om-oss%' AND link_url NOT LIKE '%/kontakt%' AND link_url NOT LIKE '%/samarbeta%' AND ${W} GROUP BY link_url ORDER BY clicks DESC LIMIT 20`).bind(filterStart, filterEnd).all(),
    env.DB.prepare(`SELECT link_url, link_text, link_type, COUNT(*) as clicks FROM click_events WHERE (page='/' OR page='/events' OR page='/stockholm' OR page='/goteborg' OR page='/malmo' OR page LIKE '%-running-events') AND link_url NOT IN ${NAV_URLS} AND ${W} GROUP BY link_url, link_text ORDER BY clicks DESC LIMIT 20`).bind(filterStart, filterEnd).all(),
    env.DB.prepare(`SELECT date(datetime(ts, '${TZ}')) as day, COUNT(*) as clicks FROM click_events WHERE ${W} GROUP BY day ORDER BY day`).bind(filterStart, filterEnd).all(),
    env.DB.prepare(`SELECT strftime('%H', datetime(ts, '${TZ}')) as hour, COUNT(*) as clicks FROM click_events WHERE ${W} GROUP BY hour ORDER BY hour`).bind(filterStart, filterEnd).all(),
    env.DB.prepare(`SELECT strftime('%w', datetime(ts, '${TZ}')) as dow, COUNT(*) as clicks FROM click_events WHERE ${W} GROUP BY dow ORDER BY dow`).bind(filterStart, filterEnd).all(),
  ]);

  const totalClicks = (totals.results || []).reduce((s, r) => s + r.clicks, 0);
  const internalClicks = (totals.results || []).find(r => r.link_type === 'internal')?.clicks || 0;
  const externalClicks = (totals.results || []).find(r => r.link_type === 'external')?.clicks || 0;

  function fmtDate(s) {
    const months = ['jan','feb','mar','apr','maj','jun','jul','aug','sep','okt','nov','dec'];
    const [y, m, d] = s.split('-');
    return `${parseInt(d)} ${months[parseInt(m)-1]} ${y}`;
  }
  const rangeLabel = startDate === endDate ? fmtDate(startDate) : `${fmtDate(startDate)} – ${fmtDate(endDate)}`;

  const html = `<!DOCTYPE html>
<html lang="sv">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>runclubs.se — klickstatistik</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'DM Sans', system-ui, sans-serif; background: #f8f8f6; color: #1a1a1a; padding: 2rem 1rem; }
  h1 { font-size: 1.4rem; font-weight: 700; margin-bottom: 0.25rem; }
  .meta { color: #666; font-size: 0.85rem; margin-bottom: 1.25rem; }
  .date-picker { display: flex; flex-wrap: wrap; align-items: center; gap: 0.75rem; margin-bottom: 2rem; background: #fff; border: 1px solid #e8e8e4; border-radius: 12px; padding: 1rem 1.25rem; }
  .presets { display: flex; gap: 0.4rem; flex-wrap: wrap; }
  .preset { padding: 0.3rem 0.75rem; border-radius: 99px; border: 1.5px solid #ddd; font-size: 0.82rem; text-decoration: none; color: #444; white-space: nowrap; }
  .preset.active { background: #1a1a1a; color: #fff; border-color: #1a1a1a; }
  .date-sep { color: #bbb; font-size: 0.9rem; flex-shrink: 0; }
  .date-form { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; margin-left: auto; }
  .date-form input[type=date] { border: 1.5px solid #ddd; border-radius: 8px; padding: 0.3rem 0.6rem; font-size: 0.82rem; color: #333; background: #fff; }
  .date-form button { padding: 0.3rem 0.9rem; border-radius: 8px; border: none; background: #1a1a1a; color: #fff; font-size: 0.82rem; cursor: pointer; }
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 1rem; margin-bottom: 2rem; }
  .stat { background: #fff; border-radius: 12px; padding: 1.25rem 1.5rem; border: 1px solid #e8e8e4; }
  .stat-num { font-size: 2rem; font-weight: 700; line-height: 1; }
  .stat-label { font-size: 0.78rem; color: #888; margin-top: 0.3rem; text-transform: uppercase; letter-spacing: 0.5px; }
  .section { background: #fff; border-radius: 12px; padding: 1.5rem; border: 1px solid #e8e8e4; margin-bottom: 1.5rem; }
  .section h2 { font-size: 0.9rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: #888; margin-bottom: 1rem; }
  table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
  th { text-align: left; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.4px; color: #aaa; padding: 0 0 0.5rem; }
  td { padding: 0.45rem 0; border-bottom: 1px solid #f0f0ec; vertical-align: top; }
  tr:last-child td { border-bottom: none; }
  .pill { display: inline-block; padding: 0.1rem 0.5rem; border-radius: 99px; font-size: 0.72rem; font-weight: 600; }
  .pill-internal { background: #D8F3DC; color: #1B4332; }
  .pill-external { background: #FEE2E2; color: #991B1B; }
  .url { max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #555; font-size: 0.8rem; }
  .cnt { font-weight: 700; text-align: right; padding-left: 1rem; white-space: nowrap; }
  .bar-wrap { width: 80px; background: #f0f0ec; border-radius: 4px; height: 6px; margin-top: 5px; }
  .bar { height: 6px; border-radius: 4px; background: #1a1a1a; }
  .ts { color: #aaa; font-size: 0.75rem; white-space: nowrap; }
  .charts-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; margin-bottom: 1.5rem; }
  .charts-grid .section { margin-bottom: 0; }
  .chart-wrap { position: relative; height: 220px; }
  .chart-wrap--tall { height: 260px; }
  @media (max-width: 640px) { .charts-grid { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<h1>Klickstatistik — runclubs.se</h1>
<p class="meta">${rangeLabel} &nbsp;·&nbsp; Hämtad ${new Date().toLocaleString('sv-SE', { timeZone: 'Europe/Stockholm', dateStyle: 'short', timeStyle: 'short' })}</p>
<div class="date-picker">
  <div class="presets">
    ${presets.map(p => {
      const active = p.start === startDate && p.end === endDate ? ' active' : '';
      return `<a href="?key=${encodeURIComponent(key)}&start=${p.start}&end=${p.end}" class="preset${active}">${p.label}</a>`;
    }).join('')}
  </div>
  <span class="date-sep">|</span>
  <form method="get" class="date-form">
    <input type="hidden" name="key" value="${esc(key)}">
    <input type="date" name="start" value="${startDate}" max="${todayStr}">
    <span class="date-sep">—</span>
    <input type="date" name="end" value="${endDate}" max="${todayStr}">
    <button type="submit">Applicera</button>
  </form>
</div>
<div class="stats">
  <div class="stat"><div class="stat-num">${totalClicks}</div><div class="stat-label">Totalt klick</div></div>
  <div class="stat"><div class="stat-num">${internalClicks}</div><div class="stat-label">Interna klick</div></div>
  <div class="stat"><div class="stat-num">${externalClicks}</div><div class="stat-label">Externa klick</div></div>
</div>
<div class="section">
  <h2>Klick per dag</h2>
  <div class="chart-wrap chart-wrap--tall"><canvas id="chart-daily"></canvas></div>
</div>
<div class="charts-grid">
  <div class="section">
    <h2>Klick per timme</h2>
    <div class="chart-wrap"><canvas id="chart-hourly"></canvas></div>
  </div>
  <div class="section">
    <h2>Klick per veckodag</h2>
    <div class="chart-wrap"><canvas id="chart-dow"></canvas></div>
  </div>
</div>
<div class="charts-grid">
  <div class="section">
    <h2>Intern / Extern fördelning</h2>
    <div class="chart-wrap"><canvas id="chart-split"></canvas></div>
  </div>
  <div class="section">
    <h2>Vilka sidor klickar användare ifrån — topp 8</h2>
    <div class="chart-wrap"><canvas id="chart-pages"></canvas></div>
  </div>
</div>
<div class="section">
  <h2>Mest klickade länkar</h2>
  <table>
    <thead><tr><th>Länk</th><th>Text</th><th style="text-align:right">Klick</th></tr></thead>
    <tbody>${(topLinks.results || []).map(r => {
      const pct = Math.round((r.clicks / ((topLinks.results[0]?.clicks) || 1)) * 100);
      return `<tr><td><span class="pill pill-${r.link_type}">${r.link_type === 'internal' ? 'intern' : 'extern'}</span><br><span class="url" title="${esc(r.link_url)}">${esc(r.link_url)}</span></td><td style="color:#666">${esc(r.link_text || '—')}</td><td class="cnt">${r.clicks}<div class="bar-wrap"><div class="bar" style="width:${pct}%"></div></div></td></tr>`;
    }).join('')}</tbody>
  </table>
</div>
<div class="section">
  <h2>Vilka sidor klickar användare ifrån</h2>
  <table>
    <thead><tr><th>Sida</th><th style="text-align:right">Klick</th></tr></thead>
    <tbody>${(byPage.results || []).map(r => {
      const pct = Math.round((r.clicks / ((byPage.results[0]?.clicks) || 1)) * 100);
      return `<tr><td>${esc(r.page)}</td><td class="cnt">${r.clicks}<div class="bar-wrap"><div class="bar" style="width:${pct}%"></div></div></td></tr>`;
    }).join('')}</tbody>
  </table>
</div>
<div class="section">
  <h2>Populäraste klubbar</h2>
  <table>
    <thead><tr><th>Klubb</th><th style="text-align:right">Klick</th></tr></thead>
    <tbody>${(topClubs.results || []).map(r => {
      const pct = Math.round((r.clicks / ((topClubs.results[0]?.clicks) || 1)) * 100);
      const name = clubName(r.link_url);
      return `<tr><td><span class="url" title="${esc(r.link_url)}">${esc(name)}</span></td><td class="cnt">${r.clicks}<div class="bar-wrap"><div class="bar" style="width:${pct}%"></div></div></td></tr>`;
    }).join('')}</tbody>
  </table>
</div>
<div class="section">
  <h2>Mest klickade event-kort</h2>
  <table>
    <thead><tr><th>Klubb</th><th>Event</th><th style="text-align:right">Klick</th></tr></thead>
    <tbody>${(topEventCards.results || []).map(r => {
      const pct = Math.round((r.clicks / ((topEventCards.results[0]?.clicks) || 1)) * 100);
      const name = clubName(r.link_url);
      const eventInfo = (r.link_text || '').replace(/läs mer\s*→?/gi, '').replace(/\s+/g, ' ').trim().slice(0, 80);
      return `<tr><td style="white-space:nowrap">${esc(name)}<br><span class="pill pill-${r.link_type}" style="margin-top:2px">${r.link_type === 'internal' ? 'intern' : 'extern'}</span></td><td style="color:#555;font-size:0.8rem">${esc(eventInfo)}</td><td class="cnt">${r.clicks}<div class="bar-wrap"><div class="bar" style="width:${pct}%"></div></div></td></tr>`;
    }).join('')}</tbody>
  </table>
</div>
<div class="section">
  <h2>Senaste klick</h2>
  <table>
    <thead><tr><th>Tid</th><th>Sida</th><th>Länk</th><th>Typ</th></tr></thead>
    <tbody>${(recentRows.results || []).map(r => `<tr><td class="ts">${r.ts}</td><td style="color:#555;font-size:0.8rem">${esc(r.page)}</td><td><span class="url" title="${esc(r.link_url)}">${esc(r.link_text || r.link_url)}</span></td><td><span class="pill pill-${r.link_type}">${r.link_type === 'internal' ? 'intern' : 'extern'}</span></td></tr>`).join('')}</tbody>
  </table>
</div>
<script>
(function () {
  Chart.defaults.font.family = "'DM Sans', system-ui, sans-serif";
  Chart.defaults.color = '#888';
  Chart.defaults.plugins.legend.display = false;

  const daily   = ${JSON.stringify(dailyClicks.results  || [])};
  const hourly  = ${JSON.stringify(hourlyClicks.results || [])};
  const dow     = ${JSON.stringify(dowClicks.results    || [])};
  const split   = ${JSON.stringify(totals.results       || [])};
  const pages   = ${JSON.stringify((byPage.results || []).slice(0, 8))};

  const gridColor = '#f0f0ec';
  const ink = '#1a1a1a';
  const yAxis = { beginAtZero: true, grid: { color: gridColor }, ticks: { precision: 0 } };
  const xAxis = { grid: { display: false } };

  // 1. Daily trend — fill gaps so missing days show as 0
  const dayMap = {};
  daily.forEach(r => { dayMap[r.day] = r.clicks; });
  const allDays = [], allCounts = [];
  const cur = new Date('${startDate}T00:00:00Z'), last = new Date('${endDate}T00:00:00Z');
  while (cur <= last) {
    const k = cur.toISOString().slice(0, 10);
    allDays.push(k.slice(5));   // "MM-DD"
    allCounts.push(dayMap[k] || 0);
    cur.setDate(cur.getDate() + 1);
  }
  new Chart(document.getElementById('chart-daily'), {
    type: 'line',
    data: { labels: allDays, datasets: [{ data: allCounts, borderColor: ink, backgroundColor: 'rgba(26,26,26,0.07)', fill: true, tension: 0.35, pointRadius: allDays.length > 20 ? 0 : 3, pointHoverRadius: 5, borderWidth: 2 }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { title: t => t[0].label } } }, scales: { x: { ...xAxis, ticks: { maxTicksLimit: 10 } }, y: yAxis } }
  });

  // 2. Hourly
  const hMap = {}; hourly.forEach(r => { hMap[r.hour] = r.clicks; });
  const hrs = Array.from({ length: 24 }, (_, i) => i.toString().padStart(2, '0'));
  new Chart(document.getElementById('chart-hourly'), {
    type: 'bar',
    data: { labels: hrs.map(h => h + ':00'), datasets: [{ data: hrs.map(h => hMap[h] || 0), backgroundColor: ink, borderRadius: 3 }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { ...xAxis, ticks: { maxTicksLimit: 8 } }, y: yAxis } }
  });

  // 3. Day of week (SQLite: 0=Sun … 6=Sat, reorder to Mon-first)
  const dowLabels = ['Mån','Tis','Ons','Tor','Fre','Lör','Sön'];
  const dowOrder  = [1, 2, 3, 4, 5, 6, 0];
  const dMap = {}; dow.forEach(r => { dMap[r.dow] = r.clicks; });
  new Chart(document.getElementById('chart-dow'), {
    type: 'bar',
    data: { labels: dowLabels, datasets: [{ data: dowOrder.map(i => dMap[String(i)] || 0), backgroundColor: ink, borderRadius: 3 }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: xAxis, y: yAxis } }
  });

  // 4. Internal / External donut
  const intC = split.find(r => r.link_type === 'internal')?.clicks || 0;
  const extC = split.find(r => r.link_type === 'external')?.clicks || 0;
  new Chart(document.getElementById('chart-split'), {
    type: 'doughnut',
    data: { labels: ['Interna', 'Externa'], datasets: [{ data: [intC, extC], backgroundColor: ['#1B4332', '#991B1B'], borderWidth: 0, hoverOffset: 6 }] },
    options: { responsive: true, maintainAspectRatio: false, cutout: '62%', plugins: { legend: { display: true, position: 'bottom' } } }
  });

  // 5. Top pages horizontal bar
  new Chart(document.getElementById('chart-pages'), {
    type: 'bar',
    data: {
      labels: pages.map(r => r.page || '/'),
      datasets: [{ data: pages.map(r => r.clicks), backgroundColor: ink, borderRadius: 3 }]
    },
    options: {
      indexAxis: 'y',
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { x: { ...yAxis, grid: { color: gridColor } }, y: { grid: { display: false }, ticks: { font: { size: 11 } } } }
    }
  });
})();
</script>
</body>
</html>`;

  return new Response(html, {
    headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store', 'X-Robots-Tag': 'noindex' },
  });
}

function clubName(url) {
  try {
    const parts = new URL(url).pathname.replace(/\/$/, '').split('/').filter(Boolean);
    const slug = (parts[parts.length - 1] || '').replace(/\.html$/, '');
    return slug.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
  } catch (_) { return url; }
}

function esc(str) {
  return String(str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
