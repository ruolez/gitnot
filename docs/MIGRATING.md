# Moving the apps from GitHub to git-Not

Do one app at a time. Below, `GIT=https://gitnot.site` is git-Not's address.

## 1. Bring the repository over

1. *New repository › Import*, URL `https://github.com/ruolez/<app>.git`.
   - For vs-gammon choose **Code + every release** so the updaters find the existing builds.
   - For a private GitHub repo, add a GitHub token with read access.
2. On your Mac, point the checkout at git-Not and keep GitHub as a second remote:
   ```bash
   git remote rename origin github
   git remote add origin $GIT/ruolez/<app>.git
   git fetch origin && git branch -u origin/main
   ```
3. In the repo's *Settings › Push mirror*, add `https://github.com/ruolez/<app>.git` with a GitHub token that can push (fine-grained, *Contents: read and write*).
   - From now on every push to git-Not also lands on GitHub.
   - Servers that still pull from GitHub keep getting updates.

## 2. Change the installer

Every installer has the GitHub address in two places:

| Was | Becomes |
|---|---|
| `REPO_URL=https://github.com/ruolez/<app>.git` | `REPO_URL=$GIT/ruolez/<app>.git` |
| `https://raw.githubusercontent.com/ruolez/<app>/main/install.sh` (header comment, README) | `$GIT/raw/ruolez/<app>/main/install.sh` |

The **update** step must re-point existing installs before it fetches. Otherwise a server installed from GitHub keeps pulling from GitHub. remote-control already does this:

```bash
git -C "$INSTALL_DIR" remote set-url origin "$REPO_URL"
git -C "$INSTALL_DIR" fetch origin main
git -C "$INSTALL_DIR" reset --hard origin/main
```

Push that installer change (it reaches GitHub through the mirror). Then run the app's normal *Update* on each server:
- the update runs the new script, which switches the remote to git-Not;
- every update after that comes from git-Not.

| App | Installer lines to change |
|---|---|
| ispend | `install.sh`: `REPO_URL` (`:16`), header (`:5`). Add `remote set-url` before `fetch` (`:531`). `SHARED_PROXY_URL` (`:25`) can point at `$GIT/raw/ruolez/shared-proxy/main/install.sh` |
| easyship | `install.sh`: `REPO_URL` (`:11`), header (`:5`). Add `remote set-url` before `fetch` (`:209`) |
| edgebourne | `install.sh`: `REPO_URL` (`:19`), header (`:5`), `SHARED_PROXY_URL` (`:28`). Add `remote set-url` before both `fetch` calls (`:408`, `:492`) |
| vs-gammon | `install.sh`: `REPO_URL` default (`:14`), header (`:4`). Add `remote set-url` in update (`:140`). The updaters are covered in section 3 |
| remote-control | `install.sh`: `REPO_URL` default (`:19`), header (`:4`). It already re-points the remote. Agent builds stay on GitHub Actions for now |
| shared-proxy | Header (`:8`). The apps reference its raw URL through `SHARED_PROXY_URL` |
| Quotation-Scan | `instal.sh`: `REPO_URL` (`:27`). It uses `git pull`: add `git remote set-url origin "$REPO_URL"` before it (`:320`) |
| bin-locations | `GITHUB_REPO` (`:21`). Add `remote set-url` before `git pull` (`:290`) |

Public repositories need no token: `curl | bash` and `git clone` work anonymously, just like on GitHub.

For a **private** repository, create a read-only deploy token in its Settings and put it in the installer's clone URL: `https://deploy:<token>@gitnot.site/...`. The update step's `remote set-url` keeps it.

## 3. vs-gammon updaters

The release JSON is GitHub's, so only the feed address changes.

- **Windows** (`app/updater.py`):
  - change `FEED` to `$GIT/api/v1/repos/ruolez/vs-gammon/releases?per_page=30`;
  - verified: the current updater, pointed at git-Not with `VSG_UPDATE_FEED`, finds the newest `-windows` release, downloads it, and the Ed25519 signature checks out.
- **macOS** (`packaging/macos/shell/Updater.swift`):
  - change the URL to `$GIT/api/v1/repos/ruolez/vs-gammon/releases/latest`;
  - a 404 still means "no update".
- **Publishing**: `packaging/macos/release.sh` and the Windows steps upload by hand today. Use the CLI instead:
  - `gitnot release create ruolez/vs-gammon v1.7.0 dist/release/VS-Gammon-1.7.0.zip*` for the Mac build;
  - `gitnot release create ruolez/vs-gammon v1.7.0-windows dist/release/*windows* --latest=false` for the Windows builds.

Apps already installed check the old GitHub feed until they update once. Keep publishing to GitHub (the push mirror covers the code, not releases) for one release cycle, or ship the new feed URL first.
