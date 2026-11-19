"""OpenSSH public keys: parsing, validation, fingerprints, and the
commands people run over SSH (git-upload-pack 'owner/repo.git' ...)."""

import base64
import binascii
import hashlib
import re
import struct
from dataclasses import dataclass

ALLOWED_TYPES = {
    "ssh-ed25519",
    "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp521",
    "ssh-rsa",
    "sk-ssh-ed25519@openssh.com",
    "sk-ecdsa-sha2-nistp256@openssh.com",
}
MIN_RSA_BITS = 2048


class KeyError_(ValueError):
    pass


@dataclass(frozen=True)
class PublicKey:
    key_type: str
    blob: str  # base64, as in authorized_keys
    comment: str
    fingerprint: str  # SHA256:..., as `ssh-keygen -lf` and sshd's %f print it

    @property
    def line(self):
        return f"{self.key_type} {self.blob}"


def _read_string(data, offset):
    if offset + 4 > len(data):
        raise KeyError_("The key data is truncated")
    (n,) = struct.unpack(">I", data[offset:offset + 4])
    start = offset + 4
    if start + n > len(data):
        raise KeyError_("The key data is truncated")
    return data[start:start + n], start + n


def fingerprint(blob_bytes):
    return "SHA256:" + base64.b64encode(hashlib.sha256(blob_bytes).digest()).decode().rstrip("=")


def parse_public_key(text):
    """PublicKey from one authorized_keys style line; raises KeyError_ with
    a message fit to show the user."""
    line = (text or "").strip()
    if "PRIVATE KEY" in line:
        raise KeyError_("That is a private key. Paste the .pub file instead, and keep the private key secret.")
    lines = [l for l in line.splitlines() if l.strip() and not l.strip().startswith("#")]
    if len(lines) != 1:
        raise KeyError_("Paste exactly one public key (the contents of a .pub file)")
    parts = lines[0].split(None, 2)
    if len(parts) < 2:
        raise KeyError_("A public key looks like: ssh-ed25519 AAAA… you@laptop")
    key_type, blob = parts[0], parts[1]
    comment = parts[2].strip() if len(parts) > 2 else ""
    if key_type not in ALLOWED_TYPES:
        if key_type == "ssh-dss":
            raise KeyError_("DSA keys are no longer supported; create an ed25519 key")
        raise KeyError_(f"Unsupported key type {key_type!r}")
    try:
        data = base64.b64decode(blob, validate=True)
    except (binascii.Error, ValueError):
        raise KeyError_("The key data is not valid base64") from None
    inner, offset = _read_string(data, 0)
    if inner.decode("ascii", "replace") != key_type:
        raise KeyError_("The key data does not match its type")
    if key_type == "ssh-rsa":
        _exponent, offset = _read_string(data, offset)
        modulus, offset = _read_string(data, offset)
        bits = int.from_bytes(modulus, "big").bit_length()
        if bits < MIN_RSA_BITS:
            raise KeyError_(f"RSA keys need at least {MIN_RSA_BITS} bits (this one has {bits})")
    return PublicKey(key_type=key_type, blob=blob, comment=comment[:200], fingerprint=fingerprint(data))


_COMMAND = re.compile(r"^(git-upload-pack|git-receive-pack|git-upload-archive|git upload-pack|git receive-pack|"
                      r"git upload-archive) +'?([^'\s]+?)'?$")
_PATH = re.compile(r"^/?~?/?([A-Za-z0-9-]+)/([A-Za-z0-9._-]+?)(?:\.git)?/?$")


@dataclass(frozen=True)
class SshCommand:
    service: str  # git-upload-pack | git-receive-pack | git-upload-archive
    owner: str
    repo: str

    @property
    def write(self):
        return self.service == "git-receive-pack"


def parse_ssh_command(command):
    """SshCommand for SSH_ORIGINAL_COMMAND, or None for anything else
    (shells, scp, other programs, odd paths)."""
    if not command or "\n" in command or "\0" in command:
        return None
    m = _COMMAND.match(command.strip())
    if not m:
        return None
    service = m.group(1).replace(" ", "-")
    p = _PATH.match(m.group(2))
    if not p or ".." in p.group(2) or p.group(2).startswith("."):
        return None
    return SshCommand(service=service, owner=p.group(1), repo=p.group(2))
