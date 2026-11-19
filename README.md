# mygit

A small self-hosted Git server: push, pull and clone over **HTTPS and SSH** with the normal `git` command, browse code on the web, and publish releases. Built for hosting our own apps and the installers that update them.

| | |
|---|---|
| Stack | Python 3.12 Flask + gunicorn, PostgreSQL 16, nginx, vanilla JS, Docker Compose |
| Git transport | `git http-backend` (HTTPS) and OpenSSH + forced command (SSH) |
| Port | 5564 (web + HTTPS git), 2222 (SSH) |

## How it works

```
browser / git ──> nginx ──auth_request──> backend (Flask)
                    │                        ▲
                    └─ fastcgi ─> git container (git-http-backend, sshd, hooks)
```

- nginx asks the backend whether a git request may go ahead, then hands it to `git http-backend`.
- SSH keys are looked up through the backend; every key runs `mygit-serve`, which only starts `git upload-pack`, `receive-pack` or `upload-archive`.
- The `pre-receive` hook enforces branch rules and the file size limit; `post-receive` records the push.

## Development

```bash
scripts/make-env.sh
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
open http://localhost:5564
```

- [ ] Releases
- [x] HTTPS and SSH
