import unittest

from credentials import ANONYMOUS, Principal, session_principal
from git_auth import Decision, decide, error_advertisement, parse_git_request
from permissions import repo_access

OWNER = {"id": 1, "username": "alice", "is_admin": False}
OTHER = {"id": 2, "username": "bob", "is_admin": False}
ADMIN = {"id": 3, "username": "root", "is_admin": True}


def repo(**kw):
    base = {"id": 10, "owner_id": 1, "name": "app", "is_private": False, "archived": False}
    base.update(kw)
    return base


def personal(user, access):
    return Principal(user=user, access=access, kind="personal", token_id=1)


def deploy(repo_id, access):
    return Principal(user=None, access=access, kind="deploy", token_id=2, deploy_repo_id=repo_id)


class TestParseGitRequest(unittest.TestCase):
    def test_smart_http_endpoints(self):
        cases = {
            "/alice/app.git/info/refs?service=git-upload-pack": ("alice", "app", "git-upload-pack", "info/refs"),
            "/alice/app/info/refs?service=git-receive-pack": ("alice", "app", "git-receive-pack", "info/refs"),
            "/alice/app.git/git-upload-pack": ("alice", "app", "git-upload-pack", "git-upload-pack"),
            "/alice/my.app/git-receive-pack": ("alice", "my.app", "git-receive-pack", "git-receive-pack"),
        }
        for uri, want in cases.items():
            with self.subTest(uri=uri):
                r = parse_git_request(uri)
                self.assertEqual((r.owner, r.repo, r.service, r.endpoint), want)

    def test_rejects_non_git_and_dumb_requests(self):
        for uri in ("/alice/app", "/alice/app.git/info/refs", "/alice/app.git/HEAD",
                    "/alice/app.git/info/refs?service=git-upload-archive", "/a/b/c/git-upload-pack",
                    "/alice/app.git/objects/info/packs"):
            with self.subTest(uri=uri):
                self.assertIsNone(parse_git_request(uri))

    def test_receive_pack_is_a_write(self):
        self.assertTrue(parse_git_request("/a/b/info/refs?service=git-receive-pack").write)
        self.assertFalse(parse_git_request("/a/b/git-upload-pack").write)


class TestRepoAccess(unittest.TestCase):
    def test_levels(self):
        cases = [
            ("owner session", repo(), session_principal(OWNER), None, "admin"),
            ("site admin on private", repo(is_private=True), session_principal(ADMIN), None, "admin"),
            ("stranger on public", repo(), session_principal(OTHER), None, "read"),
            ("stranger on private", repo(is_private=True), session_principal(OTHER), None, "none"),
            ("collaborator write", repo(is_private=True), session_principal(OTHER), "write", "write"),
            ("anonymous public", repo(), ANONYMOUS, None, "read"),
            ("anonymous private", repo(is_private=True), ANONYMOUS, None, "none"),
            ("read token caps owner", repo(), personal(OWNER, "read"), None, "read"),
            ("write token keeps write", repo(), personal(OTHER, "write"), "admin", "write"),
            ("deploy read own repo", repo(is_private=True), deploy(10, "read"), None, "read"),
            ("deploy write own repo", repo(is_private=True), deploy(10, "write"), None, "write"),
            ("deploy other private repo", repo(is_private=True), deploy(99, "write"), None, "none"),
            ("deploy other public repo", repo(), deploy(99, "write"), None, "read"),
            ("unknown role ignored", repo(is_private=True), session_principal(OTHER), "owner", "none"),
        ]
        for label, r, p, role, want in cases:
            with self.subTest(label):
                self.assertEqual(repo_access(r, p, role), want)


class TestDecide(unittest.TestCase):
    read = parse_git_request("/alice/app.git/git-upload-pack")
    write = parse_git_request("/alice/app.git/git-receive-pack")

    def test_table(self):
        cases = [
            ("anon reads public", self.read, repo(), "read", False, 200),
            ("anon reads private: prompt", self.read, repo(is_private=True), "none", False, 401),
            ("anon reads missing: prompt", self.read, None, "none", False, 401),
            ("signed-in reads missing", self.read, None, "none", True, 403),
            ("signed-in reads hidden private", self.read, repo(is_private=True), "none", True, 403),
            ("anon pushes public: prompt", self.write, repo(), "read", False, 401),
            ("reader pushes", self.write, repo(), "read", True, 403),
            ("writer pushes", self.write, repo(), "write", True, 200),
            ("admin pushes archived", self.write, repo(archived=True), "admin", True, 403),
            ("reads archived", self.read, repo(archived=True), "read", False, 200),
        ]
        for label, req, r, level, creds, want in cases:
            with self.subTest(label):
                self.assertEqual(decide(req, r, level, creds).status, want)

    def test_messages_name_the_problem(self):
        self.assertEqual(decide(self.read, None, "none", True), Decision(403, "Repository not found"))
        self.assertEqual(decide(self.write, repo(), "read", True),
                         Decision(403, "Write access to alice/app denied"))


class TestErrorAdvertisement(unittest.TestCase):
    def test_pkt_lines(self):
        self.assertEqual(
            error_advertisement("git-upload-pack", "Repository not found"),
            b"001e# service=git-upload-pack\n" b"0000" b"001cERR Repository not found",
        )


if __name__ == "__main__":
    unittest.main()
