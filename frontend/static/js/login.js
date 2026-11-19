(function () {
  const form = $('#login-form');
  const errEl = $('#login-error');
  const next = new URLSearchParams(location.search).get('next');
  const safeNext = next && next.startsWith('/') && !next.startsWith('//') ? next : '/';
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    errEl.hidden = true;
    const btn = form.querySelector('button');
    btn.disabled = true;
    try {
      await api('/api/auth/login', { method: 'POST', body: formData(form) });
      location.href = safeNext;
    } catch (err) {
      errEl.textContent = err.message;
      errEl.hidden = false;
      btn.disabled = false;
    }
  });
})();
