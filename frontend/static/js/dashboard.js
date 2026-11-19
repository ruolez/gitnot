function eventItem(e) {
  const [owner, name] = e.repo.split('/');
  const base = repoHref(owner, name);
  const isTag = e.ref.startsWith('refs/tags/');
  const short = e.ref.replace(/^refs\/(heads|tags)\//, '');
  const zero = /^0+$/;
  const refLink = `<a href="${base}/tree/${encodeURIComponent(short)}"><code>${esc(short)}</code></a>`;
  let what;
  if (zero.test(e.new_sha)) what = `deleted ${isTag ? 'tag' : 'branch'} <code>${esc(short)}</code> from`;
  else if (zero.test(e.old_sha)) what = `created ${isTag ? 'tag' : 'branch'} ${refLink} in`;
  else what = `pushed to ${refLink} in`;
  const range = !zero.test(e.old_sha) && !zero.test(e.new_sha)
    ? ` <a class="sha" href="${base}/compare/${e.old_sha.slice(0, 12)}...${e.new_sha.slice(0, 12)}">${e.old_sha.slice(0, 7)}…${e.new_sha.slice(0, 7)}</a>` : '';
  return `<li class="event">${icon(isTag ? 'tag' : 'commit')}<div class="grow">
    <div><strong>${esc(e.actor || 'someone')}</strong> ${what} <a href="${base}">${esc(e.repo)}</a>${range}</div>
    <div class="small faint">${timeTag(e.at)} · via ${e.via === 'ssh' ? 'SSH' : 'HTTPS'}</div></div></li>`;
}

(async function () {
  const me = await renderShell('home');
  if (!me) { location.replace('/explore'); return; }
  const main = $('#main');
  try {
    const [repos, activity] = await Promise.all([api('/api/repos'), api('/api/activity')]);
    main.innerHTML = `<div class="dash">
      <aside class="card">
        <div class="card-head"><h2>Repositories</h2><div class="grow"></div><a class="btn primary sm" href="/new">${icon('plus')}New</a></div>
        ${repos.length ? '<div class="filter"><input type="search" id="repo-filter" placeholder="Find a repository…" aria-label="Find a repository"></div>' : ''}
        <ul class="list compact-list" id="repo-list">${repos.map((r) => `<li data-name="${esc(r.full_name.toLowerCase())}">${avatar(r.owner)}<a class="truncate" href="${repoHref(r.owner, r.name)}">${esc(r.owner)}/${esc(r.name)}</a>${r.private ? `<span class="faint" title="Private">${icon('lock')}</span>` : ''}</li>`).join('')}</ul>
        ${repos.length ? '' : `<div class="empty"><p>You have no repositories yet.</p><a class="btn primary" href="/new">${icon('plus')}Create a repository</a></div>`}
      </aside>
      <section>
        <div class="page-head"><h1>Recent activity</h1></div>
        <div class="card">${activity.length ? `<ul class="list">${activity.map(eventItem).join('')}</ul>` : `<div class="empty">${icon('history')}<p>Pushes to repositories you can see show up here.</p></div>`}</div>
      </section>
    </div>`;
  } catch (err) { showError(main, err); return; }
  const filter = $('#repo-filter');
  if (filter) {
    filter.addEventListener('input', () => {
      const q = filter.value.trim().toLowerCase();
      $$('#repo-list li').forEach((li) => { li.hidden = Boolean(q) && !li.dataset.name.includes(q); });
    });
  }
})();
