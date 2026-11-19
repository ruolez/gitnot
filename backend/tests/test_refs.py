import unittest

from refs import clean_path, split_ref_path

BRANCHES = ["main", "feature", "feature/login", "feature/login/v2", "release/1.0"]
TAGS = ["v1.0.0", "release"]


class TestSplitRefPath(unittest.TestCase):
    def test_cases(self):
        cases = [
            (["main"], ("main", "branch", "")),
            (["main", "src", "app.py"], ("main", "branch", "src/app.py")),
            (["feature", "login", "src"], ("feature/login", "branch", "src")),
            (["feature", "login", "v2", "x"], ("feature/login/v2", "branch", "x")),
            (["feature", "other"], ("feature", "branch", "other")),
            (["v1.0.0", "install.sh"], ("v1.0.0", "tag", "install.sh")),
            (["release", "1.0", "a"], ("release/1.0", "branch", "a")),
            (["release", "notes.md"], ("release", "tag", "notes.md")),
            (["refs", "heads", "main", "install.sh"], ("main", "branch", "install.sh")),
            (["refs", "heads", "feature", "login", "f"], ("feature/login", "branch", "f")),
            (["refs", "tags", "v1.0.0", "f"], ("v1.0.0", "tag", "f")),
            (["abc1234", "src"], ("abc1234", "commit", "src")),
            (["0123456789abcdef0123456789abcdef01234567"], ("0123456789abcdef0123456789abcdef01234567", "commit", "")),
        ]
        for segs, want in cases:
            with self.subTest(segs=segs):
                self.assertEqual(split_ref_path(segs, BRANCHES, TAGS), want)

    def test_unknown(self):
        for segs in ([], ["nope"], ["refs", "heads", "nope", "x"], ["refs", "tags"], ["ABC1234"], ["abc"]):
            with self.subTest(segs=segs):
                self.assertIsNone(split_ref_path(segs, BRANCHES, TAGS))

    def test_longest_branch_wins_for_any_prefix_order(self):
        names = ["a", "a/b", "a/b/c"]
        for order in (names, list(reversed(names))):
            self.assertEqual(split_ref_path(["a", "b", "c", "d"], order, []), ("a/b/c", "branch", "d"))


class TestCleanPath(unittest.TestCase):
    def test_cases(self):
        cases = {"": "", "/": "", "src/": "src", "/src//app.py": "src/app.py", "./a/./b": "a/b",
                 "../etc": None, "a/../b": None, "a\0b": None}
        for raw, want in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(clean_path(raw), want)


if __name__ == "__main__":
    unittest.main()
