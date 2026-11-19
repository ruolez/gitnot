CREATE TABLE repos (
    id             BIGSERIAL PRIMARY KEY,
    owner_id       BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    name           TEXT NOT NULL,
    description    TEXT NOT NULL DEFAULT '',
    is_private     BOOLEAN NOT NULL DEFAULT false,
    default_branch TEXT NOT NULL DEFAULT 'main',
    archived       BOOLEAN NOT NULL DEFAULT false,
    size_kb        BIGINT NOT NULL DEFAULT 0,
    is_empty       BOOLEAN NOT NULL DEFAULT true,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    pushed_at      TIMESTAMPTZ
);
CREATE UNIQUE INDEX repos_owner_name_lower ON repos (owner_id, lower(name));

CREATE TABLE collaborators (
    repo_id    BIGINT NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role       TEXT NOT NULL CHECK (role IN ('read', 'write', 'admin')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (repo_id, user_id)
);
CREATE INDEX collaborators_user ON collaborators (user_id);

-- Personal access tokens (mgp_...) and repository deploy tokens (mgd_...).
-- Only the SHA-256 of a token is kept; `prefix` is shown so people can tell them apart.
CREATE TABLE access_tokens (
    id           BIGSERIAL PRIMARY KEY,
    user_id      BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    token_hash   TEXT NOT NULL UNIQUE,
    prefix       TEXT NOT NULL,
    access       TEXT NOT NULL CHECK (access IN ('read', 'write')),
    expires_at   TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at TIMESTAMPTZ
);
CREATE INDEX access_tokens_user ON access_tokens (user_id);

CREATE TABLE deploy_tokens (
    id           BIGSERIAL PRIMARY KEY,
    repo_id      BIGINT NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    token_hash   TEXT NOT NULL UNIQUE,
    prefix       TEXT NOT NULL,
    access       TEXT NOT NULL CHECK (access IN ('read', 'write')),
    expires_at   TIMESTAMPTZ,
    created_by   BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at TIMESTAMPTZ
);
CREATE INDEX deploy_tokens_repo ON deploy_tokens (repo_id);

CREATE TABLE push_events (
    id         BIGSERIAL PRIMARY KEY,
    repo_id    BIGINT NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    user_id    BIGINT REFERENCES users(id) ON DELETE SET NULL,
    actor      TEXT NOT NULL DEFAULT '',
    via        TEXT NOT NULL DEFAULT 'http',
    ref        TEXT NOT NULL,
    old_sha    TEXT NOT NULL,
    new_sha    TEXT NOT NULL,
    at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX push_events_repo_at ON push_events (repo_id, at DESC);
CREATE INDEX push_events_user_at ON push_events (user_id, at DESC);

-- Old owner/name pairs of renamed or transferred repositories keep working.
CREATE TABLE repo_redirects (
    owner      TEXT NOT NULL,
    name       TEXT NOT NULL,
    repo_id    BIGINT NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX repo_redirects_lower ON repo_redirects (lower(owner), lower(name));
