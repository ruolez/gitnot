/* Repository settings (repo admins only). */

function settingsUrl() { return `${repoBase()}/settings`; }

async function sectionGeneral(el, info, branches) {
  el.innerHTML = `<form class="card card-pad" id="general">
    <h2>General</h2>
    <label class="field"><span>Repository name</span><input type="text" name="name" value="${esc(info.name)}" required maxlength="100">
      <small>Renaming keeps the old web, clone and raw URLs working, so installers don't break.</small></label>
    <label class="field"><span>Description</span><input type="text" name="description" value="${esc(info.description)}" maxlength="500"></label>
    <label class="field"><span>Default branch</span>
      ${branches.length ? `<select name="default_branch">${branches.map((b) => `<option ${b === info.default_branch ? 'selected' : ''}>${esc(b)}</option>`).join('')}</select>`
        : `<input type="text" name="default_branch" value="${esc(info.default_branch)}">`}
      <small>What people get when they clone, and what raw URLs without a branch use.</small></label>
    <fieldset style="border:0;padding:0;margin:0 0 14px">
      <legend style="font-weight:600;margin-bottom:6px">Visibility</legend>
      <label class="radio-card"><input type="radio" name="visibility" value="public" ${info.private ? '' : 'checked'}><span>${icon('globe')} <strong>Public</strong><small class="muted" style="display:block">Anyone can read, clone and download without signing in.</small></span></label>
      <label class="radio-card"><input type="radio" name="visibility" value="private" ${info.private ? 'checked' : ''}><span>${icon('lock')} <strong>Private</strong><small class="muted" style="display:block">Only you, collaborators and deploy tokens. Installers need a deploy token.</small></span></label>
    </fieldset>
    <div class="form-actions"><button class="btn primary" type="submit">Save changes</button></div>
  </form>`;
  $('#general', el).addEventListener('submit', async (e) => {
    e.preventDefault();
    const d = formData(e.target);
    try {
      const updated = await api(repoApi(''), {
        method: 'PATCH',
        body: { name: d.name.trim(), description: d.description, default_branch: d.default_branch, private: d.visibility === 'private' },
      });
      snackbar('Settings saved');
      if (updated.name !== info.name) location.href = `${repoHref(updated.owner, updated.name)}/settings`;
      else Object.assign(Repo.info, updated);
    } catch (err) { snackbar(err.message, 'error'); }
  });
}

async function sectionCollaborators(el) {
  const people = await api(repoApi('/collaborators'));
  const roleSelect = (name, role) => `<select data-role="${esc(name)}" aria-label="Role for ${esc(name)}">${['read', 'write', 'admin'].map((r) => `<option value="${r}" ${r === role ? 'selected' : ''}>${{ read: 'Read', write: 'Write', admin: 'Admin' }[r]}</option>`).join('')}</select>`;
  el.innerHTML = `<div class="card">
    <div class="card-head"><h2>Collaborators</h2><div class="grow"></div><button class="btn primary sm" id="add-collab">${icon('plus')}Add people</button></div>
    <div class="card-pad" style="padding-bottom:0"><p class="muted small"><strong>Read</strong> clone and download · <strong>Write</strong> also push and publish releases · <strong>Admin</strong> also change settings.</p></div>
    ${people.length ? `<ul class="list">${people.map((p) => `<li class="row wrap">${avatar(p.username)}<div class="grow"><strong>${esc(p.username)}</strong> <span class="muted small">${esc(p.full_name)}</span></div>
      <div style="width:120px">${roleSelect(p.username, p.role)}</div><button class="btn sm danger icon" data-remove="${esc(p.username)}" title="Remove">${icon('trash')}</button></li>`).join('')}</ul>`
      : '<div class="empty small">Only the owner has access.</div>'}
  </div>`;
  const rerender = () => sectionCollaborators(el);
  $('#add-collab', el).addEventListener('click', async () => {
    const added = await openDialog({
      title: 'Add a collaborator',
      body: `<label class="field"><span>Username</span><input type="text" name="username" required autocapitalize="none"></label>
        <label class="field"><span>Role</span><select name="role"><option value="read">Read</option><option value="write" selected>Write</option><option value="admin">Admin</option></select></label>`,
      buttons: [{ label: 'Cancel' }, { label: 'Add', cls: 'primary', submit: true }],
      onSubmit: (form) => api(repoApi(`/collaborators/${enc(form.username.value.trim())}`), { method: 'PUT', body: { role: form.role.value } }),
    });
    if (added) { snackbar(`${added.username} added`); rerender(); }
  });
  el.onchange = async (e) => {
    const s = e.target.closest('[data-role]');
    if (!s) return;
    try {
      await api(repoApi(`/collaborators/${enc(s.dataset.role)}`), { method: 'PUT', body: { role: s.value } });
      snackbar('Role changed');
    } catch (err) { snackbar(err.message, 'error'); }
  };
  el.onclick = async (e) => {
    const b = e.target.closest('[data-remove]');
    if (!b) return;
    if (!await confirmDialog(`Remove ${b.dataset.remove}?`, 'They lose access to this repository at once.', { confirm: 'Remove', danger: true })) return;
    try {
      await api(repoApi(`/collaborators/${enc(b.dataset.remove)}`), { method: 'DELETE' });
      rerender();
    } catch (err) { snackbar(err.message, 'error'); }
  };
}

