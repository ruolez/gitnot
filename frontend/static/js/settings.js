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

function tokenRow(t) {
  const expired = t.expires_at && new Date(t.expires_at) < new Date();
  return `<li class="row wrap" data-id="${t.id}">
    <div class="grow">
      <strong>${esc(t.name)}</strong> <span class="badge ${t.access === 'write' ? 'accent' : ''}">${t.access === 'write' ? 'Read + write' : 'Read only'}</span>
      ${expired ? '<span class="badge danger">Expired</span>' : ''}
      <div class="small muted"><code>${esc(t.prefix)}…</code> · created ${timeTag(t.created_at)} ·
        ${t.last_used_at ? `last used ${timeTag(t.last_used_at)}` : 'never used'} ·
        ${t.expires_at ? `${expired ? 'expired' : 'expires'} ${esc(new Date(t.expires_at).toLocaleDateString())}` : 'no expiry'}</div>
    </div>
    <button class="btn sm danger" data-act="delete">${icon('trash')}Revoke</button>
  </li>`;
}

SettingsSections.push({
  key: 'tokens', label: 'Access tokens', icon: 'token',
  async render(el, me) {
    const tokens = await api('/api/user/tokens');
    el.innerHTML = `<div class="stack">
      <div class="card">
        <div class="card-head"><h2>Personal access tokens</h2><div class="grow"></div><button class="btn primary sm" id="new-token">${icon('plus')}Generate token</button></div>
        <div class="card-pad" style="padding-bottom:0"><p class="muted">Use a token as the password when git asks (username: <code>${esc(me.username)}</code>), or in scripts as <code>Authorization: Bearer &lt;token&gt;</code>. Tokens act as you, limited to the access you give them.</p></div>
        <div id="new-secret"></div>
        ${tokens.length ? `<ul class="list" id="token-list">${tokens.map(tokenRow).join('')}</ul>` : '<div class="empty">No tokens yet.</div>'}
      </div>
    </div>`;
    const rerender = () => this.render(el, me);
    $('#new-token').addEventListener('click', async () => {
      const created = await openDialog({
        title: 'Generate a token',
        body: `<label class="field"><span>Name</span><input type="text" name="name" required maxlength="100" placeholder="e.g. MacBook, release script"></label>
          <label class="field"><span>Access</span><select name="access"><option value="write">Read + write (push, create releases)</option><option value="read">Read only (clone, download)</option></select></label>
          <label class="field"><span>Expires</span><select name="expires_days"><option value="never">Never</option><option value="30">In 30 days</option><option value="90" selected>In 90 days</option><option value="365">In a year</option></select></label>`,
        buttons: [{ label: 'Cancel' }, { label: 'Generate', cls: 'primary', submit: true }],
        onSubmit: (form) => api('/api/user/tokens', { method: 'POST', body: formData(form) }),
      });
      if (!created) return;
      await rerender();
      $('#new-secret').innerHTML = `<div class="card-pad"><div class="notice success"><strong>Copy your new token now.</strong> You won't be able to see it again.
        <div class="secret" style="margin-top:8px"><code>${esc(created.token)}</code><button class="btn sm" id="copy-token">${icon('copy')}Copy</button></div></div></div>`;
      $('#copy-token').addEventListener('click', () => copyText(created.token, 'Token copied'));
    });
    const list = $('#token-list');
    if (list) {
      list.addEventListener('click', async (e) => {
        const btn = e.target.closest('[data-act=delete]');
        if (!btn) return;
        const t = tokens.find((x) => x.id === Number(btn.closest('li').dataset.id));
        if (!await confirmDialog(`Revoke “${t.name}”?`, 'Anything still using this token stops working at once.', { confirm: 'Revoke', danger: true })) return;
        try {
          await api(`/api/user/tokens/${t.id}`, { method: 'DELETE' });
          snackbar('Token revoked');
          rerender();
        } catch (err) { snackbar(err.message, 'error'); }
      });
    }
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
