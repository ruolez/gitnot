import unittest

from protection import ZERO, problems_for, rule_for

REPO = {"id": 1, "default_branch": "main"}
A, B = "a" * 40, "b" * 40


def rule(kind, pattern, force=False, delete=False, role="write"):
    return {"kind": kind, "pattern": pattern, "allow_force_push": force, "allow_delete": delete,
            "min_push_role": role}


def upd(ref, old=A, new=B):
    return {"ref": ref, "old": old, "new": new}


class TestRuleFor(unittest.TestCase):
    def test_exact_name_beats_pattern(self):
        rules = [rule("branch", "release/*", force=True), rule("branch", "release/1.0")]
        self.assertEqual(rule_for(rules, "branch", "release/1.0")["pattern"], "release/1.0")
        self.assertEqual(rule_for(rules, "branch", "release/2.0")["pattern"], "release/*")
        self.assertIsNone(rule_for(rules, "tag", "release/1.0"))
        self.assertIsNone(rule_for(rules, "branch", "Release/1.0"))


class TestProblemsFor(unittest.TestCase):
    rules = [rule("branch", "main"), rule("branch", "release/*", delete=True), rule("tag", "v*"),
             rule("branch", "prod", role="admin")]

    def check(self, updates, level="write", forced=()):
        return problems_for(REPO, level, updates, self.rules, set(forced))

    def test_allowed(self):
        cases = [
            [upd("refs/heads/main")],
            [upd("refs/heads/feature", old=ZERO)],
            [upd("refs/heads/feature"), upd("refs/heads/other", new=ZERO)],
            [upd("refs/heads/topic")],
            [upd("refs/tags/v1.0", old=ZERO)],
            [upd("refs/heads/release/1.0", new=ZERO)],
        ]
        for updates in cases:
            with self.subTest(updates=updates):
                self.assertEqual(self.check(updates, forced={"refs/heads/topic"}), [])

    def test_refused(self):
        cases = [
            ([upd("refs/heads/main")], "write", {"refs/heads/main"}, "main is a protected branch: force pushes are not allowed"),
            ([upd("refs/heads/main", new=ZERO)], "admin", (), "main: the default branch can't be deleted"),
            ([upd("refs/tags/v1.0")], "admin", (), "v1.0 is a protected tag: tags can not be moved"),
            ([upd("refs/tags/v1.0", new=ZERO)], "admin", (), "v1.0 is a protected tag and can't be deleted"),
            ([upd("refs/heads/prod")], "write", (), "prod is a protected branch: only repository admins can push to it"),
            ([upd("refs/notes/x")], "admin", (), "refs/notes/x: only branches and tags can be pushed"),
        ]
        for updates, level, forced, needle in cases:
            with self.subTest(needle=needle):
                got = self.check(updates, level, forced)
                self.assertEqual(len(got), 1)
                self.assertTrue(got[0].startswith(needle), got)

    def test_admin_may_push_to_admin_only_branch(self):
        self.assertEqual(self.check([upd("refs/heads/prod")], "admin"), [])

    def test_force_allowed_by_rule(self):
        rules = [rule("branch", "main", force=True)]
        self.assertEqual(problems_for(REPO, "write", [upd("refs/heads/main")], rules, {"refs/heads/main"}), [])


if __name__ == "__main__":
    unittest.main()
