# mygit

A small self-hosted Git server for a team: push, pull and clone over **HTTPS and SSH** with the normal `git` command, browse code on the web, publish **releases**, and serve the raw files, archives and release feeds that app installers and updaters use.

| | |
|---|---|
| Stack | Python 3.12 Flask + gunicorn, PostgreSQL 16, nginx, vanilla JS (no build step), Docker Compose |
| Git transport | `git http-backend` behind nginx `auth_request` (HTTPS), OpenSSH with a forced command (SSH) |
| Ports | 5564 web + git over HTTPS, 2222 git over SSH |

## Install (Ubuntu 22.04 / 24.04)

```bash
sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/ruolez/mygit/main/install.sh)"
```

- **With a domain** (e.g. `git.example.com`): mygit goes behind the [shared proxy](https://github.com/ruolez/shared-proxy), which owns ports 80/443 and gets a Let's Encrypt certificate. The web port only listens on 127.0.0.1.
- **Without a domain**: plain HTTP on port 5564 (fine on a LAN; tokens then travel unencrypted).
- SSH for git listens on port 2222. Open it in your provider's firewall too (e.g. IONOS Cloud Panel).

The installer menu also does **Update** (backup, pull, rebuild; data kept), **Backup**, **Restore**, **SSL**, **Status** and **Remove**. Non-interactive: `install.sh install|update|backup|restore <dir>|ssl|status|remove`.

Backups go to `/opt/mygit-backups/mygit-<time>/` (database dump, repositories, release files, SSH host keys, `.env`); the last 10 are kept.

## Using it

**HTTPS.** Make a token in *Settings › Access tokens*, then use it as the password when git asks (macOS Keychain and Git Credential Manager remember it):

```bash
git remote add origin https://git.example.com/you/app.git
git push -u origin main
```

**SSH.** Add your key in *Settings › SSH keys*, and add this to `~/.ssh/config` so the short form works:

```
Host git.example.com
  User git
  Port 2222
```

then `git clone git@git.example.com:you/app.git`. Check with `ssh -T git@git.example.com`.

Everything git can do works, because mygit runs git's own server programs: branches, tags, force pushes, shallow (`--depth`) and partial (`--filter=blob:none`) clones, protocol v0 and v2, `git archive --remote` over SSH.

## For installers and updaters

| What | URL |
|---|---|
| Raw file | `https://git.example.com/raw/<owner>/<repo>/<branch>/<path>` (also `/<owner>/<repo>/raw/<ref>/<path>` and `/raw/<owner>/<repo>/refs/heads/<branch>/<path>`) |
| One-line install | `bash -c "$(curl -fsSL https://git.example.com/raw/you/app/main/install.sh)"` |
| Archive | `/<owner>/<repo>/archive/<ref>.tar.gz` or `.zip` |
| Release file | `/<owner>/<repo>/releases/download/<tag>/<file>` and `/releases/latest/download/<file>` (resumable) |
| Releases API | `/api/v1/repos/<owner>/<repo>/releases`, `/releases/latest`, `/releases/tags/<tag>`: same JSON as GitHub's REST API, so an updater only needs a new base URL |

Raw files are served fresh (ETag, no 5-minute cache like raw.githubusercontent.com). Raw content is never rendered as a page: text is `text/plain` and every response has a sandbox CSP.

**Private repositories**: create a read-only *deploy token* in the repo's Settings and use it as `https://deploy:<token>@git.example.com/you/app.git`, `curl -u deploy:<token> …`, or `Authorization: token <token>`.

## Releases from scripts: the `mygit` CLI

```bash
curl -fsSL https://git.example.com/cli/mygit -o /usr/local/bin/mygit && chmod +x /usr/local/bin/mygit
mygit login https://git.example.com
mygit release create you/app v1.2.0 dist/*.zip --notes-file CHANGES.md
mygit release create you/app v1.2.0-windows dist/win/* --latest=false
mygit release upload you/app v1.2.0 extra.sig --clobber
mygit release list you/app
```

Python 3 standard library only. `MYGIT_URL` / `MYGIT_TOKEN` override the saved login.

## Moving from GitHub

*New repository › Import* copies branches, tags and (optionally) releases with their files from GitHub. A repo's *Settings › Push mirror* pushes every change on to GitHub, so GitHub stays a live backup while servers still pull from it. See [docs/MIGRATING.md](docs/MIGRATING.md).

## How it works

```
browser / git ──https──> host nginx (TLS) ──> nginx (container) ──auth_request──> backend (Flask)
                                               │                                     ▲   ▲
                                               └─ fastcgi ─> git container ──hooks───┘   │
git (ssh) ──:2222──> git container: sshd ──AuthorizedKeysCommand / mygit-serve───────────┘
                                                                        worker: imports, mirrors
```

- nginx asks the backend (`/internal/git-auth`) whether a git request may go ahead, then hands it to `git http-backend`. Refusals reach the git client as `remote error: Repository not found`.
- sshd looks every key up through the backend; each key runs `mygit-serve`, which only starts `git upload-pack`, `receive-pack` or `upload-archive` on a repository the key may use. No shells, PTYs or forwarding.
- `pre-receive` enforces protected branches/tags and the file size limit; `post-receive` records the push, fixes HEAD and queues the push mirror.
- Bare repositories live at `/data/repos/<id>.git`, named by id, so renames and transfers only change the database (old URLs redirect).

## Development

```bash
scripts/make-env.sh
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
open http://localhost:5564        # admin / password printed by make-env.sh
```

Tests:

```bash
docker exec mygit-backend python -m unittest discover -s tests                 # unit (no DB)
docker compose -f docker-compose.yml -f qa/compose.qa.yml run --rm qa           # e2e, git 2.39
QA_BASE=ubuntu:24.04 QA_TAG=noble docker compose -f docker-compose.yml -f qa/compose.qa.yml run --rm qa   # git 2.43
bash qa/install/e2e.sh                                                          # installer on Ubuntu 24.04 (~10 min)
```

The e2e suite drives the real git client (HTTPS and SSH, protocol v0/v2, big pushes, refusals), raw/archive URLs, `curl | bash`, releases, the CLI, imports and mirrors.
