(function () {
  'use strict';

  var MAIN_SELECTOR = 'main#main-content';
  var loadedPaths = new Set([location.pathname.replace(/\/index\.html$/, '/')]);
  var loading = false;

  var style = document.createElement('style');
  style.textContent =
    '.continuous-scroll-divider{max-width:680px;margin:0 auto;padding:2.5rem 1.5rem 0.5rem;' +
    'display:flex;align-items:center;gap:0.75rem;color:#aaa;font-size:11px;' +
    'letter-spacing:2px;text-transform:uppercase;font-weight:700;font-family:\'DM Sans\',sans-serif;}' +
    '.continuous-scroll-divider::before,.continuous-scroll-divider::after{content:\'\';flex:1;' +
    'height:1px;background:#F0D8D3;}' +
    '.continuous-post{opacity:0;animation:continuous-post-in 0.5s ease forwards;}' +
    '@keyframes continuous-post-in{from{opacity:0;transform:translateY(12px);}to{opacity:1;transform:translateY(0);}}';
  document.head.appendChild(style);

  function normalizedPath(url) {
    var p = new URL(url, location.href).pathname;
    if (!/\/$/.test(p) && !/\.[a-z0-9]+$/i.test(p)) p += '/';
    return p;
  }

  function watchForNext(scopeEl) {
    var navPrev = scopeEl.querySelector('.post-nav-prev');
    if (!navPrev) return;
    var href = navPrev.getAttribute('href');
    if (!href) return;
    var path = normalizedPath(href);
    if (loadedPaths.has(path)) return;

    var sentinel = document.createElement('div');
    sentinel.setAttribute('aria-hidden', 'true');
    navPrev.closest('.post-nav').insertAdjacentElement('afterend', sentinel);

    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting && !loading) {
          observer.disconnect();
          sentinel.remove();
          loadNext(href, path);
        }
      });
    }, { rootMargin: '800px 0px 0px 0px' });
    observer.observe(sentinel);
  }

  function loadNext(href, path) {
    loading = true;
    fetch(href)
      .then(function (r) { return r.ok ? r.text() : Promise.reject(); })
      .then(function (html) {
        var doc = new DOMParser().parseFromString(html, 'text/html');
        var newMain = doc.querySelector(MAIN_SELECTOR);
        var currentMain = document.querySelector(MAIN_SELECTOR);
        if (!newMain || !currentMain) { loading = false; return; }

        loadedPaths.add(path);

        var divider = document.createElement('div');
        divider.className = 'continuous-scroll-divider';
        divider.textContent = 'Nästa i Magazine';

        var wrapper = document.createElement('div');
        wrapper.className = 'continuous-post';
        newMain.removeAttribute('id');
        while (newMain.firstChild) wrapper.appendChild(newMain.firstChild);

        currentMain.appendChild(divider);
        currentMain.appendChild(wrapper);

        history.pushState({ continuousScroll: true }, '', href);
        document.title = doc.title;
        var canonical = document.querySelector('link[rel="canonical"]');
        var newCanonical = doc.querySelector('link[rel="canonical"]');
        if (canonical && newCanonical) canonical.setAttribute('href', newCanonical.getAttribute('href'));
        var ogUrl = document.querySelector('meta[property="og:url"]');
        var newOgUrl = doc.querySelector('meta[property="og:url"]');
        if (ogUrl && newOgUrl) ogUrl.setAttribute('content', newOgUrl.getAttribute('content'));

        var revealObserver = new IntersectionObserver(function (entries) {
          entries.forEach(function (entry) {
            if (entry.isIntersecting) entry.target.classList.add('visible');
          });
        }, { threshold: 0.1 });
        wrapper.querySelectorAll('.fade-in').forEach(function (el) { revealObserver.observe(el); });

        loading = false;
        watchForNext(wrapper);
      })
      .catch(function () { loading = false; });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  function init() {
    var main = document.querySelector(MAIN_SELECTOR);
    if (main) watchForNext(main);
  }
})();
