/* Account settings. Each section renders into the right column; the path
   after /settings picks it (/settings/tokens, /settings/keys ...). */
const SettingsSections = [];

SettingsSections.push({
  key: '', label: 'Profile', icon: 'user',
  async render(el, me) {
    el.innerHTML = `<form class="card card-pad" id="profile-form">
      <h2>Profile</h2>
      <label class="field"><span>Username</span><input type="text" value="${esc(me.username)}" disabled><small>Only a site admin can rename an account.</small></label>
      <label class="field"><span>Name</span><input type="text" name="full_name" value="${esc(me.full_name)}" maxlength="200"></label>
      <label class="field"><span>Email</span><input type="email" name="email" value="${esc(me.email)}" maxlength="254"><small>Used as the default author of commits made on the website.</small></label>
      <div class="form-actions"><button class="btn primary" type="submit">Save</button></div>
    </form>`;
    $('#profile-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      try {
        await api('/api/auth/me', { method: 'PATCH', body: formData(e.target) });
        snackbar('Profile saved');
      } catch (err) { snackbar(err.message, 'error'); }
    });
  },
});

SettingsSections.push({
  key: 'password', label: 'Password', icon: 'lock',
  async render(el) {
    el.innerHTML = `<form class="card card-pad" id="pw-form">
      <h2>Change password</h2>
      <label class="field"><span>Current password</span><input type="password" name="current" autocomplete="current-password" required></label>
      <label class="field"><span>New password</span><input type="password" name="new" autocomplete="new-password" minlength="8" required><small>At least 8 characters. Git uses access tokens, not this password.</small></label>
      <label class="field"><span>Repeat new password</span><input type="password" name="again" autocomplete="new-password" required></label>
      <div class="form-actions"><button class="btn primary" type="submit">Change password</button></div>
    </form>`;
    $('#pw-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const d = formData(e.target);
      if (d.new !== d.again) { snackbar('The new passwords differ', 'error'); return; }
      try {
        await api('/api/auth/me/password', { method: 'POST', body: { current: d.current, new: d.new } });
        e.target.reset();
        snackbar('Password changed');
      } catch (err) { snackbar(err.message, 'error'); }
    });
  },
});

(async function () {
  await renderShell('settings');
  const me = await requireLogin();
  // Later scripts (tokens, keys) register sections before this runs.
  await new Promise((r) => setTimeout(r, 0));
  const key = location.pathname.replace(/^\/settings\/?/, '').replace(/\/$/, '');
  const section = SettingsSections.find((s) => s.key === key) || SettingsSections[0];
  document.title = `${section.label} · Settings · mygit`;
  const main = $('#main');
  main.innerHTML = `<div class="page-head">${avatar(me.username)}<h1>${esc(me.username)}</h1><span class="muted">Account settings</span></div>
    <div class="split">
      <nav class="sidenav">${SettingsSections.map((s) => `<a href="/settings${s.key ? '/' + s.key : ''}" class="${s === section ? 'active' : ''}">${icon(s.icon)}${esc(s.label)}</a>`).join('')}</nav>
      <section id="section"></section>
    </div>`;
  try {
    await section.render($('#section'), me);
  } catch (err) { showError($('#section'), err); }
})();
