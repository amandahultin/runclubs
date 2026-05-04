// ── Newsletter signup handler ──
// Kopplar alla .newsletter-btn knappar till Google Sheets via Apps Script.
// Byt ut GOOGLE_SCRIPT_URL nedan mot din egen URL efter deploy.

const GOOGLE_SCRIPT_URL = 'https://script.google.com/macros/s/AKfycbyHCKDbZsRqiqsrUzCgwxesovWHo91_0ZK1Y5g3MGFCx4bh8pLzihE4Hm2_pyk-o0Jd/exec';

(function () {
  // Inject modal HTML + CSS
  const modalHTML = `
    <div id="newsletter-modal" style="
      display:none; position:fixed; inset:0; z-index:9999;
      background:rgba(28,42,69,0.5); backdrop-filter:blur(4px);
      align-items:center; justify-content:center;
    ">
      <div style="
        background:#FDFAF9; border-radius:16px; padding:2.5rem 2rem;
        max-width:380px; width:90%; text-align:center;
        box-shadow:0 20px 60px rgba(0,0,0,0.2); position:relative;
        animation: modalIn 0.3s ease;
      ">
        <div style="font-size:48px; margin-bottom:1rem;">🎉</div>
        <h3 style="
          font-family:'Archivo Black',sans-serif; font-size:22px;
          text-transform:uppercase; color:#1C2A45; margin-bottom:0.5rem;
        ">Tack!</h3>
        <p style="
          font-family:'DM Sans',sans-serif; font-size:14px;
          color:#666; line-height:1.7; margin-bottom:1.5rem;
        ">Du är nu anmäld till nyhetsbrevet. Vi hör av oss snart!</p>
        <button id="newsletter-modal-close" style="
          background:#D4715E; color:#FDFAF9; border:none; border-radius:8px;
          padding:12px 32px; font-family:'DM Sans',sans-serif;
          font-size:13px; font-weight:600; cursor:pointer;
          letter-spacing:0.5px; transition:background 0.2s;
        ">Stäng</button>
      </div>
    </div>
    <style>
      @keyframes modalIn {
        from { opacity:0; transform:scale(0.9) translateY(10px); }
        to { opacity:1; transform:scale(1) translateY(0); }
      }
    </style>
  `;
  document.body.insertAdjacentHTML('beforeend', modalHTML);

  const modal = document.getElementById('newsletter-modal');
  const closeBtn = document.getElementById('newsletter-modal-close');

  closeBtn.addEventListener('click', () => {
    modal.style.display = 'none';
  });
  modal.addEventListener('click', (e) => {
    if (e.target === modal) modal.style.display = 'none';
  });

  function showModal() {
    modal.style.display = 'flex';
  }

  function isValidEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  }

  // Attach to all newsletter forms on the page
  document.querySelectorAll('.newsletter-btn, .nl-btn').forEach((btn) => {
    btn.addEventListener('click', async (e) => {
      e.preventDefault();

      // Find the sibling input (in same .newsletter-form container)
      const form = btn.closest('.newsletter-form') || btn.parentElement;
      const input = form.querySelector('.newsletter-input, .nl-input');
      if (!input) return;

      const email = input.value.trim();

      if (!email || !isValidEmail(email)) {
        input.style.borderColor = '#e74c3c';
        input.setAttribute('placeholder', 'Ange en giltig e-postadress');
        input.focus();
        setTimeout(() => {
          input.style.borderColor = '';
          input.setAttribute('placeholder', 'din@email.se');
        }, 2000);
        return;
      }

      // Disable button while sending
      const originalText = btn.textContent;
      btn.textContent = 'Skickar...';
      btn.disabled = true;

      try {
        if (GOOGLE_SCRIPT_URL !== 'PASTE_YOUR_GOOGLE_SCRIPT_URL_HERE') {
          // Capture UTM parameters + referrer + placement for attribution.
          // UTM-parametrarna läses först från nuvarande URL, annars från sessionStorage
          // (så att en besökare som klickade en UTM-länk på IG och sen surfar runt
          //  ändå attribueras korrekt när de till slut signar up).
          const urlParams = new URLSearchParams(window.location.search);
          const utmKeys = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term'];
          const utms = {};
          utmKeys.forEach((k) => {
            const fromUrl = urlParams.get(k);
            if (fromUrl) {
              try { sessionStorage.setItem(k, fromUrl); } catch (e) {}
              utms[k] = fromUrl;
            } else {
              try { utms[k] = sessionStorage.getItem(k) || ''; } catch (e) { utms[k] = ''; }
            }
          });

          // Identifiera vilket formulär på sidan som triggade signup (hero / mid / footer etc.)
          const placement =
            form.dataset.placement ||
            (form.closest('[data-placement]') && form.closest('[data-placement]').dataset.placement) ||
            'unknown';

          const params = new URLSearchParams({
            email: email,
            page: window.location.pathname,
            date: new Date().toISOString(),
            referrer: document.referrer || '',
            placement: placement,
            utm_source: utms.utm_source || '',
            utm_medium: utms.utm_medium || '',
            utm_campaign: utms.utm_campaign || '',
            utm_content: utms.utm_content || '',
            utm_term: utms.utm_term || '',
          });
          await fetch(GOOGLE_SCRIPT_URL + '?' + params.toString(), { mode: 'no-cors' });

          // Skicka också event till dataLayer så att GTM/GA4 kan mäta signups.
          if (window.dataLayer) {
            window.dataLayer.push({
              event: 'newsletter_signup',
              signup_placement: placement,
              signup_page: window.location.pathname,
            });
          }
        }
        input.value = '';
        showModal();
      } catch (err) {
        // Show modal anyway — no-cors won't return status
        input.value = '';
        showModal();
      } finally {
        btn.textContent = originalText;
        btn.disabled = false;
      }
    });
  });

  // Also handle sticky newsletter button on nyheter.html
  const stickyBtn = document.querySelector('.sticky-newsletter-btn');
  if (stickyBtn) {
    stickyBtn.addEventListener('click', (e) => {
      e.preventDefault();
      // Scroll to the mid-page newsletter form
      const midForm = document.querySelector('.newsletter-mid');
      if (midForm) {
        midForm.scrollIntoView({ behavior: 'smooth', block: 'center' });
        setTimeout(() => {
          const input = midForm.querySelector('.newsletter-input');
          if (input) input.focus();
        }, 500);
      }
    });
  }
})();
