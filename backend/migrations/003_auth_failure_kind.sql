-- Password sign-ins and token checks are throttled separately: a script with a
-- stale token must not lock people out of signing in from the same address.
ALTER TABLE auth_failures ADD COLUMN kind TEXT NOT NULL DEFAULT 'login';
DROP INDEX auth_failures_ip_at;
CREATE INDEX auth_failures_kind_ip_at ON auth_failures (kind, ip, at);
