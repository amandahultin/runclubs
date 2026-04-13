// ── Lägg till klubb — modal + Google Sheets ──
const CLUB_SCRIPT_URL = 'https://script.google.com/macros/s/AKfycbyRh7Kka0LchiWdVKUvKx0pjcElITKeObJ6axvKToMpIRlHvuqbqZZ2bHNv00nAgyoEuQ/exec';

(function () {
  // Inject modal
  const modalHTML = `
    <div id="add-club-modal" style="
      display:none; position:fixed; inset:0; z-index:9999;
      background:rgba(28,42,69,0.5); backdrop-filter:blur(4px);
      align-items:center; justify-content:center;
    ">
      <div id="add-club-box" style="
        background:#FDFAF9; border-radius:16px; padding:2.5rem 2rem;
        max-width:400px; width:90%; text-align:center;
        box-shadow:0 20px 60px rgba(0,0,0,0.2); position:relative;
        animation: clubModalIn 0.3s ease;
      ">
        <!-- FORMULÄR -->
        <div id="add-club-form-view">
          <div style="font-size:48px; margin-bottom:0.75rem;">📍</div>
          <h3 style="
            font-family:'Archivo Black',sans-serif; font-size:20px;
            text-transform:uppercase; color:#1C2A45; margin-bottom:0.5rem;
          ">Lägg till din Run Club</h3>
          <p style="
            font-family:'DM Sans',sans-serif; font-size:13px;
            color:#888; line-height:1.6; margin-bottom:1.5rem;
          ">Fyll i klubbens namn och din e-post så hör vi av oss.</p>

          <input id="club-name" type="text" placeholder="Klubbens namn" style="
            display:block; width:100%; box-sizing:border-box;
            padding:12px 16px; margin-bottom:10px;
            border:1px solid #E8D8D3; border-radius:8px;
            font-size:14px; font-family:'DM Sans',sans-serif;
            color:#1C2A45; background:#fff; outline:none;
            transition:border-color 0.2s;
          ">
          <input id="club-email" type="email" placeholder="Din e-postadress" style="
            display:block; width:100%; box-sizing:border-box;
            padding:12px 16px; margin-bottom:1.25rem;
            border:1px solid #E8D8D3; border-radius:8px;
            font-size:14px; font-family:'DM Sans',sans-serif;
            color:#1C2A45; background:#fff; outline:none;
            transition:border-color 0.2s;
          ">
          <button id="club-submit-btn" style="
            background:#D4715E; color:#FDFAF9; border:none; border-radius:8px;
            padding:12px 32px; font-family:'DM Sans',sans-serif;
            font-size:13px; font-weight:600; cursor:pointer;
            letter-spacing:0.5px; transition:background 0.2s;
            width:100%;
          ">Skicka</button>
        </div>

        <!-- TACK -->
        <div id="add-club-thanks" style="display:none;">
          <div style="font-size:48px; margin-bottom:1rem;">🎉</div>
          <h3 style="
            font-family:'Archivo Black',sans-serif; font-size:22px;
            text-transform:uppercase; color:#1C2A45; margin-bottom:0.5rem;
          ">Tack!</h3>
          <p style="
            font-family:'DM Sans',sans-serif; font-size:14px;
            color:#666; line-height:1.7; margin-bottom:1.5rem;
          ">Vi har tagit emot din klubb och återkommer snart.</p>
          <button id="club-close-btn" style="
            background:#D4715E; color:#FDFAF9; border:none; border-radius:8px;
            padding:12px 32px; font-family:'DM Sans',sans-serif;
            font-size:13px; font-weight:600; cursor:pointer;
            letter-spacing:0.5px; transition:background 0.2s;
          ">Stäng</button>
        </div>
      </div>
    </div>
    <style>
      @keyframes clubModalIn {
        from { opacity:0; transform:scale(0.9) translateY(10px); }
        to { opacity:1; transform:scale(1) translateY(0); }
      }
      #club-name:focus, #club-email:focus { border-color: #D4715E; }
    </style>
  `;
  document.body.insertAdjacentHTML('beforeend', modalHTML);

  const modal = document.getElementById('add-club-modal');
  const formView = document.getElementById('add-club-form-view');
  const thanksView = document.getElementById('add-club-thanks');
  const nameInput = document.getElementById('club-name');
  const emailInput = document.getElementById('club-email');
  const submitBtn = document.getElementById('club-submit-btn');
  const closeBtn = document.getElementById('club-close-btn');

  function openModal() {
    formView.style.display = 'block';
    thanksView.style.display = 'none';
    nameInput.value = '';
    emailInput.value = '';
    modal.style.display = 'flex';
  }

  function closeModal() {
    modal.style.display = 'none';
  }

  modal.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });
  closeBtn.addEventListener('click', closeModal);

  // Open triggers — both #add-club-link and all .cta-btn linking to kontakt.html
  document.querySelectorAll('#add-club-link, a.cta-btn[href="kontakt.html"]').forEach((trigger) => {
    trigger.addEventListener('click', (e) => {
      e.preventDefault();
      openModal();
    });
  });

  // Submit
  submitBtn.addEventListener('click', async () => {
    const club = nameInput.value.trim();
    const email = emailInput.value.trim();
    let valid = true;

    if (!club) {
      nameInput.style.borderColor = '#e74c3c';
      valid = false;
    } else {
      nameInput.style.borderColor = '';
    }

    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      emailInput.style.borderColor = '#e74c3c';
      valid = false;
    } else {
      emailInput.style.borderColor = '';
    }

    if (!valid) return;

    const originalText = submitBtn.textContent;
    submitBtn.textContent = 'Skickar...';
    submitBtn.disabled = true;

    try {
      const params = new URLSearchParams({
        type: 'club',
        club: club,
        email: email,
        date: new Date().toISOString(),
      });
      await fetch(CLUB_SCRIPT_URL + '?' + params.toString(), { mode: 'no-cors' });
    } catch (err) {
      // no-cors — proceed anyway
    }

    submitBtn.textContent = originalText;
    submitBtn.disabled = false;
    formView.style.display = 'none';
    thanksView.style.display = 'block';
  });
})();
