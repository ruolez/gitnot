/* Code browsing views: tree, file, commits, commit, compare, branches, tags. */

const enc = (s) => encodeURIComponent(s);
const encPath = (p) => p.split('/').map(enc).join('/');
const repoApi = (suffix) => `/api/repos/${enc(Repo.info.owner)}/${enc(Repo.info.name)}${suffix}`;

function treeUrl(ref, path = '') { return `${repoBase()}/tree/${encPath(ref)}${path ? `/${encPath(path)}` : ''}`; }
function blobUrl(ref, path) { return `${repoBase()}/blob/${encPath(ref)}/${encPath(path)}`; }
function rawUrl(ref, path) { return `${repoBase()}/raw/${encPath(ref)}/${encPath(path)}`; }
function commitUrl(sha) { return `${repoBase()}/commit/${sha}`; }
function commitsUrl(ref, path = '') { return `${repoBase()}/commits/${encPath(ref)}${path ? `/${encPath(path)}` : ''}`; }

async function resolveRest(rest) {
  const tail = rest.join('/');
  if (!tail) return { ref: Repo.info.default_branch, kind: 'branch', path: '' };
  return api(repoApi(`/resolve?path=${enc(tail)}`));
}

function shortDate(iso) {
  return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

function breadcrumb(ref, path, { file = false } = {}) {
  const parts = path ? path.split('/') : [];
  let acc = '';
  const crumbs = parts.map((p, i) => {
    acc = acc ? `${acc}/${p}` : p;
    const last = i === parts.length - 1;
    if (last) return `<strong>${esc(p)}</strong>`;
    return `<a href="${treeUrl(ref, acc)}">${esc(p)}</a>`;
  });
  return `<nav class="crumbs" aria-label="Path"><a href="${treeUrl(ref)}"><strong>${esc(Repo.info.name)}</strong></a>${crumbs.map((c) => `<span class="sep">/</span>${c}`).join('')}${file || !parts.length ? '' : '<span class="sep">/</span>'}</nav>`;
}

/* Branch / tag picker. onPick(ref) navigates. */
async function refPicker(container, current, onPick) {
  container.innerHTML = `<div class="picker">
    <button type="button" class="btn sm" id="ref-btn" aria-haspopup="true">${icon('branch')}<span class="truncate" style="max-width:180px">${esc(current)}</span>${icon('chevron')}</button>
    <div class="menu picker-menu" id="ref-menu" hidden>
      <div style="padding:6px"><input type="search" id="ref-filter" placeholder="Find a branch or tag…" aria-label="Find a branch or tag"></div>
      <div class="btn-group" style="padding:0 6px 6px;width:100%"><button type="button" class="btn sm active" data-kind="branches">Branches</button><button type="button" class="btn sm" data-kind="tags">Tags</button></div>
      <div id="ref-items" class="picker-items"><div class="loading"><span class="spinner"></span></div></div>
    </div></div>`;
  const btn = $('#ref-btn', container);
  const menu = $('#ref-menu', container);
  let refs = null;
  let kind = 'branches';
  const draw = () => {
    const q = $('#ref-filter', container).value.trim().toLowerCase();
    const items = (refs[kind] || []).filter((r) => r.name.toLowerCase().includes(q)).slice(0, 200);
    $('#ref-items', container).innerHTML = items.length ? items.map((r) => `<button type="button" data-ref="${esc(r.name)}" class="${r.name === current ? 'current' : ''}">
      <span class="check-slot">${r.name === current ? icon('check') : ''}</span><span class="truncate grow">${esc(r.name)}</span>${r.default ? '<span class="badge">default</span>' : ''}</button>`).join('')
      : `<div class="empty small">Nothing to show</div>`;
  };
  btn.addEventListener('click', async (e) => {
    e.stopPropagation();
    menu.hidden = !menu.hidden;
    if (!menu.hidden) {
      $('#ref-filter', container).focus();
      if (!refs) { refs = await api(repoApi('/refs')); draw(); }
    }
  });
  document.addEventListener('click', (e) => { if (!container.contains(e.target)) menu.hidden = true; });
  $('#ref-filter', container).addEventListener('input', () => refs && draw());
  container.addEventListener('click', (e) => {
    const k = e.target.closest('[data-kind]');
    if (k) {
      kind = k.dataset.kind;
      $$('[data-kind]', container).forEach((b) => b.classList.toggle('active', b === k));
      if (refs) draw();
      return;
    }
    const r = e.target.closest('[data-ref]');
    if (r) onPick(r.dataset.ref);
  });
}

function lastCommitBar(c, ref, path, count) {
  if (!c) return '';
  return `<div class="commit-bar">
    ${avatar(c.author.name)}<strong class="truncate" style="max-width:160px">${esc(c.author.name)}</strong>
    <a class="truncate grow subject" href="${commitUrl(c.sha)}" title="${esc(c.subject)}">${esc(c.subject)}</a>
    <a class="sha" href="${commitUrl(c.sha)}">${c.short}</a>
    <span class="faint small nowrap">${timeTag(c.author.date)}</span>
    ${count != null ? `<a class="btn sm ghost nowrap" href="${commitsUrl(ref, path)}">${icon('history')}${count.toLocaleString()} commit${count === 1 ? '' : 's'}</a>` : ''}
  </div>`;
}

function codeMenu(ref) {
  const base = `${repoBase()}/archive/${encPath(ref)}`;
  return `<div class="picker" id="code-dl">
    <button type="button" class="btn sm primary" id="code-btn">${icon('code')}Code${icon('chevron')}</button>
    <div class="menu picker-menu right" id="code-menu" hidden style="width:min(420px, calc(100vw - 32px))">
      <div style="padding:10px"><h3 style="margin-bottom:8px">${icon('terminal')} Clone</h3>${cloneBox(Repo.info)}</div>
      <hr>
      <a href="${base}.zip" download>${icon('download')}Download ZIP</a>
      <a href="${base}.tar.gz" download>${icon('download')}Download tar.gz</a>
    </div></div>`;
}

function wireCodeMenu(root) {
  const btn = $('#code-btn', root);
  if (!btn) return;
  const menu = $('#code-menu', root);
  btn.addEventListener('click', (e) => { e.stopPropagation(); menu.hidden = !menu.hidden; });
  document.addEventListener('click', (e) => { if (!$('#code-dl', root).contains(e.target)) menu.hidden = true; });
  wireCloneBox(root);
}

function entryIcon(e) {
  if (e.type === 'tree') return icon('folder', 'dir');
  if (e.type === 'submodule') return icon('link');
  return icon('file');
}

function renderReadme(readme) {
  if (!readme) return '';
  const body = readme.html != null ? `<div class="markdown-body">${readme.html}</div>` : `<pre class="readme-text">${esc(readme.text)}</pre>`;
  return `<div class="card" style="margin-top:16px"><div class="card-head">${icon('file')}<h3><a href="${blobUrl(RepoState.ref, readme.path)}" style="color:inherit">${esc(readme.name)}</a></h3></div><div class="card-pad">${body}</div></div>`;
}

const RepoState = { ref: '', path: '' };

async function renderTree(el, ref, path) {
  const data = await api(repoApi(`/tree?ref=${enc(ref)}&path=${enc(path)}`));
  if (data.kind === 'blob') { location.replace(blobUrl(ref, path)); return; }
  RepoState.ref = ref;
  RepoState.path = path;
  document.title = path ? `${Repo.info.full_name}/${path} at ${ref} · mygit` : `${Repo.info.full_name} · mygit`;
  const parent = path.includes('/') ? path.slice(0, path.lastIndexOf('/')) : '';
  el.innerHTML = `<div class="toolbar">
      <div id="ref-picker"></div>
      ${breadcrumb(ref, path)}
      <div class="spacer"></div>
      <a class="btn sm ghost wide-only" href="${repoBase()}/branches">${icon('branch')}Branches</a>
      <a class="btn sm ghost wide-only" href="${repoBase()}/tags">${icon('tag')}Tags</a>
      ${codeMenu(ref)}
    </div>
    <div class="card">
      ${lastCommitBar(data.last_commit, ref, path, data.commit_count)}
      <table class="files"><tbody>
        ${path ? `<tr><td class="f-icon">${icon('folder', 'dir')}</td><td class="f-name"><a href="${parent ? treeUrl(ref, parent) : treeUrl(ref)}">..</a></td><td class="f-msg"></td><td class="f-date"></td></tr>` : ''}
        ${data.entries.map((e) => {
          const href = e.type === 'tree' ? treeUrl(ref, e.path) : e.type === 'submodule' ? '' : blobUrl(ref, e.path);
          return `<tr data-name="${esc(e.name)}">
            <td class="f-icon">${entryIcon(e)}</td>
            <td class="f-name">${href ? `<a href="${href}">${esc(e.name)}</a>` : `<span title="Submodule at ${e.sha.slice(0, 7)}">${esc(e.name)} @ <code>${e.sha.slice(0, 7)}</code></span>`}</td>
            <td class="f-msg"><span class="skeleton"></span></td>
            <td class="f-date"></td></tr>`;
        }).join('')}
      </tbody></table>
      ${data.entries.length ? '' : '<div class="empty">This folder is empty.</div>'}
    </div>
    ${renderReadme(data.readme)}`;
  refPicker($('#ref-picker', el), ref, (r) => { location.href = treeUrl(r, path); });
  wireCodeMenu(el);
  try {
    const last = await api(repoApi(`/tree-commits?ref=${enc(data.commit)}&path=${enc(path)}`));
    $$('tr[data-name]', el).forEach((tr) => {
      const c = last[tr.dataset.name];
      const msg = $('.f-msg', tr);
      if (!c) { msg.innerHTML = ''; return; }
      msg.innerHTML = `<a href="${commitUrl(c.sha)}" title="${esc(c.subject)}">${esc(c.subject)}</a>`;
      $('.f-date', tr).innerHTML = timeTag(c.date);
    });
  } catch {
    $$('.f-msg', el).forEach((m) => { m.innerHTML = ''; });
  }
}

RepoViews.code = {
  tab: 'code',
  async render(el) {
    if (Repo.info.empty) {
      el.innerHTML = quickSetup(Repo.info);
      wireCloneBox(el);
      return;
    }
    const where = Repo.rest[0] === 'tree' ? await resolveRest(Repo.rest.slice(1)) : await resolveRest([]);
    await renderTree(el, where.ref, where.path);
  },
};

function lineTable(lines) {
  return `<table class="code-lines"><tbody>${lines.map((l, i) => `<tr id="L${i + 1}"><td class="ln"><a href="#L${i + 1}" data-line="${i + 1}">${i + 1}</a></td><td class="lc hl">${l || ' '}</td></tr>`).join('')}</tbody></table>`;
}

function markLines() {
  $$('.code-lines tr.marked').forEach((tr) => tr.classList.remove('marked'));
  const m = /^#L(\d+)(?:-L?(\d+))?$/.exec(location.hash);
  if (!m) return;
  const a = Number(m[1]);
  const b = Number(m[2] || m[1]);
  for (let i = Math.min(a, b); i <= Math.max(a, b); i += 1) {
    const tr = document.getElementById(`L${i}`);
    if (tr) tr.classList.add('marked');
  }
  const first = document.getElementById(`L${Math.min(a, b)}`);
  if (first) first.scrollIntoView({ block: 'center' });
}

const IMAGE_EXT = /\.(png|jpe?g|gif|webp|svg|ico|bmp|avif)$/i;

RepoViews.blob = {
  tab: 'code',
  async render(el) {
    const where = await resolveRest(Repo.rest.slice(1));
    const { ref, path } = where;
    const data = await api(repoApi(`/blob?ref=${enc(ref)}&path=${enc(path)}`));
    if (data.kind === 'tree') { location.replace(treeUrl(ref, path)); return; }
    document.title = `${Repo.info.full_name}/${path} at ${ref} · mygit`;
    const raw = rawUrl(ref, path);
    const fileName = path.split('/').pop();
    let body;
    let isMarkdown = false;
    if (data.symlink_target != null) {
      body = `<div class="card-pad">Symbolic link to <code>${esc(data.symlink_target)}</code></div>`;
    } else if (IMAGE_EXT.test(path) && !data.too_large) {
      body = `<div class="card-pad image-view"><img src="${raw}" alt="${esc(fileName)}"></div>`;
    } else if (data.too_large || data.binary) {
      body = `<div class="empty">${icon('file')}<p>${data.too_large ? 'This file is too big to show here.' : 'This is a binary file.'}</p><a class="btn" href="${raw}">${icon('download')}View raw</a></div>`;
    } else if (data.markdown_html != null) {
      isMarkdown = true;
      body = `<div id="md-preview" class="card-pad markdown-body">${data.markdown_html}</div><div id="md-code" hidden>${lineTable(data.lines)}</div>`;
    } else {
      body = data.lines.length ? lineTable(data.lines) : '<div class="empty">This file is empty.</div>';
    }
    el.innerHTML = `<div class="toolbar"><div id="ref-picker"></div>${breadcrumb(ref, path, { file: true })}
        <button class="btn sm ghost icon" id="copy-path" title="Copy path">${icon('copy')}</button></div>
      <div class="card">
        ${lastCommitBar(data.last_commit, ref, path, null)}
        <div class="file-head">
          ${isMarkdown ? '<div class="btn-group"><button class="btn sm active" data-md="preview">Preview</button><button class="btn sm" data-md="code">Code</button></div>' : ''}
          <span class="small muted">${data.line_count != null ? `${data.line_count.toLocaleString()} lines · ` : ''}${formatBytes(data.size)}${data.language && data.language !== 'Text' ? ` · ${esc(data.language)}` : ''}</span>
          <div class="spacer"></div>
          <a class="btn sm" href="${raw}">Raw</a>
          <a class="btn sm icon" href="${raw}" download="${esc(fileName)}" title="Download">${icon('download')}</a>
          ${data.lines ? `<button class="btn sm icon" id="copy-file" title="Copy contents">${icon('copy')}</button>` : ''}
          <a class="btn sm ghost" href="${commitsUrl(ref, path)}">${icon('history')}History</a>
        </div>
        <div class="file-body">${body}</div>
      </div>`;
    refPicker($('#ref-picker', el), ref, (r) => { location.href = blobUrl(r, path); });
    $('#copy-path', el).addEventListener('click', () => copyText(path, 'Path copied'));
    const copyFile = $('#copy-file', el);
    if (copyFile) {
      copyFile.addEventListener('click', async () => {
        const text = await (await fetch(raw, { credentials: 'same-origin' })).text();
        copyText(text, 'File copied');
      });
    }
    if (isMarkdown) {
      el.addEventListener('click', (e) => {
        const b = e.target.closest('[data-md]');
        if (!b) return;
        $$('[data-md]', el).forEach((x) => x.classList.toggle('active', x === b));
        $('#md-preview', el).hidden = b.dataset.md !== 'preview';
        $('#md-code', el).hidden = b.dataset.md !== 'code';
      });
    }
    el.addEventListener('click', (e) => {
      const a = e.target.closest('[data-line]');
      if (!a || !e.shiftKey) return;
      const m = /^#L(\d+)/.exec(location.hash);
      if (!m) return;
      e.preventDefault();
      history.replaceState(null, '', `#L${m[1]}-L${a.dataset.line}`);
      markLines();
    });
    window.addEventListener('hashchange', markLines);
    if (location.hash.startsWith('#L') && isMarkdown) $('[data-md=code]', el).click();
    markLines();
  },
};

function commitRow(c) {
  return `<li class="commit-row">
    <div class="grow" style="min-width:0">
      <a class="subject" href="${commitUrl(c.sha)}">${esc(c.subject)}</a>
      <div class="small muted row" style="gap:6px;margin-top:2px">${avatar(c.author.name)}<strong>${esc(c.author.name)}</strong> committed ${timeTag(c.committer.date)}</div>
    </div>
    <div class="row nowrap"><a class="sha" href="${commitUrl(c.sha)}">${c.short}</a>
      <button class="btn sm ghost icon" data-copy="${c.sha}" title="Copy full SHA">${icon('copy')}</button>
      <a class="btn sm ghost icon" href="${treeUrl(c.sha)}" title="Browse files at this commit">${icon('code')}</a></div>
  </li>`;
}

function commitGroups(commits) {
  const groups = [];
  for (const c of commits) {
    const day = shortDate(c.committer.date);
    if (!groups.length || groups[groups.length - 1].day !== day) groups.push({ day, items: [] });
    groups[groups.length - 1].items.push(c);
  }
  return groups.map((g) => `<h3 class="day">${icon('commit')} Commits on ${esc(g.day)}</h3>
    <div class="card"><ul class="list">${g.items.map(commitRow).join('')}</ul></div>`).join('');
}

function wireCopyButtons(el) {
  el.addEventListener('click', (e) => {
    const b = e.target.closest('[data-copy]');
    if (b) copyText(b.dataset.copy, 'Copied');
  });
}

RepoViews.commits = {
  tab: 'commits',
  async render(el) {
    if (Repo.info.empty) { el.innerHTML = `<div class="card empty">${icon('history')}<p>No commits yet.</p></div>`; return; }
    const where = await resolveRest(Repo.rest.slice(1));
    const page = Number(new URLSearchParams(location.search).get('page') || 1);
    const data = await api(repoApi(`/commits?ref=${enc(where.ref)}&path=${enc(where.path)}&page=${page}`));
    document.title = `Commits · ${Repo.info.full_name} · mygit`;
    el.innerHTML = `<div class="toolbar"><div id="ref-picker"></div>
        ${where.path ? `<span class="muted">History for</span> ${breadcrumb(where.ref, where.path, { file: true })}` : '<h2 style="margin:0">Commits</h2>'}</div>
      ${data.commits.length ? commitGroups(data.commits) : `<div class="card empty">No commits${where.path ? ' touch this path' : ''}.</div>`}
      <div class="row" style="justify-content:center;margin-top:16px">
        <a class="btn sm ${page > 1 ? '' : 'disabled'}" ${page > 1 ? `href="?page=${page - 1}"` : 'aria-disabled="true"'}>Newer</a>
        <a class="btn sm ${data.has_more ? '' : 'disabled'}" ${data.has_more ? `href="?page=${page + 1}"` : 'aria-disabled="true"'}>Older</a>
      </div>`;
    refPicker($('#ref-picker', el), where.ref, (r) => { location.href = commitsUrl(r, where.path); });
    wireCopyButtons(el);
  },
};

function diffFile(f, i) {
  const statusLabel = { added: 'Added', deleted: 'Deleted', renamed: 'Renamed', copied: 'Copied', modified: '' }[f.status];
  const name = f.old_path ? `${esc(f.old_path)} → ${esc(f.path)}` : esc(f.path);
  let body;
  if (f.binary) body = '<div class="empty small">Binary file not shown.</div>';
  else if (!f.hunks.length) body = `<div class="empty small">${f.status === 'renamed' ? 'File renamed without changes.' : 'No content changes (file mode or empty file).'}</div>`;
  else {
    body = `<table class="diff"><tbody>${f.hunks.map((h) => `<tr class="hunk"><td class="ln"></td><td class="ln"></td><td class="dc">${esc(h.header)}</td></tr>${h.lines.map((l) => {
      const cls = l.t === '+' ? 'add' : l.t === '-' ? 'del' : '';
      return `<tr class="${cls}"><td class="ln">${l.old ?? ''}</td><td class="ln">${l.new ?? ''}</td><td class="dc"><span class="mark">${l.t === ' ' ? ' ' : l.t}</span>${esc(l.text)}</td></tr>`;
    }).join('')}`).join('')}</tbody></table>${f.truncated ? '<div class="notice warning" style="margin:8px">This diff is too long to show in full.</div>' : ''}`;
  }
  return `<details class="card diff-file" open id="diff-${i}">
    <summary class="card-head">${icon('chevron', 'chev')}<span class="diffstat"><span class="plus">+${f.additions}</span> <span class="minus">−${f.deletions}</span></span>
      <code class="grow truncate" title="${esc(f.path)}">${name}</code>${statusLabel ? `<span class="badge">${statusLabel}</span>` : ''}</summary>
    <div class="diff-body">${body}</div></details>`;
}

function diffSection(diff, viewRef) {
  const files = diff.files;
  return `<div class="row wrap diff-summary"><span>Showing <strong>${files.length} changed file${files.length === 1 ? '' : 's'}</strong> with <span class="plus">${diff.additions} addition${diff.additions === 1 ? '' : 's'}</span> and <span class="minus">${diff.deletions} deletion${diff.deletions === 1 ? '' : 's'}</span></span>
    <div class="spacer"></div><button class="btn sm" id="toggle-all">Collapse all</button></div>
    ${diff.truncated ? '<div class="notice warning">This change is very large; some files are not shown.</div>' : ''}
    ${files.map(diffFile).join('')}`;
}

function wireDiff(el) {
  const btn = $('#toggle-all', el);
  if (!btn) return;
  btn.addEventListener('click', () => {
    const open = btn.textContent === 'Expand all';
    $$('details.diff-file', el).forEach((d) => { d.open = open; });
    btn.textContent = open ? 'Collapse all' : 'Expand all';
  });
}

RepoViews.commit = {
  tab: 'commits',
  async render(el) {
    const sha = Repo.rest[1] || '';
    const data = await api(repoApi(`/commit/${enc(sha)}`));
    const c = data.commit;
    document.title = `${c.subject} · ${Repo.info.full_name}@${c.short} · mygit`;
    el.innerHTML = `<div class="card commit-head">
        <div class="card-pad">
          <h1 class="commit-title">${esc(c.subject)}</h1>
          ${c.body ? `<pre class="commit-body">${esc(c.body)}</pre>` : ''}
          ${data.branches.length ? `<div class="row wrap small" style="margin-top:8px">${icon('branch')}${data.branches.map((b) => `<a class="badge" href="${treeUrl(b)}">${esc(b)}</a>`).join('')}</div>` : ''}
        </div>
        <div class="commit-meta">
          ${avatar(c.author.name)}<span><strong>${esc(c.author.name)}</strong> authored ${timeTag(c.author.date)}${c.committer.name !== c.author.name ? ` · <strong>${esc(c.committer.name)}</strong> committed ${timeTag(c.committer.date)}` : ''}</span>
          <div class="spacer"></div>
          <span class="small muted">${c.parents.length ? `${c.parents.length > 1 ? 'Parents' : 'Parent'} ${c.parents.map((p) => `<a class="sha" href="${commitUrl(p)}">${p.slice(0, 7)}</a>`).join(' + ')}` : 'Initial commit'}</span>
          <span class="small muted">Commit <code class="sha">${c.sha}</code></span>
          <button class="btn sm ghost icon" data-copy="${c.sha}" title="Copy SHA">${icon('copy')}</button>
          <a class="btn sm" href="${treeUrl(c.sha)}">${icon('code')}Browse files</a>
        </div>
      </div>
      <div style="margin-top:16px">${diffSection(data.diff)}</div>`;
    wireCopyButtons(el);
    wireDiff(el);
  },
};

RepoViews.compare = {
  tab: 'code',
  async render(el) {
    const spec = Repo.rest.slice(1).join('/');
    const data = await api(repoApi(`/compare/${encPath(spec)}`));
    document.title = `Comparing ${data.base}...${data.head} · ${Repo.info.full_name} · mygit`;
    el.innerHTML = `<div class="page-head"><h1>Comparing changes</h1></div>
      <div class="toolbar"><span class="badge">${icon('branch')}base: ${esc(data.base)}</span><span class="faint">…</span><span class="badge">${icon('branch')}compare: ${esc(data.head)}</span></div>
      ${data.commits.length ? `<h3 class="day">${data.commits.length} commit${data.commits.length === 1 ? '' : 's'}</h3><div class="card"><ul class="list">${data.commits.map(commitRow).join('')}</ul></div>`
        : '<div class="card empty">These are identical.</div>'}
      <div style="margin-top:16px">${diffSection(data.diff)}</div>`;
    wireCopyButtons(el);
    wireDiff(el);
  },
};

RepoViews.branches = {
  tab: 'branches',
  async render(el) {
    const data = await api(repoApi('/refs'));
    document.title = `Branches · ${Repo.info.full_name} · mygit`;
    const def = data.branches.find((b) => b.default);
    el.innerHTML = `<div class="page-head"><h2 style="margin:0">Branches</h2><span class="badge">${data.branches.length}</span></div>
      ${data.branches.length ? `<div class="card"><ul class="list">${data.branches.map((b) => `<li class="row wrap" data-branch="${esc(b.name)}">
        ${icon('branch')}<div class="grow" style="min-width:0"><a href="${treeUrl(b.name)}"><strong>${esc(b.name)}</strong></a> ${b.default ? '<span class="badge accent">default</span>' : ''}
          <div class="small muted truncate">Updated ${timeTag(b.date)} · <a href="${commitUrl(b.sha)}" class="muted">${esc(b.subject)}</a></div></div>
        ${!b.default && def ? `<a class="btn sm ghost" href="${repoBase()}/compare/${encPath(def.name)}...${encPath(b.name)}">${icon('diff')}Compare</a>` : ''}
        <a class="btn sm ghost icon" href="${repoBase()}/archive/${encPath(b.name)}.zip" title="Download ZIP" download>${icon('download')}</a>
        ${canWrite() && !b.default ? `<button class="btn sm danger icon" data-delete="${esc(b.name)}" title="Delete branch">${icon('trash')}</button>` : ''}
      </li>`).join('')}</ul></div>` : `<div class="card empty">${icon('branch')}<p>No branches yet.</p></div>`}`;
    el.onclick = async (e) => {
      const b = e.target.closest('[data-delete]');
      if (!b) return;
      const name = b.dataset.delete;
      if (!await confirmDialog(`Delete branch ${name}?`, 'Commits only on this branch can be recovered by pushing the branch again from a clone that has them.', { confirm: 'Delete branch', danger: true })) return;
      try {
        await api(repoApi(`/branches/${encPath(name)}`), { method: 'DELETE' });
        snackbar('Branch deleted');
        this.render(el);
      } catch (err) { snackbar(err.message, 'error'); }
    };
  },
};

RepoViews.tags = {
  tab: 'tags',
  async render(el) {
    const data = await api(repoApi('/refs'));
    document.title = `Tags · ${Repo.info.full_name} · mygit`;
    el.innerHTML = `<div class="page-head"><h2 style="margin:0">Tags</h2><span class="badge">${data.tags.length}</span></div>
      ${data.tags.length ? `<div class="card"><ul class="list">${data.tags.map((t) => `<li class="row wrap">
        ${icon('tag')}<div class="grow" style="min-width:0"><a href="${treeUrl(t.name)}"><strong>${esc(t.name)}</strong></a>
          <div class="small muted truncate">${timeTag(t.date)} · <a class="sha" href="${commitUrl(t.sha)}">${t.sha.slice(0, 7)}</a> ${esc(t.subject)}</div></div>
        <a class="btn sm ghost" href="${repoBase()}/archive/${encPath(t.name)}.zip" download>${icon('download')}zip</a>
        <a class="btn sm ghost" href="${repoBase()}/archive/${encPath(t.name)}.tar.gz" download>${icon('download')}tar.gz</a>
      </li>`).join('')}</ul></div>` : `<div class="card empty">${icon('tag')}<p>No tags yet. Push one with <code>git push origin v1.0.0</code>.</p></div>`}`;
  },
};
