"""TLS certificate generation for the private HRM HTTPS endpoint."""

from __future__ import annotations

import datetime as dt
import ipaddress
import socket
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def remove_legacy_tls_identity_artifacts(data_dir: Path) -> None:
    """Delete obsolete certificate-pin artifacts left by older installations."""
    legacy_pin_file = data_dir / "tls" / "fingerprint.txt"
    legacy_pin_file.unlink(missing_ok=True)

    notice = data_dir / "FIRST_LOGIN.txt"
    if notice.is_file():
        text = notice.read_text(encoding="utf-8")
        cleaned = "\n".join(
            line for line in text.splitlines()
            if not line.startswith("TLS SHA-256:")
        )
        if text.endswith("\n"):
            cleaned += "\n"
        if cleaned != text:
            notice.write_text(cleaned, encoding="utf-8")


def ensure_self_signed_certificate(
    data_dir: Path,
    hostnames: list[str] | None = None,
) -> tuple[Path, Path]:
    remove_legacy_tls_identity_artifacts(data_dir)
    tls_dir = data_dir / "tls"
    tls_dir.mkdir(parents=True, exist_ok=True)
    cert_path, key_path = tls_dir / "server.crt", tls_dir / "server.key"
    if cert_path.exists() and key_path.exists():
        return cert_path, key_path

    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    names = {"localhost", socket.gethostname(), *(hostnames or [])}
    san: list[x509.GeneralName] = [x509.DNSName(name) for name in sorted(names) if name]
    san.extend([x509.IPAddress(ipaddress.ip_address(value)) for value in ("127.0.0.1", "::1")])
    now = dt.datetime.now(dt.timezone.utc)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "HRM Internal"),
        x509.NameAttribute(NameOID.COMMON_NAME, socket.gethostname() or "HRM Server"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=825))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    try:
        key_path.chmod(0o600)
    except OSError:
        pass
    return cert_path, key_path
