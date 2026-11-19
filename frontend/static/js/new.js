(async function () {
  await renderShell();
  const me = await requireLogin();
  const main = $('#main');
  main.className = 'page narrow';
  let owners = [me.username];
  if (me.is_admin) {
    try {
      const users = await api('/api/admin/users');
      owners = [me.username, ...users.map((u) => u.username).filter((n) => n !== me.username)];
    } catch { /* fall back to yourself */ }
  }
  const preset = new URLSearchParams(location.search);
  main.innerHTML = `<div class="page-head"><h1>Create a repository</h1></div>
    <form class="card card-pad" id="new-repo">
      <div class="row wrap" style="align-items:flex-end;gap:8px">
        <label class="field" style="margin:0;min-width:160px"><span>Owner</span>
          <select name="owner" ${owners.length > 1 ? '' : 'disabled'}>${owners.map((o) => `<option>${esc(o)}</option>`).join('')}</select></label>
        <span style="font-size:20px;padding-bottom:6px" class="faint">/</span>
        <label class="field grow" style="margin:0"><span>Repository name</span>
          <input type="text" name="name" required maxlength="100" pattern="[A-Za-z0-9._\\-]+" autocapitalize="none" spellcheck="false" value="${esc(preset.get('name') || '')}" autofocus></label>
      </div>
      <p class="small muted" style="margin:6px 0 16px">Letters, digits, <code>.</code> <code>-</code> and <code>_</code>. Short and memorable, like <code>ispend</code>.</p>
      <label class="field"><span>Description <span class="faint">(optional)</span></span><input type="text" name="description" maxlength="500"></label>
      <fieldset style="border:0;padding:0;margin:0 0 14px">
        <legend style="font-weight:600;margin-bottom:6px">Visibility</legend>
        <label class="radio-card"><input type="radio" name="visibility" value="public" checked><span>${icon('globe')} <strong>Public</strong><small class="muted" style="display:block">Anyone can clone it and download raw files and releases, no sign-in needed. Right for apps installed with <code>curl … | bash</code>.</small></span></label>
        <label class="radio-card"><input type="radio" name="visibility" value="private"><span>${icon('lock')} <strong>Private</strong><small class="muted" style="display:block">Only you, collaborators and deploy tokens can see it.</small></span></label>
      </fieldset>
      <label class="field"><span>Default branch</span><input type="text" name="default_branch" value="main" required style="max-width:240px"></label>
      <div class="form-error" hidden></div>
      <div class="form-actions"><button class="btn primary" type="submit">Create repository</button></div>
    </form>`;
  const form = $('#new-repo');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const d = formData(form);
    const errEl = form.querySelector('.form-error');
    errEl.hidden = true;
    try {
      const repo = await api('/api/repos', {
        method: 'POST',
        body: { owner: d.owner || me.username, name: d.name.trim(), description: d.description, private: d.visibility === 'private', default_branch: d.default_branch.trim() },
      });
      location.href = repoHref(repo.owner, repo.name);
    } catch (err) {
      errEl.textContent = err.message;
      errEl.hidden = false;
    }
  });
})();
