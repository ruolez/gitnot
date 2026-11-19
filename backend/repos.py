"""Repository rows + their bare git directories."""

import os
import shutil
import time

import config
import db
import gitcmd
from credentials import ANONYMOUS
from permissions import repo_access

REPO_COLUMNS = "r.*, u.username AS owner"


def find(owner, name):
    """The repository `owner/name` (case-insensitive), or None."""
    return db.query(
        f"""SELECT {REPO_COLUMNS} FROM repos r JOIN users u ON u.id = r.owner_id
            WHERE lower(u.username) = lower(%s) AND lower(r.name) = lower(%s)""",
        (owner, name),
        one=True,
    )


def find_redirect(owner, name):
    """The repository that used to be called owner/name, or None."""
    row = db.query(
        "SELECT repo_id FROM repo_redirects WHERE lower(owner) = lower(%s) AND lower(name) = lower(%s)",
        (owner, name),
        one=True,
    )
    return get(row["repo_id"]) if row else None


def resolve(owner, name):
    """find(), falling back to redirects of renamed repositories."""
    return find(owner, name) or find_redirect(owner, name)


def get(repo_id):
    return db.query(
        f"SELECT {REPO_COLUMNS} FROM repos r JOIN users u ON u.id = r.owner_id WHERE r.id = %s",
        (repo_id,),
        one=True,
    )


def collaborator_role(repo_id, user):
    if not user:
        return None
    row = db.query(
        "SELECT role FROM collaborators WHERE repo_id = %s AND user_id = %s", (repo_id, user["id"]), one=True
    )
    return row["role"] if row else None


def access_for(repo, principal):
    if repo is None:
        return "none"
    return repo_access(repo, principal or ANONYMOUS, collaborator_role(repo["id"], principal.user if principal else None))


def add_redirect(owner, name, repo_id):
    """Old address owner/name keeps leading to repo_id."""
    db.execute(
        """INSERT INTO repo_redirects (owner, name, repo_id) VALUES (%s, %s, %s)
           ON CONFLICT ((lower(owner)), (lower(name))) DO UPDATE SET repo_id = EXCLUDED.repo_id""",
        (owner, name, repo_id),
    )


def clear_redirect(owner, name):
    db.execute("DELETE FROM repo_redirects WHERE lower(owner) = lower(%s) AND lower(name) = lower(%s)", (owner, name))


def create(owner_id, name, description="", is_private=False, default_branch="main"):
    owner = db.query("SELECT username FROM users WHERE id = %s", (owner_id,), one=True)
    with db.transaction():
        clear_redirect(owner["username"], name)
        row = db.execute(
            """INSERT INTO repos (owner_id, name, description, is_private, default_branch)
               VALUES (%s, %s, %s, %s, %s) RETURNING id""",
            (owner_id, name, description, is_private, default_branch),
            returning=True,
        )
        gitcmd.init_bare(row["id"], default_branch)
    return get(row["id"])


def trash_dir():
    path = os.path.join(config.REPOS_DIR, ".trash")
    os.makedirs(path, exist_ok=True)
    return path


def delete(repo_id):
    """Drop the row and move the git directory to .trash (purged after a week)."""
    db.execute("DELETE FROM repos WHERE id = %s", (repo_id,))
    path = gitcmd.repo_path(repo_id)
    if os.path.isdir(path):
        os.rename(path, os.path.join(trash_dir(), f"{repo_id}-{int(time.time())}.git"))
    purge_trash()


def purge_trash(max_age_s=7 * 86400):
    now = time.time()
    for name in os.listdir(trash_dir()):
        full = os.path.join(trash_dir(), name)
        if now - os.path.getmtime(full) > max_age_s:
            shutil.rmtree(full, ignore_errors=True)


def public_repo(row, level=None):
    out = {
        "id": row["id"],
        "owner": row["owner"],
        "name": row["name"],
        "full_name": f"{row['owner']}/{row['name']}",
        "description": row["description"],
        "private": row["is_private"],
        "archived": row["archived"],
        "default_branch": row["default_branch"],
        "empty": row["is_empty"],
        "size_kb": row["size_kb"],
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
        "pushed_at": row["pushed_at"].isoformat() if row["pushed_at"] else None,
    }
    if level is not None:
        out["permission"] = level
    return out
