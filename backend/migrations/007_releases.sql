CREATE TABLE releases (
    id               BIGSERIAL PRIMARY KEY,
    repo_id          BIGINT NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    tag_name         TEXT NOT NULL,
    target_commitish TEXT NOT NULL DEFAULT '',
    name             TEXT NOT NULL DEFAULT '',
    body             TEXT NOT NULL DEFAULT '',
    draft            BOOLEAN NOT NULL DEFAULT false,
    prerelease       BOOLEAN NOT NULL DEFAULT false,
    -- GitHub's make_latest: false keeps this release from becoming "latest".
    make_latest      BOOLEAN NOT NULL DEFAULT true,
    created_by       BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at     TIMESTAMPTZ
);
CREATE UNIQUE INDEX releases_repo_tag ON releases (repo_id, tag_name);

CREATE TABLE release_assets (
    id             BIGSERIAL PRIMARY KEY,
    release_id     BIGINT NOT NULL REFERENCES releases(id) ON DELETE CASCADE,
    name           TEXT NOT NULL,
    label          TEXT NOT NULL DEFAULT '',
    content_type   TEXT NOT NULL DEFAULT 'application/octet-stream',
    size           BIGINT NOT NULL,
    sha256         TEXT NOT NULL,
    download_count BIGINT NOT NULL DEFAULT 0,
    uploaded_by    BIGINT REFERENCES users(id) ON DELETE SET NULL,
    uploader       TEXT NOT NULL DEFAULT '',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX release_assets_release_name ON release_assets (release_id, name);
