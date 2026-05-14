(function () {
  var ENDPOINT = 'https://runclubs-tracker.amandajenny-hultin.workers.dev/track';
  var host = location.hostname;

  document.addEventListener('click', function (e) {
    var a = e.target.closest('a');
    if (!a || !a.href) return;

    var url = a.href;
    // Skip anchor-only links and mailto/tel
    if (url.startsWith('#') || /^(mailto|tel):/.test(url)) return;

    var isExternal = true;
    try {
      isExternal = new URL(url).hostname !== host;
    } catch (_) {}

    var payload = JSON.stringify({
      page: location.pathname,
      url: url.slice(0, 500),
      text: (a.innerText || a.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 100),
      type: isExternal ? 'external' : 'internal'
    });

    if (navigator.sendBeacon) {
      navigator.sendBeacon(ENDPOINT, payload);
    } else {
      fetch(ENDPOINT, { method: 'POST', body: payload, headers: { 'Content-Type': 'application/json' }, keepalive: true });
    }
  });
})();
