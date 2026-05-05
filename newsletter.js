// ── Newsletter signup handler ──
// Two-step flow: step 1 = email (inline form), step 2 = profile fields (modal).
// Both steps send to the same Google Sheet via Apps Script.

const GOOGLE_SCRIPT_URL = 'https://script.google.com/macros/s/AKfycbw3N8tYho3ShQ9dKtSDCL1xMNyCzxkB576DBmJiempY_HLJ_jxB4A_2m0-Rwryys0Pc1Q/exec';

(function () {
  const modalHTML = `
    <div id="newsletter-modal" style="
      display:none; position:fixed; inset:0; z-index:9999;
      background:rgba(28,42,69,0.5); backdrop-filter:blur(4px);
      align-items:center; justify-content:center;
    ">
      <div id="nl-modal-box" style="
        background:#FDFAF9; border-radius:16px; padding:2.5rem 2rem;
        max-width:400px; width:90%; text-align:center;
        box-shadow:0 20px 60px rgba(0,0,0,0.2); position:relative;
      ">

        <!-- Step 2: profile fields -->
        <div id="nl-step2">
          <div style="font-size:40px; margin-bottom:0.75rem;">👟</div>
          <h3 style="
            font-family:'Archivo Black',sans-serif; font-size:20px;
            text-transform:uppercase; color:#1C2A45; margin-bottom:0.25rem;
          ">Berätta lite mer</h3>
          <p style="
            font-family:'DM Sans',sans-serif; font-size:13px;
            color:#888; line-height:1.6; margin-bottom:1.5rem;
          ">Frivilligt – hjälper oss att skräddarsy nyhetsbrev, erbjudanden och event för dig.</p>

          <!-- Gender -->
          <div style="margin-bottom:1rem; text-align:left;">
            <div style="
              font-family:'DM Sans',sans-serif; font-size:11px; font-weight:700;
              color:#1C2A45; text-transform:uppercase; letter-spacing:0.6px;
              margin-bottom:0.5rem;
            ">Kön</div>
            <div style="display:flex; gap:8px;">
              <label style="flex:1; cursor:pointer;">
                <input type="radio" name="nl-gender" value="Man" style="display:none;" class="nl-radio">
                <span class="nl-pill">Man</span>
              </label>
              <label style="flex:1; cursor:pointer;">
                <input type="radio" name="nl-gender" value="Kvinna" style="display:none;" class="nl-radio">
                <span class="nl-pill">Kvinna</span>
              </label>
              <label style="flex:1; cursor:pointer;">
                <input type="radio" name="nl-gender" value="Annat" style="display:none;" class="nl-radio">
                <span class="nl-pill">Annat</span>
              </label>
            </div>
          </div>

          <!-- Birthyear -->
          <div style="margin-bottom:1rem; text-align:left;">
            <label for="nl-birthyear" style="
              font-family:'DM Sans',sans-serif; font-size:11px; font-weight:700;
              color:#1C2A45; text-transform:uppercase; letter-spacing:0.6px;
              display:block; margin-bottom:0.5rem;
            ">Födelseår</label>
            <div style="position:relative;">
              <select id="nl-birthyear" style="
                width:100%; padding:10px 36px 10px 12px; border:2px solid #e0dbd8;
                border-radius:8px; font-family:'DM Sans',sans-serif; font-size:13px;
                color:#1C2A45; background:#fff; outline:none;
                appearance:none; -webkit-appearance:none; cursor:pointer;
              ">
                <option value="">Välj år...</option>
                ${(function() {
                  let opts = '';
                  for (let y = 2026; y >= 1940; y--) {
                    opts += '<option value="' + y + '"' + (y === 1998 ? ' selected' : '') + '>' + y + '</option>';
                  }
                  return opts;
                })()}
              </select>
              <span style="
                position:absolute; right:12px; top:50%; transform:translateY(-50%);
                pointer-events:none; color:#888; font-size:11px;
              ">▾</span>
            </div>
          </div>

          <!-- City -->
          <div style="margin-bottom:1rem; text-align:left;">
            <label for="nl-city" style="
              font-family:'DM Sans',sans-serif; font-size:11px; font-weight:700;
              color:#1C2A45; text-transform:uppercase; letter-spacing:0.6px;
              display:block; margin-bottom:0.5rem;
            ">Stad</label>
            <div style="position:relative;">
              <select id="nl-city" style="
                width:100%; padding:10px 36px 10px 12px; border:2px solid #e0dbd8;
                border-radius:8px; font-family:'DM Sans',sans-serif; font-size:13px;
                color:#1C2A45; background:#fff; outline:none;
                appearance:none; -webkit-appearance:none; cursor:pointer;
              ">
                <option value="">Välj stad...</option>
                <option value="Stockholm">Stockholm</option>
                <option value="Göteborg">Göteborg</option>
                <option value="Malmö">Malmö</option>
                <option value="Annan">Annan</option>
              </select>
              <span style="
                position:absolute; right:12px; top:50%; transform:translateY(-50%);
                pointer-events:none; color:#888; font-size:11px;
              ">▾</span>
            </div>
          </div>

          <!-- Easy pace -->
          <div style="margin-bottom:1.75rem; text-align:left;">
            <label for="nl-pace" style="
              font-family:'DM Sans',sans-serif; font-size:11px; font-weight:700;
              color:#1C2A45; text-transform:uppercase; letter-spacing:0.6px;
              display:block; margin-bottom:0.5rem;
            ">Easy pace</label>
            <div style="position:relative;">
              <select id="nl-pace" style="
                width:100%; padding:10px 36px 10px 12px; border:2px solid #e0dbd8;
                border-radius:8px; font-family:'DM Sans',sans-serif; font-size:13px;
                color:#1C2A45; background:#fff; outline:none;
                appearance:none; -webkit-appearance:none; cursor:pointer;
              ">
                <option value="">Välj tempo...</option>
                <option value="runt 5:00/km">runt 5:00/km</option>
                <option value="runt 5:30/km">runt 5:30/km</option>
                <option value="runt 6:00/km">runt 6:00/km</option>
                <option value="runt 6:30/km">runt 6:30/km</option>
                <option value="runt 7:00/km och uppåt">runt 7:00/km och uppåt</option>
              </select>
              <span style="
                position:absolute; right:12px; top:50%; transform:translateY(-50%);
                pointer-events:none; color:#888; font-size:11px;
              ">▾</span>
            </div>
          </div>

          <button id="nl-submit-step2" style="
            background:#D4715E; color:#FDFAF9; border:none; border-radius:8px;
            padding:12px 32px; font-family:'DM Sans',sans-serif; font-size:13px;
            font-weight:600; cursor:pointer; letter-spacing:0.5px;
            width:100%; margin-bottom:0.75rem; transition:background 0.2s;
          ">Slutför anmälan →</button>
          <button id="nl-skip-step2" style="
            background:none; border:none; font-family:'DM Sans',sans-serif;
            font-size:13px; color:#aaa; cursor:pointer;
            text-decoration:underline; padding:4px;
          ">Hoppa över</button>
        </div>

        <!-- Thanks -->
        <div id="nl-thanks" style="display:none;">
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
    </div>
    <style>
      @keyframes nlModalIn {
        from { opacity:0; transform:scale(0.9) translateY(10px); }
        to   { opacity:1; transform:scale(1)   translateY(0); }
      }
      #nl-modal-box.nl-animate { animation: nlModalIn 0.3s ease; }
      .nl-pill {
        display:block; padding:8px 4px; border:2px solid #e0dbd8;
        border-radius:8px; font-family:'DM Sans',sans-serif; font-size:13px;
        text-align:center; transition:border-color 0.15s, background 0.15s, color 0.15s;
      }
      .nl-radio:checked + .nl-pill {
        border-color:#D4715E; background:#FDF0ED; color:#D4715E; font-weight:600;
      }
    </style>
  `;
  document.body.insertAdjacentHTML('beforeend', modalHTML);

  const modal     = document.getElementById('newsletter-modal');
  const modalBox  = document.getElementById('nl-modal-box');
  const step2     = document.getElementById('nl-step2');
  const thanks    = document.getElementById('nl-thanks');
  const closeBtn  = document.getElementById('newsletter-modal-close');
  const submitBtn = document.getElementById('nl-submit-step2');
  const skipBtn   = document.getElementById('nl-skip-step2');

  let pendingData = null;

  function openModal() {
    modal.style.display = 'flex';
    modalBox.classList.remove('nl-animate');
    void modalBox.offsetWidth;
    modalBox.classList.add('nl-animate');
  }

  function closeModal() {
    modal.style.display = 'none';
  }

  function showStep2(data) {
    pendingData = data;
    document.querySelectorAll('input[name="nl-gender"]').forEach(r => r.checked = false);
    document.getElementById('nl-birthyear').value = '';
    document.getElementById('nl-city').value = '';
    document.getElementById('nl-pace').value = '';
    step2.style.display = 'block';
    thanks.style.display = 'none';
    openModal();
  }

  function showThanks() {
    step2.style.display = 'none';
    thanks.style.display = 'block';
  }

  async function submitToSheet(extraFields) {
    if (!pendingData) return;
    try {
      if (GOOGLE_SCRIPT_URL !== 'PASTE_YOUR_GOOGLE_SCRIPT_URL_HERE') {
        const params = new URLSearchParams({ ...pendingData, ...extraFields });
        await fetch(GOOGLE_SCRIPT_URL + '?' + params.toString(), { mode: 'no-cors' });
        if (window.dataLayer) {
          window.dataLayer.push({
            event: 'newsletter_signup',
            signup_placement: pendingData.placement,
            signup_page: pendingData.page,
          });
        }
      }
    } catch (_) {}
    pendingData = null;
  }

  closeBtn.addEventListener('click', closeModal);
  modal.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });

  submitBtn.addEventListener('click', async () => {
    const gender    = (document.querySelector('input[name="nl-gender"]:checked') || {}).value || '';
    const birthyear = document.getElementById('nl-birthyear').value.trim();
    const city      = document.getElementById('nl-city').value;
    const pace      = document.getElementById('nl-pace').value;

    submitBtn.textContent = 'Skickar...';
    submitBtn.disabled = true;
    await submitToSheet({ gender, birthyear, city, pace });
    submitBtn.textContent = 'Slutför anmälan →';
    submitBtn.disabled = false;
    showThanks();
  });

  skipBtn.addEventListener('click', async () => {
    await submitToSheet({ gender: '', birthyear: '', city: '', pace: '' });
    showThanks();
  });

  function isValidEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  }

  document.querySelectorAll('.newsletter-btn, .nl-btn').forEach((btn) => {
    btn.addEventListener('click', async (e) => {
      e.preventDefault();

      const form  = btn.closest('.newsletter-form') || btn.parentElement;
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

      const urlParams = new URLSearchParams(window.location.search);
      const utmKeys   = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term'];
      const utms      = {};
      utmKeys.forEach((k) => {
        const fromUrl = urlParams.get(k);
        if (fromUrl) {
          try { sessionStorage.setItem(k, fromUrl); } catch (_) {}
          utms[k] = fromUrl;
        } else {
          try { utms[k] = sessionStorage.getItem(k) || ''; } catch (_) { utms[k] = ''; }
        }
      });

      const placement =
        form.dataset.placement ||
        (form.closest('[data-placement]') && form.closest('[data-placement]').dataset.placement) ||
        'unknown';

      input.value = '';

      showStep2({
        email,
        page:         window.location.pathname,
        date:         new Date().toLocaleString('sv-SE', { timeZone: 'Europe/Stockholm' }),
        referrer:     document.referrer || '',
        placement,
        utm_source:   utms.utm_source   || '',
        utm_medium:   utms.utm_medium   || '',
        utm_campaign: utms.utm_campaign || '',
        utm_content:  utms.utm_content  || '',
        utm_term:     utms.utm_term     || '',
      });
    });
  });

  const stickyBtn = document.querySelector('.sticky-newsletter-btn');
  if (stickyBtn) {
    stickyBtn.addEventListener('click', (e) => {
      e.preventDefault();
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
