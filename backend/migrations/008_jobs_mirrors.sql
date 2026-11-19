-- Background work done by the worker container: imports and push mirrors.
CREATE TABLE jobs (
    id          BIGSERIAL PRIMARY KEY,
    kind        TEXT NOT NULL CHECK (kind IN ('import', 'mirror')),
    repo_id     BIGINT NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    status      TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'failed')),
    payload     JSONB NOT NULL DEFAULT '{}'::jsonb,
    progress    TEXT NOT NULL DEFAULT '',
    message     TEXT NOT NULL DEFAULT '',
    created_by  BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at  TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);
CREATE INDEX jobs_queue ON jobs (status, id);
CREATE INDEX jobs_repo ON jobs (repo_id, id DESC);

-- After every push, branches and tags are pushed on to this remote (e.g. GitHub as a backup).
CREATE TABLE push_mirrors (
    repo_id     BIGINT PRIMARY KEY REFERENCES repos(id) ON DELETE CASCADE,
    url         TEXT NOT NULL,
    username    TEXT NOT NULL DEFAULT 'x-access-token',
    token       TEXT NOT NULL DEFAULT '',
    enabled     BOOLEAN NOT NULL DEFAULT true,
    last_at     TIMESTAMPTZ,
    last_status TEXT NOT NULL DEFAULT '',
    last_error  TEXT NOT NULL DEFAULT ''
);
