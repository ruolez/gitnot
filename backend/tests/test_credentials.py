import base64
import unittest

from credentials import DEPLOY_PREFIX, PERSONAL_PREFIX, looks_like_token, mint, parse_authorization, token_hash


def basic(user, password):
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


class TestMint(unittest.TestCase):
    def test_shape_and_uniqueness(self):
        tokens = {mint(PERSONAL_PREFIX) for _ in range(200)}
        self.assertEqual(len(tokens), 200)
        self.assertTrue(all(looks_like_token(t) and t.startswith("mgp_") for t in tokens))
        self.assertTrue(looks_like_token(mint(DEPLOY_PREFIX)))

    def test_hash_is_sha256_hex(self):
        self.assertEqual(token_hash("abc"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")


class TestParseAuthorization(unittest.TestCase):
    tok = mint(PERSONAL_PREFIX)

    def test_forms(self):
        cases = {
            f"Bearer {self.tok}": self.tok,
            f"token {self.tok}": self.tok,
            basic("alice", self.tok): self.tok,
            basic("deploy", self.tok): self.tok,
            basic(self.tok, ""): self.tok,
            basic(self.tok, "x-oauth-basic"): self.tok,
            basic("alice", "account-password"): "account-password",
            "": None,
            "Basic !!!": None,
            "Digest abc": None,
            "Bearer ": None,
        }
        for header, want in cases.items():
            with self.subTest(header=header):
                self.assertEqual(parse_authorization(header), want)

    def test_looks_like_token_rejects_lookalikes(self):
        for value in ("mgp_short", "xyz_" + "a" * 36, self.tok + "a", self.tok[:-1] + "!", None):
            with self.subTest(value=value):
                self.assertFalse(looks_like_token(value))


if __name__ == "__main__":
    unittest.main()
