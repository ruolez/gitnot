CREATE TABLE ssh_keys (
    id           BIGSERIAL PRIMARY KEY,
    user_id      BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title        TEXT NOT NULL,
    key_type     TEXT NOT NULL,
    key_blob     TEXT NOT NULL,
    fingerprint  TEXT NOT NULL UNIQUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at TIMESTAMPTZ
);
CREATE INDEX ssh_keys_user ON ssh_keys (user_id);