async function sectionProtection(el) {
  const rules = await api(repoApi('/protection'));
  const describe = (r) => [
    r.min_push_role === 'admin' ? 'only admins push' : 'writers push',
    r.allow_force_push ? 'force pushes allowed' : (r.kind === 'tag' ? 'cannot be moved' : 'no force pushes'),
    r.allow_delete ? 'can be deleted' : 'cannot be deleted',
  ].join(' · ');
  el.innerHTML = `<div class="card">
    <div class="card-head"><h2>Protected branches and tags</h2><div class="grow"></div><button class="btn primary sm" id="add-rule">${icon('plus')}Add rule</button></div>
    <div class="card-pad" style="padding-bottom:0"><p class="muted small">Stops history from being rewritten or deleted. Patterns use <code>*</code>, e.g. <code>release/*</code> or <code>v*</code>. The default branch can never be deleted.</p></div>
    ${rules.length ? `<ul class="list">${rules.map((r) => `<li class="row wrap">${icon(r.kind === 'tag' ? 'tag' : 'shield')}<div class="grow"><code>${esc(r.pattern)}</code> <span class="badge">${r.kind}</span><div class="small muted">${describe(r)}</div></div>
      <button class="btn sm danger icon" data-rule="${r.id}" title="Remove rule">${icon('trash')}</button></li>`).join('')}</ul>`
      : '<div class="empty small">No rules yet. Protecting the default branch is a good start.</div>'}
  </div>`;
  const rerender = () => sectionProtection(el);
  $('#add-rule', el).addEventListener('click', async () => {
    const added = await openDialog({
      title: 'Protect branches or tags',
      body: `<label class="field"><span>Applies to</span><select name="kind"><option value="branch">Branches</option><option value="tag">Tags</option></select></label>
        <label class="field"><span>Name or pattern</span><input type="text" name="pattern" required value="${esc(Repo.info.default_branch)}"></label>
        <label class="field"><span>Who can push</span><select name="min_push_role"><option value="write">Anyone with write access</option><option value="admin">Repository admins only</option></select></label>
        <label class="check"><input type="checkbox" name="allow_force_push"><span>Allow force pushes<small>Rewriting history (or moving tags).</small></span></label>
        <label class="check"><input type="checkbox" name="allow_delete"><span>Allow deletion</span></label>`,
      buttons: [{ label: 'Cancel' }, { label: 'Add rule', cls: 'primary', submit: true }],
      onSubmit: (form) => api(repoApi('/protection'), { method: 'POST', body: formData(form) }),
    });
    if (added) { snackbar('Rule added'); rerender(); }
  });
  el.onclick = async (e) => {
    const b = e.target.closest('[data-rule]');
    if (!b) return;
    try {
      await api(repoApi(`/protection/${b.dataset.rule}`), { method: 'DELETE' });
      rerender();
    } catch (err) { snackbar(err.message, 'error'); }
  };
}

