/* Shared rendering of repository rows (dashboard, owner page, explore). */
function repoHref(owner, name) {
  return `/${encodeURIComponent(owner)}/${encodeURIComponent(name)}`;
}

function repoBadges(r) {
  return `${r.private ? `<span class="badge">${icon('lock')}Private</span>` : '<span class="badge">Public</span>'}${r.archived ? ' <span class="badge warning">Archived</span>' : ''}`;
}

function repoItem(r, { showOwner = true } = {}) {
  const when = r.pushed_at ? `Updated ${timeTag(r.pushed_at)}` : `Created ${timeTag(r.created_at)}`;
  return `<li class="repo-item">${icon(r.private ? 'lock' : 'repo')}
    <div class="grow">
      <h3><a href="${repoHref(r.owner, r.name)}">${showOwner ? `${esc(r.owner)}/` : ''}<strong>${esc(r.name)}</strong></a>${repoBadges(r)}</h3>
      ${r.description ? `<p>${esc(r.description)}</p>` : ''}
      <div class="repo-meta"><span>${when}</span>${r.empty ? '<span>Empty</span>' : ''}</div>
    </div></li>`;
}
