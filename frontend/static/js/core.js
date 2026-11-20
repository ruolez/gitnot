/* Shared helpers for every page: API calls, escaping, icons, the top bar,
   dialogs, theme. Pages are plain scripts loaded after this one. */

(function applyTheme() {
  let t = null;
  try { t = localStorage.getItem('mygit-theme'); } catch { /* storage off */ }
  if (t === 'light' || t === 'dark') document.documentElement.dataset.theme = t;
})();

const Mygit = {};

async function api(path, options = {}) {
  const opts = { credentials: 'same-origin', ...options };
  opts.headers = { 'X-Requested-With': 'mygit', ...(options.headers || {}) };
  if (opts.body !== undefined && !(opts.body instanceof FormData) && !(opts.body instanceof Blob)
      && typeof opts.body !== 'string') {
    opts.body = JSON.stringify(opts.body);
    opts.headers['Content-Type'] = 'application/json';
  }
  const res = await fetch(path, opts);
  let data = null;
  const type = res.headers.get('Content-Type') || '';
  if (type.includes('application/json')) {
    try { data = await res.json(); } catch { data = null; }
  }
  if (!res.ok) {
    const err = new Error((data && data.error) || `Request failed (${res.status})`);
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function $(sel, root = document) { return root.querySelector(sel); }
function $$(sel, root = document) { return [...root.querySelectorAll(sel)]; }

const ICONS = {
  repo: '<path d="M4 19.5V5a2 2 0 0 1 2-2h13v16H6.5A2.5 2.5 0 0 0 4 21.5"/><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H19"/>',
  lock: '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  branch: '<circle cx="6" cy="5" r="2"/><circle cx="6" cy="19" r="2"/><circle cx="18" cy="7" r="2"/><path d="M6 7v10M18 9a6 6 0 0 1-6 6H8"/>',
  tag: '<path d="M20.6 13.4 13.4 20.6a2 2 0 0 1-2.8 0L3 13V3h10l7.6 7.6a2 2 0 0 1 0 2.8Z"/><circle cx="7.5" cy="7.5" r="1.5"/>',
  commit: '<circle cx="12" cy="12" r="3.5"/><path d="M3 12h5.5M15.5 12H21"/>',
  history: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5M12 7v5l3 2"/>',
  file: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z"/><path d="M14 3v6h6"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
  copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h8"/>',
  check: '<path d="m5 12 5 5L20 7"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  key: '<circle cx="8" cy="15" r="4"/><path d="m11 12 9-9M17 6l3 3M14 9l2 2"/>',
  token: '<path d="M21 2l-2 2m-7.6 7.6a5.5 5.5 0 1 1-7.8 7.8 5.5 5.5 0 0 1 7.8-7.8Zm0 0L15.5 7.5m0 0 3 3L22 7l-3-3m-3.5 3.5L19 4"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0M16 4.5a3.5 3.5 0 0 1 0 7M18 14a6.5 6.5 0 0 1 3.5 6"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z"/>',
  shield: '<path d="M12 3 4 6v6c0 5 3.4 8.5 8 9 4.6-.5 8-4 8-9V6Z"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z"/>',
  download: '<path d="M12 3v12M7 10l5 5 5-5M5 21h14"/>',
  upload: '<path d="M12 21V9M7 14l5-5 5 5M5 3h14"/>',
  package: '<path d="m21 8-9-5-9 5v8l9 5 9-5Z"/><path d="m3 8 9 5 9-5M12 13v8"/>',
  code: '<path d="m8 16-4-4 4-4M16 8l4 4-4 4M14 4l-4 16"/>',
  trash: '<path d="M3 6h18M8 6V4h8v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>',
  edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
  terminal: '<path d="m4 17 6-6-6-6M12 19h8"/>',
  chevron: '<path d="m6 9 6 6 6-6"/>',
  arrowLeft: '<path d="M19 12H5M12 19l-7-7 7-7"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
  star: '<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1 6.2L12 17.3 6.5 20.2l1-6.2L3 9.6l6.2-.9Z"/>',
  archive: '<rect x="3" y="4" width="18" height="4" rx="1"/><path d="M5 8v11a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8M10 12h4"/>',
  diff: '<path d="M12 3v14M5 10h14M5 21h14"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 16v-4M12 8h.01"/>',
  mirror: '<path d="M17 2l4 4-4 4"/><path d="M3 11V9a3 3 0 0 1 3-3h15M7 22l-4-4 4-4"/><path d="M21 13v2a3 3 0 0 1-3 3H3"/>',
};

function icon(name, cls = '') {
  return `<svg class="ico ${cls}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ''}</svg>`;
}

const AVATAR_COLORS = ['#2563eb', '#7c3aed', '#db2777', '#dc2626', '#ea580c', '#ca8a04', '#16a34a', '#0d9488', '#0891b2', '#4f46e5'];
function avatar(name, cls = '') {
  let h = 0;
  for (const c of String(name || '?')) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return `<span class="avatar ${cls}" style="background:${AVATAR_COLORS[h % AVATAR_COLORS.length]}" aria-hidden="true">${esc(String(name || '?').slice(0, 1))}</span>`;
}

function timeAgo(iso) {
  if (!iso) return '';
  const then = new Date(iso);
  const s = Math.round((Date.now() - then.getTime()) / 1000);
  const fmt = (n, unit) => `${n} ${unit}${n === 1 ? '' : 's'} ago`;
  if (s < 45) return 'just now';
  if (s < 3600) return fmt(Math.max(1, Math.round(s / 60)), 'minute');
  if (s < 86400) return fmt(Math.round(s / 3600), 'hour');
  if (s < 86400 * 30) return fmt(Math.round(s / 86400), 'day');
  return then.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

function timeTag(iso) {
  if (!iso) return '';
  return `<time datetime="${esc(iso)}" title="${esc(new Date(iso).toLocaleString())}">${esc(timeAgo(iso))}</time>`;
}

function formatBytes(n) {
  if (n == null) return '';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  let v = Number(n);
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i += 1; }
  return `${i === 0 ? v : v.toFixed(v < 10 ? 1 : 0)} ${units[i]}`;
}

let snackTimer = null;
function snackbar(message, type = '') {
  let el = document.getElementById('snackbar');
  if (!el) {
    el = document.createElement('div');
    el.id = 'snackbar';
    el.setAttribute('role', 'status');
    document.body.appendChild(el);
  }
  el.textContent = message;
  el.className = `show ${type}`;
  clearTimeout(snackTimer);
  snackTimer = setTimeout(() => { el.className = ''; }, 4500);
}

async function copyText(text, label = 'Copied') {
  try {
    await navigator.clipboard.writeText(text);
    snackbar(label);
  } catch {
    snackbar('Copy failed; select the text and copy it', 'error');
  }
}

/* A modal with a body (HTML) and buttons. Resolves with the button's value,
   or null when dismissed. onSubmit(dialogEl) may throw to keep it open. */
function openDialog({ title, body, buttons = [], onSubmit }) {
  return new Promise((resolve) => {
    const back = document.createElement('div');
    back.className = 'dialog-backdrop';
    back.innerHTML = `<form class="dialog" role="dialog" aria-modal="true" aria-label="${esc(title)}">
      <header><h2>${esc(title)}</h2></header>
      <div class="dialog-body">${body}<div class="form-error" hidden></div></div>
      <footer>${buttons.map((b, i) => `<button type="${b.submit ? 'submit' : 'button'}" class="btn ${b.cls || ''}" data-i="${i}">${esc(b.label)}</button>`).join('')}</footer>
    </form>`;
    const form = back.querySelector('form');
    const errEl = back.querySelector('.form-error');
    const close = (value) => {
      back.remove();
      document.removeEventListener('keydown', onKey);
      resolve(value);
    };
    const onKey = (e) => { if (e.key === 'Escape') close(null); };
    document.addEventListener('keydown', onKey);
    back.addEventListener('mousedown', (e) => { if (e.target === back) close(null); });
    form.addEventListener('click', (e) => {
      const btn = e.target.closest('button[data-i]');
      if (!btn || btn.type === 'submit') return;
      const b = buttons[Number(btn.dataset.i)];
      close(b.value === undefined ? null : b.value);
    });
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const submit = buttons.find((b) => b.submit);
      const btn = form.querySelector('button[type=submit]');
      if (!onSubmit) { close(submit ? submit.value ?? true : true); return; }
      errEl.hidden = true;
      if (btn) btn.disabled = true;
      try {
        const result = await onSubmit(form);
        close(result === undefined ? true : result);
      } catch (err) {
        errEl.textContent = err.message;
        errEl.hidden = false;
        if (btn) btn.disabled = false;
      }
    });
    document.body.appendChild(back);
    const first = form.querySelector('input, select, textarea') || form.querySelector('button[type=submit]');
    if (first) first.focus();
  });
}

