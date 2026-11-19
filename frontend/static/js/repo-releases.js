/* Releases: list, one release, and the new/edit form with asset uploads. */

const relApi = (suffix = '') => `/api/v1/repos/${enc(Repo.info.owner)}/${enc(Repo.info.name)}${suffix}`;
const releaseUrl = (tag) => `${repoBase()}/releases/tag/${encPath(tag)}`;

function uploadWithProgress(url, file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', url);
    xhr.setRequestHeader('X-Requested-With', 'mygit');
    xhr.setRequestHeader('Content-Type', file.type || 'application/octet-stream');
    xhr.upload.onprogress = (e) => { if (e.lengthComputable) onProgress(e.loaded / e.total); };
    xhr.onload = () => {
      let data = null;
      try { data = JSON.parse(xhr.responseText); } catch { /* not JSON */ }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data);
      else reject(new Error((data && data.error) || `Upload failed (${xhr.status})`));
    };
    xhr.onerror = () => reject(new Error('Upload failed: network error'));
    xhr.send(file);
  });
}

function assetList(r, { editable = false, sources = true } = {}) {
  const archives = sources ? [
    { name: 'Source code (zip)', url: r.zipball_url },
    { name: 'Source code (tar.gz)', url: r.tarball_url },
  ] : [];
  const rows = r.assets.map((a) => `<li class="row wrap asset" data-asset="${a.id}">${icon('package')}
      <a class="grow truncate" href="${esc(a.browser_download_url)}"><strong>${esc(a.name)}</strong></a>
      <span class="small muted nowrap">${formatBytes(a.size)}</span>
      <span class="small faint nowrap" title="Downloads">${icon('download')} ${a.download_count}</span>
      <button class="btn sm ghost icon" data-copysha="${esc(a.digest)}" title="Copy ${esc(a.digest)}">${icon('shield')}</button>
      ${editable ? `<button class="btn sm danger icon" data-delasset="${a.id}" title="Delete asset">${icon('trash')}</button>` : ''}</li>`);
  return `<ul class="list assets">${rows.join('')}${archives.map((x) => `<li class="row asset">${icon('archive')}<a class="grow" href="${esc(x.url)}">${x.name}</a></li>`).join('')}</ul>`;
}

function releaseCard(r, latestTag, { full = false } = {}) {
  const badges = [
    r.tag_name === latestTag ? '<span class="badge success">Latest</span>' : '',
    r.prerelease ? '<span class="badge warning">Pre-release</span>' : '',
    r.draft ? '<span class="badge">Draft</span>' : '',
  ].join(' ');
  return `<article class="card release">
    <div class="release-side">
      <div class="small muted">${r.published_at ? timeTag(r.published_at) : 'Not published'}</div>
      <div class="row small">${icon('tag')}<a href="${repoBase()}/tree/${encPath(r.tag_name)}"><code>${esc(r.tag_name)}</code></a></div>
      ${r.author.login ? `<div class="row small muted">${avatar(r.author.login)}${esc(r.author.login)}</div>` : ''}
    </div>
    <div class="release-main">
      <div class="row wrap" style="margin-bottom:8px"><h2 style="margin:0"><a href="${releaseUrl(r.tag_name)}" style="color:inherit">${esc(r.name)}</a></h2>${badges}
        <div class="spacer"></div>
        ${canWrite() ? `<a class="btn sm" href="${repoBase()}/releases/edit/${encPath(r.tag_name)}">${icon('edit')}Edit</a>` : ''}</div>
      ${r.body_html ? `<div class="markdown-body">${r.body_html}</div>` : (r.body ? '' : '<p class="muted small">No release notes.</p>')}
      <details class="assets-box" ${full || r.assets.length <= 6 ? 'open' : ''}><summary><strong>Assets</strong> <span class="badge">${r.assets.length + 2}</span></summary>${assetList(r)}</details>
    </div>
  </article>`;
}

function wireAssetButtons(el, after) {
  el.addEventListener('click', async (e) => {
    const sha = e.target.closest('[data-copysha]');
    if (sha) { copyText(sha.dataset.copysha, 'SHA-256 copied'); return; }
    const del = e.target.closest('[data-delasset]');
    if (!del) return;
    e.preventDefault();
    if (!await confirmDialog('Delete this asset?', 'Download links to it stop working.', { confirm: 'Delete', danger: true })) return;
    try {
      await api(relApi(`/releases/assets/${del.dataset.delasset}`), { method: 'DELETE' });
      snackbar('Asset deleted');
      after();
    } catch (err) { snackbar(err.message, 'error'); }
  });
}

