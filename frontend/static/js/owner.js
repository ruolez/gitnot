(async function () {
  const me = await renderShell();
  const main = $('#main');
  const username = decodeURIComponent(location.pathname.split('/')[1]);
  try {
    const user = await api(`/api/users/${encodeURIComponent(username)}`);
    document.title = `${user.username} · mygit`;
    const own = me && me.username.toLowerCase() === user.username.toLowerCase();
    const repos = user.repos.length
      ? `<ul class="list">${user.repos.map((r) => repoItem(r, { showOwner: false })).join('')}</ul>`
      : `<div class="empty">${icon('repo')}<p>${own ? 'You have no repositories yet.' : `${esc(user.username)} has no repositories you can see.`}</p></div>`;
    main.innerHTML = `<div class="split">
      <aside><div class="stack">${avatar(user.username, 'lg')}
        <div><h1 style="margin:0">${esc(user.full_name || user.username)}</h1><div class="muted">${esc(user.username)}</div></div>
        <div class="small faint">Joined ${timeTag(user.created_at)}</div></div></aside>
      <section>
        <div class="page-head"><h2 style="margin:0">Repositories</h2><span class="badge">${user.repos.length}</span><div class="spacer"></div>${own ? `<a class="btn primary sm" href="/new">${icon('plus')}New</a>` : ''}</div>
        <div class="card">${repos}</div>
      </section></div>`;
  } catch (err) { showError(main, err); }
})();
