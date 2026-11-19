import unittest

from gitparse import parse_diff, parse_log, parse_ls_tree

DIFF = """diff --git a/src/app.py b/src/app.py
index 1111111..2222222 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1,3 +1,4 @@ def main():
 import os
-import sys
+import sys, json
+import re
 print(1)
\\ No newline at end of file
diff --git a/new file.txt b/new file.txt
new file mode 100644
index 0000000..3333333
--- /dev/null
+++ b/new file.txt
@@ -0,0 +1 @@
+hello
diff --git a/gone.txt b/gone.txt
deleted file mode 100644
index 4444444..0000000
--- a/gone.txt
+++ /dev/null
@@ -1 +0,0 @@
-bye
diff --git a/old.md b/docs/new.md
similarity index 90%
rename from old.md
rename to docs/new.md
index 5555555..6666666 100644
--- a/old.md
+++ b/docs/new.md
@@ -2 +2 @@
-a
+b
diff --git a/logo.png b/logo.png
new file mode 100644
index 0000000..7777777
Binary files /dev/null and b/logo.png differ
diff --git a/same.txt b/same.txt
old mode 100644
new mode 100755
"""


class TestParseDiff(unittest.TestCase):
    def test_files_statuses_and_counts(self):
        result = parse_diff(DIFF)
        summary = [(f["path"], f["old_path"], f["status"], f["binary"], f["additions"], f["deletions"])
                   for f in result["files"]]
        self.assertEqual(summary, [
            ("src/app.py", None, "modified", False, 2, 1),
            ("new file.txt", None, "added", False, 1, 0),
            ("gone.txt", None, "deleted", False, 0, 1),
            ("docs/new.md", "old.md", "renamed", False, 1, 1),
            ("logo.png", None, "added", True, 0, 0),
            ("same.txt", None, "modified", False, 0, 0),
        ])
        self.assertEqual((result["additions"], result["deletions"], result["truncated"]), (4, 3, False))

    def test_line_numbers(self):
        hunk = parse_diff(DIFF)["files"][0]["hunks"][0]
        self.assertEqual(hunk["header"], "@@ -1,3 +1,4 @@ def main():")
        self.assertEqual(hunk["lines"], [
            {"t": " ", "text": "import os", "old": 1, "new": 1},
            {"t": "-", "text": "import sys", "old": 2},
            {"t": "+", "text": "import sys, json", "new": 2},
            {"t": "+", "text": "import re", "new": 3},
            {"t": " ", "text": "print(1)", "old": 3, "new": 4},
        ])

    def test_limits(self):
        big = "diff --git a/f b/f\n--- a/f\n+++ b/f\n@@ -0,0 +1,50 @@\n" + "".join(f"+{i}\n" for i in range(50))
        cut = parse_diff(big, max_file_lines=10)
        self.assertEqual((len(cut["files"][0]["hunks"][0]["lines"]), cut["files"][0]["truncated"],
                          cut["files"][0]["additions"]), (10, True, 50))
        many = "".join(f"diff --git a/f{i} b/f{i}\nnew file mode 100644\n" for i in range(5))
        self.assertEqual((len(parse_diff(many, max_files=3)["files"]), parse_diff(many, max_files=3)["truncated"]),
                         (3, True))

    def test_empty(self):
        self.assertEqual(parse_diff(""), {"files": [], "truncated": False, "additions": 0, "deletions": 0})


class TestParseLog(unittest.TestCase):
    def test_records(self):
        raw = ("a" * 40 + "\x1f" + "b" * 40 + " " + "c" * 40 + "\x1fAnn\x1fann@x.org\x1f2026-01-02T03:04:05+00:00"
               "\x1fBob\x1fbob@x.org\x1f2026-01-03T00:00:00+00:00\x1fMerge it\x1fbody line\n\n\x1e\n"
               + "d" * 40 + "\x1f\x1fA\x1fa@x\x1f2026-01-01T00:00:00Z\x1fA\x1fa@x\x1f2026-01-01T00:00:00Z\x1froot\x1f\x1e")
        commits = parse_log(raw)
        self.assertEqual([(c["sha"][0], c["parents"], c["subject"], c["body"]) for c in commits], [
            ("a", ["b" * 40, "c" * 40], "Merge it", "body line"),
            ("d", [], "root", ""),
        ])
        self.assertEqual(commits[0]["author"], {"name": "Ann", "email": "ann@x.org", "date": "2026-01-02T03:04:05+00:00"})


class TestParseLsTree(unittest.TestCase):
    def test_entries_sorted_dirs_first(self):
        raw = (b"100644 blob " + b"1" * 40 + b"     120\tsrc/zeta.py\0"
               b"040000 tree " + b"2" * 40 + b"       -\tsrc/lib\0"
               b"120000 blob " + b"3" * 40 + b"      9\tsrc/link\0"
               b"160000 commit " + b"4" * 40 + b"       -\tsrc/vendor\0"
               b"100755 blob " + b"5" * 40 + b"    3\tsrc/Alpha.sh\0")
        got = [(e["name"], e["type"], e["size"]) for e in parse_ls_tree(raw)]
        self.assertEqual(got, [("lib", "tree", None), ("vendor", "submodule", None), ("Alpha.sh", "blob", 3),
                               ("link", "symlink", 9), ("zeta.py", "blob", 120)])

    def test_without_long_sizes(self):
        raw = b"100644 blob " + b"1" * 40 + b"\ta.txt\0"
        self.assertEqual(parse_ls_tree(raw), [{"name": "a.txt", "path": "a.txt", "type": "blob", "mode": "100644",
                                               "sha": "1" * 40, "size": None}])


if __name__ == "__main__":
    unittest.main()
