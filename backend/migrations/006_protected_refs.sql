CREATE TABLE protected_refs (
    id               BIGSERIAL PRIMARY KEY,
    repo_id          BIGINT NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    kind             TEXT NOT NULL CHECK (kind IN ('branch', 'tag')),
    pattern          TEXT NOT NULL,
    allow_force_push BOOLEAN NOT NULL DEFAULT false,
    allow_delete     BOOLEAN NOT NULL DEFAULT false,
    min_push_role    TEXT NOT NULL DEFAULT 'write' CHECK (min_push_role IN ('write', 'admin')),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX protected_refs_repo_kind_pattern ON protected_refs (repo_id, kind, pattern);
