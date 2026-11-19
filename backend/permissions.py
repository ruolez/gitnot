"""What a Principal may do with a repository. Pure: callers load the rows."""

LEVELS = {"none": 0, "read": 1, "write": 2, "admin": 3}


def at_least(level, wanted):
    return LEVELS[level] >= LEVELS[wanted]


def repo_access(repo, principal, collaborator_role=None):
    """'none' | 'read' | 'write' | 'admin' for `principal` on `repo`
    (a repos row with id, owner_id, is_private, archived).

    Site admins and the owner get admin; collaborators their role; a deploy
    token its access on its own repository; anyone read on a public one.
    A token never grants more than its own access. An archived repository is
    read-only for everyone except its admins' settings changes."""
    level = "none"
    user = principal.user
    if user is not None:
        if user["is_admin"] or user["id"] == repo["owner_id"]:
            level = "admin"
        elif collaborator_role in LEVELS:
            level = collaborator_role
    elif principal.kind == "deploy" and principal.deploy_repo_id == repo["id"]:
        level = principal.access
    if not repo["is_private"] and LEVELS[level] < LEVELS["read"]:
        level = "read"
    if LEVELS[level] > LEVELS[principal.access]:
        level = principal.access
    return level


def can_push(repo, level):
    return at_least(level, "write") and not repo["archived"]