async function sectionDeployTokens(el) {
  const tokens = await api(repoApi('/deploy-tokens'));
  const urls = Repo.info.clone_urls;
  el.innerHTML = `<div class="card">
    <div class="card-head"><h2>Deploy tokens</h2><div class="grow"></div><button class="btn primary sm" id="add-deploy">${icon('plus')}New deploy token</button></div>
    <div class="card-pad" style="padding-bottom:0"><p class="muted small">For servers and installers. A deploy token works only on this repository and belongs to no person, so it keeps working when people leave.</p></div>
    <div id="deploy-secret"></div>
    ${tokens.length ? `<ul class="list">${tokens.map((t) => `<li class="row wrap">${icon('token')}<div class="grow"><strong>${esc(t.name)}</strong> <span class="badge ${t.access === 'write' ? 'accent' : ''}">${t.access === 'write' ? 'Read + write' : 'Read only'}</span>
      <div class="small muted"><code>${esc(t.prefix)}…</code> · ${t.last_used_at ? `last used ${timeTag(t.last_used_at)}` : 'never used'} · ${t.expires_at ? `expires ${esc(new Date(t.expires_at).toLocaleDateString())}` : 'no expiry'}</div></div>
      <button class="btn sm danger" data-token="${t.id}">${icon('trash')}Revoke</button></li>`).join('')}</ul>` : '<div class="empty small">No deploy tokens.</div>'}
  </div>`;
  const rerender = () => sectionDeployTokens(el);
  $('#add-deploy', el).addEventListener('click', async () => {
    const created = await openDialog({
      title: 'New deploy token',
      body: `<label class="field"><span>Name</span><input type="text" name="name" required placeholder="e.g. office-server installer"></label>
        <label class="field"><span>Access</span><select name="access"><option value="read">Read only (clone, raw files, releases)</option><option value="write">Read + write (push, publish releases)</option></select></label>
        <label class="field"><span>Expires</span><select name="expires_days"><option value="never">Never</option><option value="90">In 90 days</option><option value="365">In a year</option></select></label>`,
      buttons: [{ label: 'Cancel' }, { label: 'Create', cls: 'primary', submit: true }],
      onSubmit: (form) => api(repoApi('/deploy-tokens'), { method: 'POST', body: formData(form) }),
    });
    if (!created) return;
    await rerender();
    const t = created.token;
    const httpsUrl = urls.https.replace('://', `://deploy:${t}@`);
    $('#deploy-secret', el).innerHTML = `<div class="card-pad"><div class="notice success"><strong>Copy the token now.</strong> It is shown only once.
      <div class="secret" style="margin-top:8px"><code>${esc(t)}</code><button class="btn sm" data-copytext="${esc(t)}">${icon('copy')}Copy</button></div>
      <p class="small" style="margin:10px 0 4px">Clone or update:</p><pre class="code">git clone ${esc(httpsUrl)}</pre>
      <p class="small" style="margin:10px 0 4px">Raw file:</p><pre class="code">curl -fsSL -u deploy:${esc(t)} ${esc(location.origin)}/raw/${esc(Repo.info.full_name)}/${esc(Repo.info.default_branch)}/install.sh</pre></div></div>`;
  });
  el.onclick = async (e) => {
    const c = e.target.closest('[data-copytext]');
    if (c) { copyText(c.dataset.copytext, 'Token copied'); return; }
    const b = e.target.closest('[data-token]');
    if (!b) return;
    if (!await confirmDialog('Revoke this deploy token?', 'Servers using it will stop being able to update.', { confirm: 'Revoke', danger: true })) return;
    await api(repoApi(`/deploy-tokens/${b.dataset.token}`), { method: 'DELETE' });
    rerender();
  };
}

async function sectionMirror(el) {
  const m = await api(repoApi('/mirror'));
  const status = m && m.last_at
    ? (m.last_status === 'ok' ? `<span class="badge success">${icon('check')}Synced ${timeTag(m.last_at)}</span>`
      : `<span class="badge danger">Failed ${timeTag(m.last_at)}</span><div class="small" style="color:var(--danger);margin-top:6px;white-space:pre-wrap">${esc(m.last_error)}</div>`)
    : (m ? '<span class="badge">Not synced yet</span>' : '');
  el.innerHTML = `<form class="card" id="mirror-form">
    <div class="card-head"><h2>Push mirror</h2>${m ? (m.enabled ? '<span class="badge accent">On</span>' : '<span class="badge">Off</span>') : ''}</div>
    <div class="card-pad">
      <p class="muted small">After every push, branches and tags are pushed on to another server, for example the GitHub repository this one came from, so it stays an up-to-date backup and old installers that still pull from GitHub keep working.</p>
      <label class="field"><span>Remote URL</span><input type="text" name="url" value="${esc(m ? m.url : '')}" placeholder="https://github.com/owner/repo.git" autocapitalize="none" spellcheck="false"></label>
      <div class="row wrap" style="gap:12px;align-items:flex-start">
        <label class="field" style="min-width:160px"><span>Username</span><input type="text" name="username" value="${esc(m ? m.username : 'x-access-token')}"></label>
        <label class="field grow"><span>Token</span><input type="password" name="token" autocomplete="off" placeholder="${m && m.has_token ? 'Saved (leave empty to keep)' : 'A token that can push'}">
          <small>For GitHub: a fine-grained token with Contents: read and write on that repository.</small></label>
      </div>
      <label class="check"><input type="checkbox" name="enabled" ${!m || m.enabled ? 'checked' : ''}><span>Push after every change</span></label>
      ${status ? `<div style="margin:8px 0">${status}</div>` : ''}
      <div class="form-actions"><button class="btn primary" type="submit">Save</button>
        ${m ? `<button class="btn" type="button" id="mirror-sync">${icon('mirror')}Sync now</button><div style="flex:1"></div><button class="btn danger" type="button" id="mirror-del">Remove</button>` : ''}</div>
    </div></form>`;
  const rerender = () => sectionMirror(el);
  $('#mirror-form', el).addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      await api(repoApi('/mirror'), { method: 'PUT', body: formData(e.target) });
      snackbar('Mirror saved; syncing now');
      rerender();
    } catch (err) { snackbar(err.message, 'error'); }
  });
  const sync = $('#mirror-sync', el);
  if (sync) {
    sync.addEventListener('click', async () => {
      await api(repoApi('/mirror/sync'), { method: 'POST' });
      snackbar('Sync queued');
      setTimeout(rerender, 3000);
    });
    $('#mirror-del', el).addEventListener('click', async () => {
      if (!await confirmDialog('Remove the push mirror?', 'Nothing is deleted on the other server.', { confirm: 'Remove', danger: true })) return;
      await api(repoApi('/mirror'), { method: 'DELETE' });
      rerender();
    });
  }
}

