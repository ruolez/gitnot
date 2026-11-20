/* Site admin: users, and later site settings. */
const AdminSections = [];

function userDialog(user) {
  const editing = Boolean(user);
  const u = user || { username: '', full_name: '', email: '', is_admin: false, is_active: true };
  return openDialog({
    title: editing ? `Edit ${u.username}` : 'New user',
    body: `
      <label class="field"><span>Username</span><input type="text" name="username" value="${esc(u.username)}" required autocapitalize="none" spellcheck="false">${editing ? '<small>Renaming changes the URLs of this user\'s repositories. The old URLs keep working.</small>' : ''}</label>
      <label class="field"><span>Name</span><input type="text" name="full_name" value="${esc(u.full_name)}"></label>
      <label class="field"><span>Email</span><input type="email" name="email" value="${esc(u.email)}"></label>
      <label class="field"><span>${editing ? 'New password' : 'Password'}</span><input type="password" name="password" autocomplete="new-password" ${editing ? 'placeholder="Leave empty to keep"' : 'required minlength="8"'}></label>
      <label class="check"><input type="checkbox" name="is_admin" ${u.is_admin ? 'checked' : ''}><span>Site admin<small>Can manage users, settings and every repository.</small></span></label>
      ${editing ? `<label class="check"><input type="checkbox" name="is_active" ${u.is_active ? 'checked' : ''}><span>Active<small>Inactive users can't sign in, push or use their tokens.</small></span></label>` : ''}`,
    buttons: [{ label: 'Cancel' }, { label: editing ? 'Save' : 'Create user', cls: 'primary', submit: true }],
    async onSubmit(form) {
      const d = formData(form);
      if (editing && !d.password) delete d.password;
      if (editing) return api(`/api/admin/users/${u.id}`, { method: 'PATCH', body: d });
      return api('/api/admin/users', { method: 'POST', body: d });
    },
  });
}

AdminSections.push({
  key: '', label: 'Users', icon: 'users',
  async render(el, me) {
    const users = await api('/api/admin/users');
    el.innerHTML = `<div class="card">
      <div class="card-head"><h2>Users</h2><span class="badge">${users.length}</span><div class="grow"></div><button class="btn primary sm" id="new-user">${icon('plus')}New user</button></div>
      <div class="table-wrap"><table class="table">
        <thead><tr><th>User</th><th>Email</th><th>Role</th><th>Last sign-in</th><th></th></tr></thead>
        <tbody>${users.map((u) => `<tr data-id="${u.id}">
          <td><div class="row">${avatar(u.username)}<div><a href="/${encodeURIComponent(u.username)}"><strong>${esc(u.username)}</strong></a><div class="small muted">${esc(u.full_name)}</div></div></div></td>
          <td class="muted">${esc(u.email)}</td>
          <td>${u.is_admin ? '<span class="badge accent">Admin</span>' : '<span class="badge">User</span>'} ${u.is_active ? '' : '<span class="badge danger">Inactive</span>'}</td>
          <td class="muted small">${u.last_login_at ? timeTag(u.last_login_at) : 'Never'}</td>
          <td class="actions"><button class="btn sm" data-act="edit">${icon('edit')}Edit</button>
            ${u.id === me.id ? '' : `<button class="btn sm danger" data-act="delete">${icon('trash')}</button>`}</td>
        </tr>`).join('')}</tbody>
      </table></div></div>`;
    const rerender = () => this.render(el, me);
    $('#new-user').addEventListener('click', async () => { if (await userDialog()) { snackbar('User created'); rerender(); } });
    el.querySelector('tbody').addEventListener('click', async (e) => {
      const btn = e.target.closest('button[data-act]');
      if (!btn) return;
      const user = users.find((u) => u.id === Number(btn.closest('tr').dataset.id));
      if (btn.dataset.act === 'edit') {
        if (await userDialog(user)) { snackbar('User saved'); rerender(); }
        return;
      }
      const ok = await confirmDialog(`Delete ${user.username}?`, 'This removes the account, its tokens and SSH keys. Users who still own repositories can\'t be deleted; transfer or delete those first.', { confirm: 'Delete user', danger: true, typeToConfirm: user.username });
      if (!ok) return;
      try {
        await api(`/api/admin/users/${user.id}`, { method: 'DELETE' });
        snackbar('User deleted');
        rerender();
      } catch (err) { snackbar(err.message, 'error'); }
    });
  },
});

AdminSections.push({
  key: 'settings', label: 'Settings', icon: 'gear',
  async render(el) {
    const s = await api('/api/admin/settings');
    el.innerHTML = `<form class="card card-pad" id="site-settings">
      <h2>Limits</h2>
      <label class="field"><span>Largest file in a push (MB)</span><input type="number" name="max_file_mb" min="0" max="10240" value="${s.max_file_mb}" style="max-width:160px">
        <small>Pushes with a bigger file are refused with its name. 0 = no limit. Big binaries belong in releases.</small></label>
      <label class="field"><span>Largest release file (MB)</span><input type="number" name="max_asset_mb" min="1" max="102400" value="${s.max_asset_mb}" style="max-width:160px">
        <small>Also capped by the server's MAX_UPLOAD setting.</small></label>
      <h2 style="margin-top:20px">Imports and mirrors</h2>
      <label class="check"><input type="checkbox" name="allow_internal_remotes" ${s.allow_internal_remotes ? 'checked' : ''}><span>Allow servers on the local network (and plain http)
        <small>Off: imports and push mirrors only reach public https servers, so nobody can point them at this server's own internals. Turn on only to import from a git server on your LAN.</small></span></label>
      <div class="form-actions"><button class="btn primary" type="submit">Save</button></div>
    </form>`;
    $('#site-settings', el).addEventListener('submit', async (e) => {
      e.preventDefault();
      const d = formData(e.target);
      try {
        await api('/api/admin/settings', { method: 'PATCH', body: { max_file_mb: Number(d.max_file_mb), max_asset_mb: Number(d.max_asset_mb), allow_internal_remotes: d.allow_internal_remotes } });
        snackbar('Settings saved');
      } catch (err) { snackbar(err.message, 'error'); }
    });
  },
});

(async function () {
  await renderShell('admin');
  const me = await requireLogin();
  const main = $('#main');
  if (!me.is_admin) { showError(main, { status: 404 }); return; }
  await new Promise((r) => setTimeout(r, 0));
  const key = location.pathname.replace(/^\/-\/admin\/?/, '').replace(/\/$/, '');
  const section = AdminSections.find((s) => s.key === key) || AdminSections[0];
  document.title = `${section.label} · Site admin · git-Not`;
  main.innerHTML = `<div class="page-head"><h1>Site admin</h1></div>
    <div class="split">
      <nav class="sidenav">${AdminSections.map((s) => `<a href="/-/admin${s.key ? '/' + s.key : ''}" class="${s === section ? 'active' : ''}">${icon(s.icon)}${esc(s.label)}</a>`).join('')}</nav>
      <section id="section"></section>
    </div>`;
  try {
    await section.render($('#section'), me);
  } catch (err) { showError($('#section'), err); }
})();
