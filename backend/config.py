import os

SECRET_KEY = os.environ["SECRET_KEY"]
INTERNAL_TOKEN = os.environ["INTERNAL_TOKEN"]
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_INITIAL_PASSWORD = os.environ.get("ADMIN_INITIAL_PASSWORD", "admin")

POSTGRES = {
    "host": os.environ.get("POSTGRES_HOST", "postgres"),
    "dbname": os.environ.get("POSTGRES_DB", "mygit"),
    "user": os.environ.get("POSTGRES_USER", "mygit"),
    "password": os.environ["POSTGRES_PASSWORD"],
}

REPOS_DIR = os.environ.get("REPOS_DIR", "/data/repos")
RELEASES_DIR = os.environ.get("RELEASES_DIR", "/data/releases")

# Public address of the site, used in clone URLs and API links. Empty = take it
# from the request (X-Forwarded-Proto + Host).
PUBLIC_URL = os.environ.get("PUBLIC_URL", "").rstrip("/")
SSH_HOST = os.environ.get("SSH_HOST", "")
SSH_PORT = int(os.environ.get("SSH_PORT", "2222"))

# Sign-in throttling: this many failures per address inside the window.
AUTH_FAILURE_LIMIT = int(os.environ.get("AUTH_FAILURE_LIMIT", "20"))
AUTH_FAILURE_WINDOW_MIN = int(os.environ.get("AUTH_FAILURE_WINDOW_MIN", "15"))