function confirmDialog(title, message, { confirm = 'Confirm', danger = false, typeToConfirm = null } = {}) {
  const extra = typeToConfirm
    ? `<label class="field"><span>Type <code>${esc(typeToConfirm)}</code> to confirm</span><input type="text" name="confirm" autocomplete="off" required></label>`
    : '';
  return openDialog({
    title,
    body: `<p>${message}</p>${extra}`,
    buttons: [{ label: 'Cancel' }, { label: confirm, cls: danger ? 'danger' : 'primary', submit: true, value: true }],
    onSubmit: typeToConfirm ? (form) => {
      if (form.confirm.value.trim() !== typeToConfirm) throw new Error('That does not match');
      return true;
    } : null,
  });
}

function formData(form) {
  const out = {};
  for (const el of form.elements) {
    if (!el.name) continue;
    if (el.type === 'checkbox') out[el.name] = el.checked;
    else if (el.type === 'radio') { if (el.checked) out[el.name] = el.value; } else out[el.name] = el.value;
  }
  return out;
}

/* ---------- session + top bar ---------- */

Mygit.me = undefined;

async function loadMe() {
  if (Mygit.me !== undefined) return Mygit.me;
  try {
    Mygit.me = await api('/api/auth/me');
  } catch (err) {
    if (err.status !== 401) throw err;
    Mygit.me = null;
  }
  return Mygit.me;
}

