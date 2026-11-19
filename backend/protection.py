"""Branch and tag protection, checked by the pre-receive hook and by
branch deletes on the website."""

from fnmatch import fnmatchcase

from permissions import at_least

ZERO = "0" * 40


def rule_for(rules, kind, name):
    """The first rule whose glob matches (exact names before patterns)."""
    candidates = [r for r in rules if r["kind"] == kind and fnmatchcase(name, r["pattern"])]
    candidates.sort(key=lambda r: (any(c in r["pattern"] for c in "*?["), r["pattern"]))
    return candidates[0] if candidates else None


def problems_for(repo, level, updates, rules, forced):
    """Problems (strings) with a push; empty when it may go ahead.

    updates: [{old, new, ref}]; forced: set of refs whose update is not a
    fast-forward; rules: protected_refs rows; level: the pusher's access."""
    problems = []
    default_ref = f"refs/heads/{repo['default_branch']}"
    for u in updates:
        ref, deleting = u["ref"], u["new"] == ZERO
        if ref.startswith("refs/heads/"):
            kind, name = "branch", ref[len("refs/heads/"):]
        elif ref.startswith("refs/tags/"):
            kind, name = "tag", ref[len("refs/tags/"):]
        else:
            problems.append(f"{ref}: only branches and tags can be pushed")
            continue
        if ref == default_ref and deleting:
            problems.append(f"{name}: the default branch can't be deleted; pick another default branch first")
            continue
        rule = rule_for(rules, kind, name)
        if rule is None:
            continue
        label = f"{name} is a protected {kind}"
        if not at_least(level, rule["min_push_role"]):
            problems.append(f"{label}: only repository admins can push to it")
        elif deleting:
            if not rule["allow_delete"]:
                problems.append(f"{label} and can't be deleted")
        else:
            moved = kind == "tag" and u["old"] != ZERO
            if (ref in forced or moved) and not rule["allow_force_push"]:
                problems.append(f"{label}: {'tags can not be moved' if moved else 'force pushes are not allowed'}")
    return problems


def check(repo, level, updates, is_force=None):
    import db

    rules = db.query("SELECT * FROM protected_refs WHERE repo_id = %s", (repo["id"],))
    return problems_for(repo, level, updates, rules, set(is_force or {}))