async function releaseList(el) {
  const page = Number(new URLSearchParams(location.search).get('page') || 1);
  const [list, latest] = await Promise.all([
    api(relApi(`/releases?per_page=10&page=${page}&html=1`)),
    api(relApi('/releases/latest')).catch(() => null),
  ]);
  document.title = `Releases · ${Repo.info.full_name} · mygit`;
  el.innerHTML = `<div class="page-head"><h2 style="margin:0">Releases</h2><div class="spacer"></div>
      ${canWrite() && !Repo.info.empty ? `<a class="btn primary sm" href="${repoBase()}/releases/new">${icon('plus')}New release</a>` : ''}</div>
    ${list.length ? list.map((r) => releaseCard(r, latest && latest.tag_name)).join('') : `<div class="card empty">${icon('package')}<p>No releases yet.</p>
      <p class="small muted">Publish one here, or from a release script: <code>mygit release create ${esc(Repo.info.full_name)} v1.0.0 dist/*</code></p></div>`}
    ${page > 1 || list.length === 10 ? `<div class="row" style="justify-content:center;margin-top:16px">
      <a class="btn sm ${page > 1 ? '' : 'disabled'}" href="?page=${page - 1}">Newer</a><a class="btn sm ${list.length === 10 ? '' : 'disabled'}" href="?page=${page + 1}">Older</a></div>` : ''}
    <div class="card card-pad small muted" style="margin-top:16px">${icon('info')} Installers can fetch the newest file from <code>${esc(location.origin)}${repoBase()}/releases/latest/download/&lt;file name&gt;</code>
      or read <code>${esc(location.origin)}/api/v1/repos/${esc(Repo.info.full_name)}/releases/latest</code> (same JSON as GitHub's API).</div>`;
  wireAssetButtons(el, () => releaseList(el));
}

async function releaseOne(el, tag) {
  const [r, latest] = await Promise.all([api(relApi(`/releases/tags/${encPath(tag)}?html=1`)), api(relApi('/releases/latest')).catch(() => null)]);
  document.title = `${r.name} · ${Repo.info.full_name} · mygit`;
  el.innerHTML = `<div class="toolbar"><a href="${repoBase()}/releases">${icon('arrowLeft')} All releases</a></div>${releaseCard(r, latest && latest.tag_name, { full: true })}`;
  wireAssetButtons(el, () => releaseOne(el, tag));
}

async function releaseForm(el, tag) {
  if (!canWrite()) { showError(el, { status: 404 }); return; }
  const editing = Boolean(tag);
  const r = editing ? await api(relApi(`/releases/tags/${encPath(tag)}`)) : null;
  const refs = await api(repoApi('/refs'));
  document.title = `${editing ? 'Edit release' : 'New release'} · ${Repo.info.full_name} · mygit`;
  const existingTags = new Set(refs.tags.map((t) => t.name));
  el.innerHTML = `<div class="page-head"><h1>${editing ? `Edit ${esc(r.name)}` : 'New release'}</h1></div>
    <form class="card card-pad" id="rel-form" style="max-width:880px">
      <div class="row wrap" style="gap:12px;align-items:flex-start">
        <label class="field grow" style="min-width:200px"><span>Tag</span>
          <input type="text" name="tag_name" required list="tag-list" value="${esc(r ? r.tag_name : '')}" placeholder="v1.0.0" autocapitalize="none" spellcheck="false">
          <datalist id="tag-list">${refs.tags.map((t) => `<option value="${esc(t.name)}">`).join('')}</datalist>
          <small id="tag-hint">Pick an existing tag or type a new one.</small></label>
        <label class="field" style="min-width:200px" id="target-field"><span>Create the tag on</span>
          <select name="target_commitish">${refs.branches.map((b) => `<option ${b.name === (r ? r.target_commitish : Repo.info.default_branch) ? 'selected' : ''}>${esc(b.name)}</option>`).join('')}</select></label>
      </div>
      <label class="field"><span>Title</span><input type="text" name="name" value="${esc(r ? r.name : '')}" maxlength="200" placeholder="Defaults to the tag"></label>
      <label class="field"><span>Release notes</span><textarea name="body" rows="10" placeholder="Markdown is supported">${esc(r ? r.body : '')}</textarea></label>
      <div class="field"><span style="font-weight:600;display:block;margin-bottom:4px">Assets</span>
        <div class="dropzone" id="dropzone" tabindex="0" role="button">${icon('upload')} Drop files here or <u>choose files</u><input type="file" id="files" multiple hidden></div>
        <ul class="list upload-list" id="upload-list"></ul>
        ${r && r.assets.length ? `<div class="small muted" style="margin-top:8px">Already attached:</div>${assetList(r, { editable: true, sources: false })}` : ''}
      </div>
      <label class="check"><input type="checkbox" name="prerelease" ${r && r.prerelease ? 'checked' : ''}><span>Pre-release<small>Not shown as Latest, and update checks that ask for the latest release skip it.</small></span></label>
      <label class="check"><input type="checkbox" name="make_latest" ${!r || r.make_latest ? 'checked' : ''}><span>Can be the latest release<small>Untick for side builds (e.g. a Windows-only release next to the main one).</small></span></label>
      <div class="form-error" hidden></div>
      <div class="form-actions">
        <button class="btn primary" type="submit" data-publish="1">${editing && !r.draft ? 'Update release' : 'Publish release'}</button>
        ${!editing || r.draft ? '<button class="btn" type="submit" data-publish="0">Save draft</button>' : ''}
        <div class="spacer" style="flex:1"></div>
        ${editing ? `<button class="btn danger" type="button" id="del-rel">${icon('trash')}Delete release</button>` : ''}
      </div>
    </form>`;
  const form = $('#rel-form', el);
  const pending = [];
  const list = $('#upload-list', el);
  const tagInput = form.tag_name;
  const syncTag = () => {
    const exists = existingTags.has(tagInput.value.trim());
    $('#target-field', el).hidden = exists;
    $('#tag-hint', el).textContent = exists ? 'Existing tag: the release points at it.' : 'New tag: it is created when you publish.';
  };
  tagInput.addEventListener('input', syncTag);
  syncTag();
  const addFiles = (files) => {
    for (const f of files) {
      if (pending.some((p) => p.file.name === f.name) || (r && r.assets.some((a) => a.name === f.name))) {
        snackbar(`${f.name} is already in the list`, 'error');
        continue;
      }
      const li = document.createElement('li');
      li.className = 'row';
      li.innerHTML = `${icon('file')}<span class="grow truncate">${esc(f.name)}</span><span class="small muted">${formatBytes(f.size)}</span><progress max="1" value="0" hidden></progress><button type="button" class="btn sm ghost icon" title="Remove">${icon('x')}</button>`;
      const entry = { file: f, li };
      li.querySelector('button').addEventListener('click', () => { pending.splice(pending.indexOf(entry), 1); li.remove(); });
      pending.push(entry);
      list.appendChild(li);
    }
  };
  const drop = $('#dropzone', el);
  const picker = $('#files', el);
  drop.addEventListener('click', () => picker.click());
  drop.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); picker.click(); } });
  picker.addEventListener('change', () => { addFiles(picker.files); picker.value = ''; });
  drop.addEventListener('dragover', (e) => { e.preventDefault(); drop.classList.add('over'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('over'));
  drop.addEventListener('drop', (e) => { e.preventDefault(); drop.classList.remove('over'); addFiles(e.dataTransfer.files); });
  if (r) wireAssetButtons(el, () => releaseForm(el, tag));

  let submitter = null;
  form.addEventListener('click', (e) => { const b = e.target.closest('button[type=submit]'); if (b) submitter = b; });
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const publish = (e.submitter || submitter || {}).dataset.publish !== '0';
    const errEl = form.querySelector('.form-error');
    errEl.hidden = true;
    const d = formData(form);
    const fields = { tag_name: d.tag_name.trim(), name: d.name.trim(), body: d.body, prerelease: d.prerelease, make_latest: d.make_latest };
    if (!existingTags.has(fields.tag_name)) fields.target_commitish = d.target_commitish;
    $$('button', form).forEach((b) => { b.disabled = true; });
    try {
      // Upload into a draft, publish last: nobody downloads a half-uploaded release.
      let rel = editing ? await api(relApi(`/releases/${r.id}`), { method: 'PATCH', body: fields })
        : await api(relApi('/releases'), { method: 'POST', body: { ...fields, draft: true } });
      for (const p of pending) {
        const bar = p.li.querySelector('progress');
        bar.hidden = false;
        await uploadWithProgress(relApi(`/releases/${rel.id}/assets?name=${enc(p.file.name)}`), p.file, (v) => { bar.value = v; });
        bar.value = 1;
      }
      if (publish && rel.draft) rel = await api(relApi(`/releases/${rel.id}`), { method: 'PATCH', body: { draft: false } });
      location.href = releaseUrl(rel.tag_name);
    } catch (err) {
      errEl.textContent = err.message;
      errEl.hidden = false;
      $$('button', form).forEach((b) => { b.disabled = false; });
    }
  });
  const del = $('#del-rel', el);
  if (del) {
    del.addEventListener('click', async () => {
      if (!await confirmDialog(`Delete ${r.name}?`, 'The release and its assets are removed. The git tag stays.', { confirm: 'Delete release', danger: true })) return;
      await api(relApi(`/releases/${r.id}`), { method: 'DELETE' });
      location.href = `${repoBase()}/releases`;
    });
  }
}

RepoViews.releases = {
  tab: 'releases',
  async render(el) {
    const [, sub, ...rest] = Repo.rest;
    if (sub === 'new') return releaseForm(el, null);
    if (sub === 'edit') return releaseForm(el, rest.join('/'));
    if (sub === 'tag') return releaseOne(el, rest.join('/'));
    return releaseList(el);
  },
};
