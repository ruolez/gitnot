-- "Last commit" per entry of a directory at a commit. A commit never changes,
-- so entries stay valid until the repository is deleted.
CREATE TABLE tree_commit_cache (
    repo_id    BIGINT NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    commit_sha TEXT NOT NULL,
    path       TEXT NOT NULL,
    data       JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (repo_id, commit_sha, path)
);
