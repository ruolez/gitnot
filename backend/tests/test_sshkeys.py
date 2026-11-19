import base64
import struct
import unittest

from sshkeys import KeyError_, parse_public_key, parse_ssh_command

# FINGERPRINT is what `ssh-keygen -lf` prints for this key.
ED25519 = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C1okWi0dh2l9GKJl test@example"
FINGERPRINT = "SHA256:yl43vwp9IXgx5iZaegOJgqVPaBIl7DUaS/dDbpKFj/E"


def ssh_string(b):
    return struct.pack(">I", len(b)) + b


def rsa_key(bits):
    modulus = (1 << (bits - 1)) | 1
    blob = ssh_string(b"ssh-rsa") + ssh_string(b"\x01\x00\x01") + ssh_string(b"\x00" + modulus.to_bytes(bits // 8, "big"))
    return "ssh-rsa " + base64.b64encode(blob).decode()


class TestParsePublicKey(unittest.TestCase):
    def test_ed25519_with_comment(self):
        key = parse_public_key(ED25519 + "\n")
        self.assertEqual((key.key_type, key.comment), ("ssh-ed25519", "test@example"))
        self.assertEqual(key.fingerprint, FINGERPRINT)

    def test_rsa_size_limit(self):
        self.assertEqual(parse_public_key(rsa_key(2048)).key_type, "ssh-rsa")
        with self.assertRaises(KeyError_) as ctx:
            parse_public_key(rsa_key(1024))
        self.assertIn("1024", str(ctx.exception))

    def test_rejections(self):
        cases = {
            "": "exactly one",
            "-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n-----END OPENSSH PRIVATE KEY-----": "private key",
            "ssh-dss AAAAB3NzaC1kc3M=": "DSA",
            "ssh-foo AAAA": "Unsupported",
            "ssh-ed25519 not*base64": "base64",
            "ssh-ed25519 " + base64.b64encode(ssh_string(b"ssh-rsa") + b"x").decode(): "does not match",
            ED25519 + "\n" + ED25519: "exactly one",
            "ssh-ed25519": "looks like",
        }
        for text, needle in cases.items():
            with self.subTest(text=text[:30]):
                with self.assertRaises(KeyError_) as ctx:
                    parse_public_key(text)
                self.assertIn(needle, str(ctx.exception))


class TestParseSshCommand(unittest.TestCase):
    def test_accepted_forms(self):
        cases = {
            "git-upload-pack 'alice/app.git'": ("git-upload-pack", "alice", "app"),
            "git-receive-pack '/alice/app.git'": ("git-receive-pack", "alice", "app"),
            "git-upload-pack 'alice/app'": ("git-upload-pack", "alice", "app"),
            "git upload-pack 'alice/my.app.git'": ("git-upload-pack", "alice", "my.app"),
            "git-upload-archive 'alice/app.git'": ("git-upload-archive", "alice", "app"),
            "git-upload-pack alice/app.git": ("git-upload-pack", "alice", "app"),
            "git-upload-pack '~/alice/app.git'": ("git-upload-pack", "alice", "app"),
        }
        for command, want in cases.items():
            with self.subTest(command=command):
                c = parse_ssh_command(command)
                self.assertEqual((c.service, c.owner, c.repo), want)

    def test_refused(self):
        for command in (
            "", "ls", "bash", "scp -t /tmp", "git-upload-pack", "git-upload-pack '../../etc/passwd'",
            "git-upload-pack '/data/repos/1.git'", "git-upload-pack 'alice/app.git'; rm -rf /",
            "git-upload-pack 'alice/app.git' && id", "git-upload-pack 'alice/../app'",
            "git-upload-pack 'alice/.hidden'", "git-upload-pack 'a/b/c'", "git-upload-pack 'alice/app\n'",
            "git-shell -c 'git-upload-pack alice/app'", "git-upload-pack 'alice/app.git' extra",
            "git-upload-pack '$(id)/app'",
        ):
            with self.subTest(command=command):
                self.assertIsNone(parse_ssh_command(command))

    def test_write_flag(self):
        self.assertTrue(parse_ssh_command("git-receive-pack 'a/b'").write)
        self.assertFalse(parse_ssh_command("git-upload-archive 'a/b'").write)


if __name__ == "__main__":
    unittest.main()
