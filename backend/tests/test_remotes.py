import socket
import unittest

from remotes import RemoteError, check_remote_url, git_env, github_repo, latest_flags


def resolver(address):
    return lambda host, port, proto=0: [(socket.AF_INET, socket.SOCK_STREAM, proto, "", (address, port))]


class TestCheckRemoteUrl(unittest.TestCase):
    def test_accepts_public_https(self):
        self.assertEqual(check_remote_url("https://github.com/ruolez/ispend.git#x", resolve=resolver("140.82.112.3")),
                         "https://github.com/ruolez/ispend.git")

    def test_refuses(self):
        cases = [
            ("http://github.com/a/b", "140.82.112.3", "https"),
            ("file:///data/repos/1.git", "1.1.1.1", "https"),
            ("ext::sh -c id", "1.1.1.1", "https"),
            ("https://user:tok@github.com/a/b", "140.82.112.3", "token field"),
            ("https://backend:5000/internal", "172.18.0.4", "internal"),
            ("https://localhost/a", "127.0.0.1", "internal"),
            ("https://metadata/a", "169.254.169.254", "internal"),
            ("https://lan/a", "192.168.1.10", "internal"),
            ("", "1.1.1.1", "https"),
        ]
        for url, address, needle in cases:
            with self.subTest(url=url):
                with self.assertRaises(RemoteError) as ctx:
                    check_remote_url(url, resolve=resolver(address))
                self.assertIn(needle, str(ctx.exception))

    def test_internal_allowed_when_asked(self):
        self.assertEqual(check_remote_url("https://git.lan/a", resolve=resolver("10.0.0.5"), allow_internal=True),
                         "https://git.lan/a")


class TestHelpers(unittest.TestCase):
    def test_git_env(self):
        self.assertEqual(git_env("", ""), {
            "GIT_CONFIG_COUNT": "3", "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_KEY_0": "protocol.allow", "GIT_CONFIG_VALUE_0": "never",
            "GIT_CONFIG_KEY_1": "protocol.https.allow", "GIT_CONFIG_VALUE_1": "always",
            "GIT_CONFIG_KEY_2": "credential.helper", "GIT_CONFIG_VALUE_2": "",
        })
        env = git_env(None, "tok")
        self.assertEqual((env["GIT_CONFIG_COUNT"], env["GIT_CONFIG_KEY_3"], env["GIT_CONFIG_VALUE_3"]),
                         ("4", "http.extraHeader", "Authorization: Basic eC1hY2Nlc3MtdG9rZW46dG9r"))

    def test_github_repo(self):
        self.assertEqual(github_repo("https://github.com/ruolez/vs-gammon.git"), ("ruolez", "vs-gammon"))
        self.assertEqual(github_repo("https://github.com/ruolez/ispend"), ("ruolez", "ispend"))
        self.assertIsNone(github_repo("https://gitlab.com/a/b"))
        self.assertIsNone(github_repo("https://github.com/only-owner"))

    def test_latest_flags(self):
        releases = [
            {"tag_name": "v1.6.2-windows", "published_at": "2026-11-03", "prerelease": False},
            {"tag_name": "v1.6.2", "published_at": "2026-11-02", "prerelease": False},
            {"tag_name": "v1.7.0-beta", "published_at": "2026-11-04", "prerelease": True},
            {"tag_name": "v1.6.1", "published_at": "2026-10-01", "prerelease": False},
        ]
        self.assertEqual(latest_flags(releases, "v1.6.2"),
                         {"v1.6.2-windows": False, "v1.6.2": True, "v1.7.0-beta": True, "v1.6.1": True})
        self.assertEqual(latest_flags(releases, None), {r["tag_name"]: True for r in releases})


if __name__ == "__main__":
    unittest.main()
