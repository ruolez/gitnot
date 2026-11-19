(async function () {
  const me = await renderShell('home');
  if (!me) { location.replace('/explore'); return; }
  const main = $('#main');
  main.innerHTML = `
    <div class="page-head"><h1>Welcome, ${esc(me.full_name || me.username)}</h1></div>
    <div class="card empty">${icon('repo')}<p>Repositories arrive in the next phase.</p></div>`;
})();
