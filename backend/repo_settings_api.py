"""Repository settings: general, rename/transfer, collaborators, protected
branches and tags, deploy tokens."""

from flask import Blueprint, g, jsonify

import credentials
import db
import gitcmd
import repos
from auth import login_required, session_required
from names import repo_name_error
from repos_api import load_repo, repo_json
from tokens_api import mint_row, token_json
from util import api_error, audit, body

bp = Blueprint("repo_settings", __name__, url_prefix="/api/repos/<owner>/<name>")


def _full(repo):
    return f"{repo['owner']}/{repo['name']}"


@bp.patch("")
@login_required
def update_repo(owner, name):
    found, err = load_repo(owner, name, "admin")
    if err:
        return err
    repo, level = found
    data = body()
    fields = {}
    if "description" in data:
        fields["description"] = str(data["description"] or "")[:500]
    if "private" in data:
        fields["is_private"] = bool(data["private"])
    if "archived" in data:
        fields["archived"] = bool(data["archived"])
    if "default_branch" in data:
        branch = str(data["default_branch"] or "")
        if not repo["is_empty"] and not gitcmd.ref_exists(repo["id"], f"refs/heads/{branch}"):
            return api_error(f"There is no branch {branch!r}")
        if gitcmd.run(None, ["check-ref-format", "--branch", branch], check=False).strip() != branch.encode() \
                or branch.startswith("-"):
            return api_error("That is not a valid branch name")
        fields["default_branch"] = branch
    new_name = None
    if "name" in data and data["name"] != repo["name"]:
        new_name = str(data["name"] or "").strip()
        err = repo_name_error(new_name)
        if err:
            return api_error(err)
        clash = repos.find(repo["owner"], new_name)
        if clash and clash["id"] != repo["id"]:
            return api_error(f"{repo['owner']}/{new_name} already exists", 409)
        fields["name"] = new_name
    if not fields:
        return jsonify(repo_json(repo, level))
    with db.transaction():
        if new_name:
            repos.add_redirect(repo["owner"], repo["name"], repo["id"])
            repos.clear_redirect(repo["owner"], new_name)
        sets = ", ".join(f"{k} = %s" for k in fields)
        db.execute(f"UPDATE repos SET {sets}, updated_at = now() WHERE id = %s", (*fields.values(), repo["id"]))
        if "default_branch" in fields:
            gitcmd.set_head(repo["id"], fields["default_branch"])
    audit("repo.updated", {"repo": _full(repo), "fields": sorted(fields)})
    return jsonify(repo_json(repos.get(repo["id"]), level))


@bp.post("/transfer")
@session_required
def transfer(owner, name):
    found, err = load_repo(owner, name, "admin")
    if err:
        return err
    repo, _level = found
    target = db.query("SELECT * FROM users WHERE lower(username) = lower(%s) AND is_active",
                      (str(body().get("new_owner") or ""),), one=True)
    if not target:
        return api_error("No such user", 404)
    if target["id"] == repo["owner_id"]:
        return api_error("They already own it")
    if repos.find(target["username"], repo["name"]):
        return api_error(f"{target['username']} already has a repository called {repo['name']}", 409)
    with db.transaction():
        repos.add_redirect(repo["owner"], repo["name"], repo["id"])
        repos.clear_redirect(target["username"], repo["name"])
        db.execute("UPDATE repos SET owner_id = %s, updated_at = now() WHERE id = %s", (target["id"], repo["id"]))
        # The old owner keeps working on it as an admin collaborator.
        db.execute("DELETE FROM collaborators WHERE repo_id = %s AND user_id = %s", (repo["id"], target["id"]))
        db.execute(
            """INSERT INTO collaborators (repo_id, user_id, role) VALUES (%s, %s, 'admin')
               ON CONFLICT (repo_id, user_id) DO UPDATE SET role = 'admin'""",
            (repo["id"], repo["owner_id"]),
        )
    audit("repo.transferred", {"repo": _full(repo), "to": target["username"]})
    return jsonify(repo_json(repos.get(repo["id"]), "admin"))


# ---------- collaborators ----------

@bp.get("/collaborators")
@login_required
def list_collaborators(owner, name):
    found, err = load_repo(owner, name, "admin")
    if err:
        return err
    repo, _ = found
    rows = db.query(
        """SELECT u.username, u.full_name, c.role, c.created_at FROM collaborators c
           JOIN users u ON u.id = c.user_id WHERE c.repo_id = %s ORDER BY lower(u.username)""",
        (repo["id"],),
    )
    return jsonify([{**r, "created_at": r["created_at"].isoformat()} for r in rows])


@bp.put("/collaborators/<username>")
@session_required
def put_collaborator(owner, name, username):
    found, err = load_repo(owner, name, "admin")
    if err:
        return err
    repo, _ = found
    role = body().get("role", "write")
    if role not in ("read", "write", "admin"):
        return api_error("Role must be read, write or admin")
    user = db.query("SELECT * FROM users WHERE lower(username) = lower(%s) AND is_active", (username,), one=True)
    if not user:
        return api_error("No such user", 404)
    if user["id"] == repo["owner_id"]:
        return api_error("The owner already has full access")
    db.execute(
        """INSERT INTO collaborators (repo_id, user_id, role) VALUES (%s, %s, %s)
           ON CONFLICT (repo_id, user_id) DO UPDATE SET role = EXCLUDED.role""",
        (repo["id"], user["id"], role),
    )
    audit("collaborator.set", {"repo": _full(repo), "user": user["username"], "role": role})
    return jsonify({"username": user["username"], "full_name": user["full_name"], "role": role})


