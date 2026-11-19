import unittest

from names import repo_name_error, username_error


class TestUsernameError(unittest.TestCase):
    def test_accepts_github_style_names(self):
        for name in ("ruolez", "a", "Team-42", "x" * 39, "a-b-c"):
            with self.subTest(name=name):
                self.assertIsNone(username_error(name))

    def test_rejects_bad_shapes(self):
        for name in ("", "-a", "a-", "a--b", "a_b", "a.b", "x" * 40, "ab\n", "a/b", "a b", None, 5):
            with self.subTest(name=name):
                self.assertIsNotNone(username_error(name))

    def test_rejects_reserved_any_case(self):
        for name in ("settings", "API", "Login", "raw", "static"):
            with self.subTest(name=name):
                self.assertIn("reserved", username_error(name))


class TestRepoNameError(unittest.TestCase):
    def test_accepts_common_names(self):
        for name in ("ispend", "vs-gammon", "my_app", "app.v2", "x" * 100):
            with self.subTest(name=name):
                self.assertIsNone(repo_name_error(name))

    def test_rejects_bad_shapes(self):
        for name in ("", ".", "..", ".hidden", "a/b", "a b", "x" * 101, "ä", "a\nb", "app\n", None):
            with self.subTest(name=name):
                self.assertIsNotNone(repo_name_error(name))

    def test_rejects_git_suffix(self):
        self.assertIn(".git", repo_name_error("app.GIT"))

    def test_site_words_are_fine_under_an_owner(self):
        self.assertIsNone(repo_name_error("settings"))


if __name__ == "__main__":
    unittest.main()