function loginUrl() {
  return `/login?next=${encodeURIComponent(location.pathname + location.search)}`;
}

async function requireLogin() {
  const me = await loadMe();
  if (!me) {
    location.replace(loginUrl());
    return new Promise(() => {});
  }
  return me;
}

function themeIsDark() {
  const t = document.documentElement.dataset.theme;
  if (t) return t === 'dark';
  return matchMedia('(prefers-color-scheme: dark)').matches;
}

function toggleTheme() {
  const next = themeIsDark() ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem('mygit-theme', next); } catch { /* storage off */ }
}

async function renderShell(active = '') {
  const me = await loadMe();
  const bar = document.createElement('header');
  bar.className = 'topbar';
  bar.innerHTML = `<div class="topbar-inner">
      <a class="brand" href="/"><span class="brand-mark">${icon('branch')}</span>git-Not</a>
      <nav class="topnav">
        <a href="/explore" class="${active === 'explore' ? 'active' : ''}">Explore</a>
      </nav>
      <div class="spacer"></div>
      ${me ? `
        <a class="btn sm" href="/new" title="New repository">${icon('plus')}<span>New</span></a>
        <div class="user-menu">
          <button class="btn ghost icon" id="user-btn" aria-haspopup="true" aria-expanded="false" title="Account">${avatar(me.username)}</button>
          <div class="menu" id="user-menu" hidden>
            <div class="menu-head">Signed in as <strong>${esc(me.username)}</strong></div>
            <a href="/${encodeURIComponent(me.username)}">${icon('repo')}Your repositories</a>
            <a href="/settings">${icon('gear')}Settings</a>
            ${me.is_admin ? `<a href="/-/admin">${icon('shield')}Site admin</a>` : ''}
            <button type="button" id="theme-btn">${icon('moon')}Toggle theme</button>
            <hr>
            <button type="button" id="logout-btn">${icon('logout')}Sign out</button>
          </div>
        </div>` : `
        <button class="btn ghost icon" id="theme-btn" title="Toggle theme">${icon('moon')}</button>
        <a class="btn primary sm" href="${esc(loginUrl())}">Sign in</a>`}
    </div>`;
  document.body.prepend(bar);
  const themeBtn = $('#theme-btn', bar);
  if (themeBtn) themeBtn.addEventListener('click', toggleTheme);
  const userBtn = $('#user-btn', bar);
  if (userBtn) {
    const menu = $('#user-menu', bar);
    userBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      menu.hidden = !menu.hidden;
      userBtn.setAttribute('aria-expanded', String(!menu.hidden));
    });
    document.addEventListener('click', (e) => { if (!menu.contains(e.target)) menu.hidden = true; });
    $('#logout-btn', bar).addEventListener('click', async () => {
      await api('/api/auth/logout', { method: 'POST' });
      location.href = '/login';
    });
  }
  return me;
}

function showError(container, err) {
  const status = err && err.status;
  const title = status === 404 ? 'Not found' : 'Something went wrong';
  const msg = status === 404 ? 'This page does not exist, or you do not have access to it.' : esc(err.message || String(err));
  container.innerHTML = `<div class="card empty">${icon('info')}<h2>${title}</h2><p class="muted">${msg}</p></div>`;
}
