import contextlib
import os

import psycopg2
import psycopg2.extras
from flask import g
from werkzeug.security import generate_password_hash

import config

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "migrations")


def connect():
    return psycopg2.connect(**config.POSTGRES)


def get_db():
    if "db" not in g:
        g.db = connect()
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def query(sql, params=None, one=False):
    conn = get_db()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        rows = cur.fetchall() if cur.description is not None else None
    if not getattr(g, "in_tx", False):
        conn.commit()
    if rows is None:
        return None
    return (rows[0] if rows else None) if one else rows


def execute(sql, params=None, returning=False):
    conn = get_db()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        row = cur.fetchone() if returning else None
    if not getattr(g, "in_tx", False):
        conn.commit()
    return row


@contextlib.contextmanager
def transaction():
    """Group query()/execute() calls into one commit; rolls back on error."""
    if getattr(g, "in_tx", False):
        yield
        return
    conn = get_db()
    g.in_tx = True
    try:
        yield
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        g.in_tx = False


def get_setting(key, default=None):
    row = query("SELECT value FROM settings WHERE key = %s", (key,), one=True)
    return row["value"] if row and row["value"] is not None else default


def set_setting(key, value):
    execute(
        """INSERT INTO settings (key, value) VALUES (%s, %s)
           ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()""",
        (key, value),
    )


def run_migrations():
    conn = connect()
    try:
        with conn.cursor() as cur:
            # One process migrates at a time (several gunicorn masters may start together).
            cur.execute("SELECT pg_advisory_lock(424242)")
            cur.execute(
                """CREATE TABLE IF NOT EXISTS schema_migrations (
                       filename TEXT PRIMARY KEY,
                       applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                   )"""
            )
            cur.execute("SELECT filename FROM schema_migrations")
            applied = {r[0] for r in cur.fetchall()}
            for fname in sorted(os.listdir(MIGRATIONS_DIR)):
                if not fname.endswith(".sql") or fname in applied:
                    continue
                with open(os.path.join(MIGRATIONS_DIR, fname)) as f:
                    cur.execute(f.read())
                cur.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (fname,))
            conn.commit()
            _seed_admin(cur)
            conn.commit()
            cur.execute("SELECT pg_advisory_unlock(424242)")
    finally:
        conn.close()


def _seed_admin(cur):
    cur.execute("SELECT COUNT(*) FROM users")
    if cur.fetchone()[0] == 0:
        cur.execute(
            "INSERT INTO users (username, password_hash, is_admin) VALUES (%s, %s, true)",
            (config.ADMIN_USERNAME, generate_password_hash(config.ADMIN_INITIAL_PASSWORD)),
        )
