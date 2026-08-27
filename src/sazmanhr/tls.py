"""TLS certificate generation and fingerprint helpers."""

from __future__ import annotations

import datetime as dt
import hashlib
import ipaddress
import socket
import ssl
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def certificate_fingerprint(cert_der: bytes) -> str:
    raw = hashlib.sha256(cert_der).hexdigest().upper()
    return ":".join(raw[i:i + 2] for i in range(0, len(raw), 2))


def pem_fingerprint(cert_path: Path) -> str:
    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    return certificate_fingerprint(cert.public_bytes(serialization.Encoding.DER))


def ensure_self_signed_certificate(data_dir: Path, hostnames: list[str] | None = None) -> tuple[Path, Path, str]:
    tls_dir = data_dir / "tls"
    tls_dir.mkdir(parents=True, exist_ok=True)
    cert_path, key_path = tls_dir / "server.crt", tls_dir / "server.key"
    if cert_path.exists() and key_path.exists():
        fingerprint = pem_fingerprint(cert_path)
        (tls_dir / "fingerprint.txt").write_text(fingerprint + "\n", encoding="ascii")
        return cert_path, key_path, fingerprint
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    names = {"localhost", socket.gethostname(), *(hostnames or [])}
    san: list[x509.GeneralName] = [x509.DNSName(name) for name in sorted(names) if name]
    san.extend([x509.IPAddress(ipaddress.ip_address(value)) for value in ("127.0.0.1", "::1")])
    now = dt.datetime.now(dt.timezone.utc)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "SazmanHR Internal"),
        x509.NameAttribute(NameOID.COMMON_NAME, socket.gethostname() or "SazmanHR Server"),
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
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ))
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    try:
        key_path.chmod(0o600)
    except OSError:
        pass
    fingerprint = pem_fingerprint(cert_path)
    (tls_dir / "fingerprint.txt").write_text(fingerprint + "\n", encoding="ascii")
    return cert_path, key_path, fingerprint


def remote_fingerprint(host: str, port: int, timeout: float = 8.0) -> str:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with socket.create_connection((host, port), timeout=timeout) as raw:
        with context.wrap_socket(raw, server_hostname=host) as wrapped:
            return certificate_fingerprint(wrapped.getpeercert(binary_form=True))

