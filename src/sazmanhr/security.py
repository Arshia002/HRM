"""Password hashing, session tokens and audit-chain helpers."""

from __future__ import annotations

import hashlib
import hmac
import base64
import re
import secrets
import struct
import time
from pathlib import Path

from cryptography.fernet import Fernet

PBKDF2_ITERATIONS = 600_000
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")


def normalize_username(value: str) -> str:
    username = value.strip().lower()
    if not USERNAME_RE.fullmatch(username):
        raise ValueError("نام کاربری باید ۳ تا ۶۴ نویسه و شامل حروف انگلیسی، عدد، نقطه، خط تیره یا زیرخط باشد.")
    return username


def validate_password(password: str) -> None:
    if len(password) < 12:
        raise ValueError("رمز عبور باید حداقل ۱۲ نویسه باشد.")
    classes = [
        any(c.islower() for c in password),
        any(c.isupper() for c in password),
        any(c.isdigit() for c in password),
        any(not c.isalnum() for c in password),
    ]
    if sum(classes) < 3:
        raise ValueError("رمز عبور باید دست‌کم سه گروه از حروف کوچک، بزرگ، عدد و نماد را داشته باشد.")


def hash_password(password: str, *, iterations: int = PBKDF2_ITERATIONS) -> str:
    validate_password(password)
    salt = secrets.token_bytes(24)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations_text, salt_hex, digest_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations_text)
        )
        return hmac.compare_digest(digest, bytes.fromhex(digest_hex))
    except (ValueError, TypeError):
        return False


def new_session_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(48)
    return raw, token_digest(raw)


def token_digest(raw: str) -> str:
    return hashlib.sha256(raw.encode("ascii")).hexdigest()


def generate_temporary_password() -> str:
    return f"Saz!{secrets.token_urlsafe(11)}9a"


def audit_digest(previous_hash: str, canonical_event: str) -> str:
    return hashlib.sha256((previous_hash + "\n" + canonical_event).encode("utf-8")).hexdigest()


class SecretBox:
    def __init__(self, key_path: Path):
        self.key_path = key_path
        key_path.parent.mkdir(parents=True, exist_ok=True)
        if key_path.exists():
            key = key_path.read_bytes().strip()
        else:
            key = Fernet.generate_key()
            key_path.write_bytes(key)
            try:
                key_path.chmod(0o600)
            except OSError:
                pass
        self._fernet = Fernet(key)

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        return self._fernet.decrypt(value.encode("ascii")).decode("utf-8")


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def totp_code(secret: str, when: int | None = None, period: int = 30) -> str:
    timestamp = int(time.time() if when is None else when)
    padded = secret.upper() + "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded)
    counter = struct.pack(">Q", timestamp // period)
    digest = hmac.new(key, counter, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{value:06d}"


def verify_totp(secret: str, code: str, when: int | None = None, window: int = 1) -> bool:
    if not re.fullmatch(r"\d{6}", code.strip()):
        return False
    timestamp = int(time.time() if when is None else when)
    return any(hmac.compare_digest(totp_code(secret, timestamp + delta * 30), code.strip())
               for delta in range(-window, window + 1))


def recovery_code() -> str:
    raw = secrets.token_hex(5).upper()
    return raw[:5] + "-" + raw[5:]