function sectionDanger(el, info) {
  el.innerHTML = `<div class="card danger-zone">
    <div class="card-head"><h2>Danger zone</h2></div>
    <ul class="list">
      <li class="row wrap"><div class="grow"><strong>${info.archived ? 'Unarchive' : 'Archive'} this repository</strong><div class="small muted">${info.archived ? 'Allow pushes again.' : 'Make it read-only: no pushes, nothing else changes.'}</div></div>
        <button class="btn danger sm" id="archive">${info.archived ? 'Unarchive' : 'Archive'}</button></li>
      <li class="row wrap"><div class="grow"><strong>Transfer ownership</strong><div class="small muted">Move it to another user. Old URLs redirect; you stay on as an admin.</div></div>
        <button class="btn danger sm" id="transfer">Transfer</button></li>
      <li class="row wrap"><div class="grow"><strong>Delete this repository</strong><div class="small muted">Removes the code, releases and settings. Clones elsewhere are not affected.</div></div>
        <button class="btn danger sm" id="delete">Delete</button></li>
    </ul></div>`;
  $('#archive', el).addEventListener('click', async () => {
    const archiving = !info.archived;
    if (!await confirmDialog(archiving ? 'Archive repository?' : 'Unarchive repository?', archiving ? 'Pushes will be refused until you unarchive it.' : 'People with write access can push again.', { confirm: archiving ? 'Archive' : 'Unarchive', danger: archiving })) return;
    await api(repoApi(''), { method: 'PATCH', body: { archived: archiving } });
    location.reload();
  });
  $('#transfer', el).addEventListener('click', async () => {
    const moved = await openDialog({
      title: `Transfer ${info.full_name}`,
      body: `<label class="field"><span>New owner's username</span><input type="text" name="new_owner" required autocapitalize="none"></label>
        <label class="field"><span>Type <code>${esc(info.full_name)}</code> to confirm</span><input type="text" name="confirm" required autocomplete="off"></label>`,
      buttons: [{ label: 'Cancel' }, { label: 'Transfer', cls: 'danger', submit: true }],
      onSubmit: async (form) => {
        if (form.confirm.value.trim() !== info.full_name) throw new Error('The name does not match');
        return api(repoApi('/transfer'), { method: 'POST', body: { new_owner: form.new_owner.value.trim() } });
      },
    });
    if (moved) location.href = repoHref(moved.owner, moved.name);
  });
  $('#delete', el).addEventListener('click', async () => {
    if (!await confirmDialog(`Delete ${info.full_name}?`, 'This cannot be undone from the website.', { confirm: 'Delete repository', danger: true, typeToConfirm: info.full_name })) return;
    try {
      await api(repoApi(''), { method: 'DELETE' });
      location.href = '/';
    } catch (err) { snackbar(err.message, 'error'); }
  });
}

RepoViews.settings = {
  tab: 'settings',
  async render(el) {
    if (!isRepoAdmin()) { showError(el, { status: 404 }); return; }
    document.title = `Settings · ${Repo.info.full_name} · mygit`;
    const refs = Repo.info.empty ? { branches: [] } : await api(repoApi('/refs'));
    el.innerHTML = `<div class="stack" style="max-width:880px">
      <section id="s-general"></section><section id="s-collab"></section><section id="s-protect"></section>
      <section id="s-deploy"></section><section id="s-mirror"></section><section id="s-danger"></section></div>`;
    await sectionGeneral($('#s-general', el), Repo.info, refs.branches.map((b) => b.name));
    await Promise.all([sectionCollaborators($('#s-collab', el)), sectionProtection($('#s-protect', el)),
      sectionDeployTokens($('#s-deploy', el)), sectionMirror($('#s-mirror', el))]);
    sectionDanger($('#s-danger', el), Repo.info);
  },
};
