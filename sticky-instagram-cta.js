/**
 * Sitewide floating "follow us on Instagram" pill, bottom-right.
 * Self-contained: injects its own styles and markup so every page only
 * needs a single script tag. Dismissal is remembered in localStorage.
 */
(function () {
  if (document.getElementById('ig-sticky-wrap')) return;
  var DISMISS_KEY = 'ig-sticky-dismissed';
  if (localStorage.getItem(DISMISS_KEY) === '1') return;

  var style = document.createElement('style');
  style.textContent =
    '#ig-sticky-wrap { position: fixed; right: 18px; bottom: 18px; z-index: 999; ' +
    'opacity: 0; transform: translateY(16px); transition: opacity 0.35s ease, transform 0.35s ease; pointer-events: none; }' +
    '#ig-sticky-wrap.ig-sticky-show { opacity: 1; transform: translateY(0); pointer-events: auto; }' +
    '#ig-sticky-cta { display: flex; align-items: center; gap: 10px; background: #1C2A45; color: #FFF8F3; ' +
    'text-decoration: none; padding: 13px 20px 13px 13px; border-radius: 100px; ' +
    'box-shadow: 0 12px 30px rgba(28,42,69,0.35); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; ' +
    'font-size: 13px; font-weight: 600; line-height: 1.3; max-width: min(280px, calc(100vw - 76px)); ' +
    'transition: background 0.15s ease, transform 0.15s ease; }' +
    '#ig-sticky-cta:hover { background: #334463; transform: translateY(-2px); }' +
    '#ig-sticky-icon { width: 32px; height: 32px; border-radius: 9px; flex-shrink: 0; ' +
    'background: linear-gradient(135deg, #F58529, #DD2A7B, #8134AF); display: flex; align-items: center; justify-content: center; }' +
    '#ig-sticky-icon svg { width: 18px; height: 18px; }' +
    '#ig-sticky-close { position: absolute; top: -8px; right: -8px; width: 22px; height: 22px; border-radius: 50%; ' +
    'background: #FFF8F3; color: #1C2A45; border: 1px solid rgba(28,42,69,0.15); font-size: 14px; line-height: 1; ' +
    'cursor: pointer; display: flex; align-items: center; justify-content: center; font-family: inherit; padding: 0; }' +
    '#ig-sticky-close:hover { background: #FFDAC4; }' +
    '@media (max-width: 480px) { #ig-sticky-wrap { right: 12px; bottom: 12px; } ' +
    '#ig-sticky-cta { font-size: 12.5px; padding: 11px 16px 11px 11px; } }';
  document.head.appendChild(style);

  var wrap = document.createElement('div');
  wrap.id = 'ig-sticky-wrap';
  wrap.innerHTML =
    '<button id="ig-sticky-close" type="button" aria-label="Stäng">&times;</button>' +
    '<a id="ig-sticky-cta" href="https://www.instagram.com/runclubs.se/" target="_blank" rel="noopener">' +
      '<span id="ig-sticky-icon"><svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">' +
        '<rect x="2" y="2" width="20" height="20" rx="5" stroke="white" stroke-width="1.8"/>' +
        '<circle cx="12" cy="12" r="4.2" stroke="white" stroke-width="1.8"/>' +
        '<circle cx="17.6" cy="6.4" r="1.1" fill="white"/>' +
      '</svg></span>' +
      '<span>Nya klubbar & event - häng med oss på Instagram</span>' +
    '</a>';

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount);
  } else {
    mount();
  }

  function mount() {
    if (!document.body || document.getElementById('ig-sticky-wrap')) return;
    document.body.appendChild(wrap);

    document.getElementById('ig-sticky-close').addEventListener('click', function () {
      localStorage.setItem(DISMISS_KEY, '1');
      wrap.classList.remove('ig-sticky-show');
      setTimeout(function () { wrap.remove(); }, 350);
    });

    var shown = false;
    function show() {
      if (shown) return;
      shown = true;
      wrap.classList.add('ig-sticky-show');
      window.removeEventListener('scroll', onScroll);
    }
    function onScroll() {
      if (window.scrollY > 300) show();
    }
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
    setTimeout(show, 3500);
  }
})();
