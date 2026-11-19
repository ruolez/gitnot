(async function () {
  await renderShell('explore');
  const main = $('#main');
  main.className = 'page narrow';
  const q = new URLSearchParams(location.search).get('q') || '';
  main.innerHTML = `<div class="page-head"><h1>Explore repositories</h1></div>
    <form class="row" style="margin-bottom:16px" id="search"><input type="search" name="q" value="${esc(q)}" placeholder="Search by name, description or owner" aria-label="Search repositories"><button class="btn" type="submit">${icon('search')}Search</button></form>
    <div class="card" id="results"><div class="loading"><span class="spinner"></span></div></div>`;
  $('#search').addEventListener('submit', (e) => {
    e.preventDefault();
    const v = e.target.q.value.trim();
    location.search = v ? `?q=${encodeURIComponent(v)}` : '';
  });
  try {
    const repos = await api(`/api/explore${q ? `?q=${encodeURIComponent(q)}` : ''}`);
    $('#results').innerHTML = repos.length ? `<ul class="list">${repos.map((r) => repoItem(r)).join('')}</ul>`
      : `<div class="empty">${icon('search')}<p>${q ? 'No repositories match.' : 'No public repositories yet.'}</p></div>`;
  } catch (err) { showError($('#results'), err); }
})();
