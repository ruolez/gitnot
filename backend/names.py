import re

# Top-level paths the site owns; an account with one of these names would
# shadow a page (mygit.example/login) or a route nginx sends elsewhere.
RESERVED = frozenset({
    "about", "api", "cli", "assets", "explore", "favicon.ico", "health", "healthz",
    "help", "install", "internal", "login", "logout", "new", "raw", "robots.txt",
    "settings", "signup", "static", "users", "git", "mygit", "gitnot", "git-not", "repos", "org", "orgs",
    "_auth", "well-known", ".well-known",
})

USERNAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")
REPO_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")


def username_error(name):
    """None when `name` can be an account name, otherwise why not."""
    if not isinstance(name, str) or not USERNAME_RE.fullmatch(name):
        return "Usernames are 1-39 letters, digits or single hyphens, not starting or ending with a hyphen"
    if name.lower() in RESERVED:
        return f"'{name}' is reserved"
    return None


def repo_name_error(name):
    """None when `name` can be a repository name, otherwise why not."""
    if not isinstance(name, str) or not REPO_RE.fullmatch(name):
        return "Repository names are 1-100 letters, digits, '.', '-' or '_'"
    if name in (".", "..") or name.startswith("."):
        return "Repository names can't start with '.'"
    if name.lower().endswith(".git"):
        return "Leave '.git' off the name; it is added to clone URLs"
    return None
