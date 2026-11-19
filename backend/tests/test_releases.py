import unittest
from datetime import datetime, timezone

from releases import asset_name_error, pick_latest, release_json, tag_name_error


def at(day):
    return datetime(2026, 1, day, tzinfo=timezone.utc)


def rel(id_, day, draft=False, pre=False, latest=True, published=True):
    return {"id": id_, "draft": draft, "prerelease": pre, "make_latest": latest,
            "published_at": at(day) if published else None}


class TestPickLatest(unittest.TestCase):
    def test_newest_eligible(self):
        releases = [rel(1, 1), rel(2, 5, pre=True), rel(3, 6, draft=True, published=False), rel(4, 3),
                    rel(5, 9, latest=False)]
        self.assertEqual(pick_latest(releases)["id"], 4)

    def test_none(self):
        self.assertIsNone(pick_latest([]))
        self.assertIsNone(pick_latest([rel(1, 1, pre=True), rel(2, 2, draft=True, published=False)]))

    def test_tie_breaks_on_id(self):
        self.assertEqual(pick_latest([rel(7, 2), rel(8, 2)])["id"], 8)


class TestNames(unittest.TestCase):
    def test_tags(self):
        for tag in ("v1.0.0", "1.6.2-windows", "release/2026.11", "v2-rc.1"):
            with self.subTest(tag=tag):
                self.assertIsNone(tag_name_error(tag))
        for tag in ("", "-v1", "v1..2", "v 1", "v1~", "v1^", "a:b", "x.lock", "a//b", "@", "v1@{u}", "/v1", "v1/",
                    ".v1", "v1.", "a\nb", "x" * 201, None):
            with self.subTest(tag=tag):
                self.assertIsNotNone(tag_name_error(tag))

    def test_assets(self):
        for name in ("VS-Gammon-1.6.2.zip", "app.zip.sig", "RemoteAgent 0.7.0.msi", "a"):
            with self.subTest(name=name):
                self.assertIsNone(asset_name_error(name))
        for name in ("", "a/b", "..", ".", "a\\b", "a\nb", "x" * 256):
            with self.subTest(name=name):
                self.assertIsNotNone(asset_name_error(name))


class TestReleaseJson(unittest.TestCase):
    def test_github_shape(self):
        r = {"id": 3, "tag_name": "v1.2.0", "target_commitish": "main", "name": "", "body": "notes", "draft": False,
             "prerelease": False, "make_latest": True, "created_at": at(1), "published_at": at(2)}
        a = {"id": 9, "name": "app.zip", "label": "", "content_type": "application/zip", "size": 10, "sha256": "ab",
             "download_count": 4, "created_at": at(2), "updated_at": at(2), "uploader": "alice"}
        out = release_json(r, [a], "https://git.example.com", "alice/app", "alice")
        self.assertEqual(out["name"], "v1.2.0")
        self.assertEqual(out["published_at"], "2026-01-02T00:00:00Z")
        self.assertEqual(out["assets"][0]["browser_download_url"],
                         "https://git.example.com/alice/app/releases/download/v1.2.0/app.zip")
        self.assertEqual(out["assets"][0]["digest"], "sha256:ab")
        self.assertEqual(out["upload_url"], "https://git.example.com/api/v1/repos/alice/app/releases/3/assets{?name,label}")


if __name__ == "__main__":
    unittest.main()
