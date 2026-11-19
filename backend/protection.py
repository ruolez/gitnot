"""Branch and tag protection, checked by the pre-receive hook."""

ZERO = "0" * 40


def check(repo, level, updates, is_force=None):
    """Problems (strings) with a push; empty when it may go ahead.
    updates: [{old, new, ref}]. Protected refs arrive in a later phase."""
    problems = []
    default_ref = f"refs/heads/{repo['default_branch']}"
    for u in updates:
        ref = u["ref"]
        if not (ref.startswith("refs/heads/") or ref.startswith("refs/tags/")):
            problems.append(f"{ref}: only branches and tags can be pushed")
        elif ref == default_ref and u["new"] == ZERO:
            problems.append(f"{ref}: the default branch can't be deleted; pick another default branch first")
    return problems
