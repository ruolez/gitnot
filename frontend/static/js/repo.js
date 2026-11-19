/* Repository pages. /<owner>/<repo>/<view>/<rest...>; each view renders
   into #view. Views register in RepoViews (later scripts add more). */

const RepoViews = {};
const Repo = { owner: '', name: '', info: null, me: null, rest: [] };

function repoBase() { return repoHref(Repo.info.owner, Repo.info.name); }

function canWrite() { return ['write', 'admin'].includes(Repo.info.permission); }
function isRepoAdmin() { return Repo.info.permission === 'admin'; }

function cloneBox(info) {
  const urls = info.clone_urls;
  return `<div class="clone-box" id="clone-box">
    <div class="btn-group" role="tablist">
      <button type="button" class="btn sm active" data-proto="https">HTTPS</button>
      <button type="button" class="btn sm" data-proto="ssh">SSH</button>
    </div>
    <input type="text" readonly value="${esc(urls.https)}" aria-label="Clone URL" id="clone-url">
    <button type="button" class="btn sm icon" id="clone-copy" title="Copy">${icon('copy')}</button>
  </div>`;
}

function wireCloneBox(root) {
  const box = $('#clone-box', root);
  if (!box) return;
  const input = $('#clone-url', box);
  let proto = 'https';
  try { proto = localStorage.getItem('mygit-clone-proto') || 'https'; } catch { /* storage off */ }
  const set = (p) => {
    proto = p;
    input.value = Repo.info.clone_urls[p];
    $$('[data-proto]', box).forEach((b) => b.classList.toggle('active', b.dataset.proto === p));
    try { localStorage.setItem('mygit-clone-proto', p); } catch { /* storage off */ }
    $$('[data-clone-url]', root).forEach((el) => { el.textContent = Repo.info.clone_urls[p]; });
  };
  set(proto);
  box.addEventListener('click', (e) => {
    const b = e.target.closest('[data-proto]');
    if (b) set(b.dataset.proto);
  });
  $('#clone-copy', box).addEventListener('click', () => copyText(input.value, 'Clone URL copied'));
  input.addEventListener('focus', () => input.select());
}

function quickSetup(info) {
  const branch = info.default_branch;
  return `<div class="card card-pad setup">
    <h2>Quick setup</h2>
    <p class="muted">This repository is empty. Push an existing project, or start a new one.</p>
    ${cloneBox(info)}
    <h3>Push an existing repository</h3>
    <pre class="code">git remote add origin <span data-clone-url>${esc(info.clone_urls.https)}</span>
git push -u origin ${esc(branch)}</pre>
    <h3>Start a new repository</h3>
    <pre class="code">echo "# ${esc(info.name)}" > README.md
git init -b ${esc(branch)}
git add README.md
git commit -m "first commit"
git remote add origin <span data-clone-url>${esc(info.clone_urls.https)}</span>
git push -u origin ${esc(branch)}</pre>
    <h3>Signing in</h3>
    <p class="muted">Git asks for a username and password: use your username and a <a href="/settings/tokens">personal access token</a> as the password, not your account password. The macOS Keychain and Git Credential Manager remember it. For SSH, add a key in <a href="/settings/keys">Settings › SSH keys</a>.</p>
  </div>`;
}

const REPO_TABS = [
  { key: 'code', label: 'Code', icon: 'code', path: '' },
  { key: 'commits', label: 'Commits', icon: 'history', path: '/commits' },
  { key: 'branches', label: 'Branches', icon: 'branch', path: '/branches' },
  { key: 'tags', label: 'Tags', icon: 'tag', path: '/tags' },
  { key: 'releases', label: 'Releases', icon: 'package', path: '/releases' },
  { key: 'settings', label: 'Settings', icon: 'gear', path: '/settings', admin: true },
];

function renderRepoHeader(activeTab) {
  const info = Repo.info;
  const head = document.createElement('div');
  head.className = 'repo-head';
  head.innerHTML = `<div class="repo-head-inner">
    <div class="repo-title">${icon(info.private ? 'lock' : 'repo')}
      <a href="/${encodeURIComponent(info.owner)}">${esc(info.owner)}</a><span class="sep">/</span>
      <strong><a href="${repoBase()}">${esc(info.name)}</a></strong>${repoBadges(info)}
    </div>
    ${info.description ? `<p class="muted" style="margin-top:-6px">${esc(info.description)}</p>` : ''}
    <nav class="tabs">${REPO_TABS.filter((t) => !t.admin || isRepoAdmin()).map((t) => `<a href="${repoBase()}${t.path}" class="${t.key === activeTab ? 'active' : ''}" data-tab="${t.key}">${icon(t.icon)}${t.label}</a>`).join('')}</nav>
  </div>`;
  $('.topbar').after(head);
}

function pickView(rest) {
  const first = rest[0] || '';
  const map = {
    '': 'code', tree: 'code', blob: 'blob', raw: 'code', commits: 'commits', commit: 'commit',
    compare: 'compare', branches: 'branches', tags: 'tags', releases: 'releases', settings: 'settings',
  };
  const key = map[first];
  return key && RepoViews[key] ? RepoViews[key] : null;
}

// Views come from later scripts; start once every script has run.
document.addEventListener('DOMContentLoaded', async () => {
  Repo.me = await renderShell();
  const parts = location.pathname.split('/').filter(Boolean).map(decodeURIComponent);
  [Repo.owner, Repo.name] = parts;
  Repo.rest = parts.slice(2);
  const main = $('#main');
  if (Repo.name.toLowerCase().endsWith('.git')) {
    location.replace(repoHref(Repo.owner, Repo.name.slice(0, -4)));
    return;
  }
  try {
    Repo.info = await api(`/api/repos/${encodeURIComponent(Repo.owner)}/${encodeURIComponent(Repo.name)}`);
  } catch (err) {
    if (err.status === 404 && !Repo.me) { location.replace(loginUrl()); return; }
    showError(main, err);
    return;
  }
  if (Repo.info.owner !== Repo.owner || Repo.info.name !== Repo.name) {
    // Renamed, or typed with other capitals: show the canonical address.
    const fixed = repoHref(Repo.info.owner, Repo.info.name) + location.pathname.split('/').slice(3).map((p) => `/${p}`).join('');
    history.replaceState(null, '', fixed + location.search + location.hash);
  }
  document.title = `${Repo.info.full_name} · mygit`;
  const view = pickView(Repo.rest);
  renderRepoHeader(view ? view.tab : '');
  main.innerHTML = '<div id="view"></div>';
  if (!view) { showError($('#view'), { status: 404 }); return; }
  try {
    await view.render($('#view'));
  } catch (err) { showError($('#view'), err); }
});