@bp.delete("/collaborators/<username>")
@session_required
def delete_collaborator(owner, name, username):
    found, err = load_repo(owner, name, "admin")
    if err:
        return err
    repo, _ = found
    row = db.execute(
        """DELETE FROM collaborators c USING users u
           WHERE c.user_id = u.id AND c.repo_id = %s AND lower(u.username) = lower(%s) RETURNING u.username""",
        (repo["id"], username), returning=True,
    )
    if not row:
        return api_error("Not a collaborator", 404)
    audit("collaborator.removed", {"repo": _full(repo), "user": row["username"]})
    return jsonify({"ok": True})


# ---------- protected branches and tags ----------

def _rule_json(r):
    return {k: r[k] for k in ("id", "kind", "pattern", "allow_force_push", "allow_delete", "min_push_role")}


@bp.get("/protection")
@login_required
def list_rules(owner, name):
    found, err = load_repo(owner, name)
    if err:
        return err
    repo, _ = found
    rows = db.query("SELECT * FROM protected_refs WHERE repo_id = %s ORDER BY kind, pattern", (repo["id"],))
    return jsonify([_rule_json(r) for r in rows])


@bp.post("/protection")
@session_required
def add_rule(owner, name):
    found, err = load_repo(owner, name, "admin")
    if err:
        return err
    repo, _ = found
    data = body()
    kind = data.get("kind", "branch")
    pattern = str(data.get("pattern") or "").strip()
    if kind not in ("branch", "tag"):
        return api_error("kind must be branch or tag")
    if not pattern or len(pattern) > 200 or any(c in pattern for c in " \t\n~^:\\"):
        return api_error("Give a branch or tag name, or a pattern like release/* or v*")
    role = data.get("min_push_role", "write")
    if role not in ("write", "admin"):
        return api_error("min_push_role must be write or admin")
    if db.query("SELECT 1 FROM protected_refs WHERE repo_id = %s AND kind = %s AND pattern = %s",
                (repo["id"], kind, pattern), one=True):
        return api_error("There is already a rule for that", 409)
    row = db.execute(
        """INSERT INTO protected_refs (repo_id, kind, pattern, allow_force_push, allow_delete, min_push_role)
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING *""",
        (repo["id"], kind, pattern, bool(data.get("allow_force_push")), bool(data.get("allow_delete")), role),
        returning=True,
    )
    audit("protection.added", {"repo": _full(repo), "kind": kind, "pattern": pattern})
    return jsonify(_rule_json(row)), 201


@bp.delete("/protection/<int:rule_id>")
@session_required
def delete_rule(owner, name, rule_id):
    found, err = load_repo(owner, name, "admin")
    if err:
        return err
    repo, _ = found
    row = db.execute("DELETE FROM protected_refs WHERE id = %s AND repo_id = %s RETURNING kind, pattern",
                     (rule_id, repo["id"]), returning=True)
    if not row:
        return api_error("No such rule", 404)
    audit("protection.removed", {"repo": _full(repo), **row})
    return jsonify({"ok": True})


# ---------- deploy tokens ----------

@bp.get("/deploy-tokens")
@session_required
def list_deploy_tokens(owner, name):
    found, err = load_repo(owner, name, "admin")
    if err:
        return err
    repo, _ = found
    rows = db.query("SELECT * FROM deploy_tokens WHERE repo_id = %s ORDER BY created_at DESC", (repo["id"],))
    return jsonify([token_json(r) for r in rows])


@bp.post("/deploy-tokens")
@session_required
def create_deploy_token(owner, name):
    found, err = load_repo(owner, name, "admin")
    if err:
        return err
    repo, _ = found
    data = body()
    try:
        row, token = mint_row("deploy_tokens", "repo_id", repo["id"], data.get("name"), data.get("access", "read"),
                              data.get("expires_days"), credentials.DEPLOY_PREFIX, {"created_by": g.user["id"]})
    except ValueError as e:
        return api_error(str(e))
    audit("deploy_token.created", {"repo": _full(repo), "name": row["name"], "access": row["access"]})
    return jsonify({**token_json(row), "token": token}), 201


@bp.delete("/deploy-tokens/<int:token_id>")
@session_required
def delete_deploy_token(owner, name, token_id):
    found, err = load_repo(owner, name, "admin")
    if err:
        return err
    repo, _ = found
    row = db.execute("DELETE FROM deploy_tokens WHERE id = %s AND repo_id = %s RETURNING name",
                     (token_id, repo["id"]), returning=True)
    if not row:
        return api_error("No such token", 404)
    audit("deploy_token.deleted", {"repo": _full(repo), "name": row["name"]})
    return jsonify({"ok": True})
