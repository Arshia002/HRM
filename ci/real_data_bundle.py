"""Authenticated encrypted transport for the four approved HRM workbooks."""

from __future__ import annotations

import hashlib
import io
import json
import os
import secrets
import stat
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath

from cryptography.fernet import Fernet, InvalidToken


MAGIC = b"HRM-REAL-DATA-BUNDLE-V1\n"
BUNDLE_SCHEMA = 1
MAX_PLAINTEXT_BYTES = 512 * 1024 * 1024
MAX_ENCRYPTED_BYTES = MAX_PLAINTEXT_BYTES * 2
SUPPORTED_SUFFIXES = {".xls", ".xlsx", ".csv"}
REQUIRED_PROFILES = {"official", "contractor", "named_positions", "county_enrichment"}


class BundleError(RuntimeError):
    """A safe-to-log bundle validation failure."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalized_filename(name: str) -> str:
    value = unicodedata.normalize("NFKC", name).replace("ي", "ی").replace("ك", "ک")
    return "".join(character for character in value.casefold() if character.isalnum())


def source_profile(name: str) -> str:
    normalized = _normalized_filename(name)
    if "پستبانام" in normalized:
        return "named_positions"
    if "شهرستان" in normalized:
        return "county_enrichment"
    if "رسمی" in normalized:
        return "official"
    if any(token in normalized for token in ("شرکتی", "حجمی", "پیمانکاری")):
        return "contractor"
    return "unknown"


def discover_sources(input_dir: Path) -> list[Path]:
    input_dir = input_dir.resolve()
    if not input_dir.is_dir():
        raise BundleError("The approved real-data input directory does not exist.")
    sources = sorted(
        path for path in input_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    )
    if len(sources) != 4:
        raise BundleError(f"Expected exactly four approved workbook files; found {len(sources)}.")
    profiles = [source_profile(path.name) for path in sources]
    if set(profiles) != REQUIRED_PROFILES or len(set(profiles)) != len(profiles):
        raise BundleError(
            "The four approved source profiles must be official, contractor, "
            "named positions and county enrichment exactly once each."
        )
    if len({path.name.casefold() for path in sources}) != len(sources):
        raise BundleError("Approved workbook filenames must be unique.")
    return sources


def build_plaintext_archive(sources: list[Path]) -> bytes:
    if sum(source.stat().st_size for source in sources) > MAX_PLAINTEXT_BYTES:
        raise BundleError("Approved real-data source files exceed the 512 MiB safety limit.")
    files: list[dict[str, object]] = []
    raw_files: list[bytes] = []
    for source in sources:
        raw = source.read_bytes()
        raw_files.append(raw)
        files.append({
            "archive_name": f"input/{source.name}",
            "profile": source_profile(source.name),
            "bytes": len(raw),
            "sha256": sha256_bytes(raw),
        })
    manifest = {
        "bundle_schema": BUNDLE_SCHEMA,
        "product": "HRM",
        "purpose": "v0.6.0-beta.1-protected-real-data-validation",
        "file_count": len(files),
        "files": files,
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        entries: list[tuple[str, bytes]] = [
            ("manifest.json", json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")),
        ]
        entries.extend((str(item["archive_name"]), raw) for item, raw in zip(files, raw_files))
        for name, raw in entries:
            info = zipfile.ZipInfo(name)
            info.date_time = (2026, 9, 2, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o600 & 0xFFFF) << 16
            archive.writestr(info, raw, compresslevel=9)
    return output.getvalue()


def create_encrypted_bundle(input_dir: Path, bundle_path: Path, key_path: Path) -> dict[str, object]:
    sidecar = bundle_path.with_suffix(bundle_path.suffix + ".sha256")
    if bundle_path.exists() or key_path.exists() or sidecar.exists():
        raise BundleError("Refusing to overwrite an existing encrypted bundle, key or checksum.")
    sources = discover_sources(input_dir)
    plaintext = build_plaintext_archive(sources)
    if len(plaintext) > MAX_PLAINTEXT_BYTES:
        raise BundleError("Approved real-data bundle exceeds the 512 MiB safety limit.")
    key = Fernet.generate_key()
    encrypted = MAGIC + Fernet(key).encrypt(plaintext)
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    digest = sha256_bytes(encrypted)
    token = secrets.token_hex(12)
    temp_bundle = bundle_path.with_name(f".{bundle_path.name}.{token}.tmp")
    temp_sidecar = sidecar.with_name(f".{sidecar.name}.{token}.tmp")
    temp_key = key_path.with_name(f".{key_path.name}.{token}.tmp")
    try:
        temp_bundle.write_bytes(encrypted)
        temp_sidecar.write_text(f"{digest}  {bundle_path.name}\n", encoding="ascii")
        temp_key.write_bytes(key + b"\n")
        try:
            temp_key.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
        os.replace(temp_key, key_path)
        os.replace(temp_bundle, bundle_path)
        os.replace(temp_sidecar, sidecar)
    except Exception:
        for path in (temp_bundle, temp_sidecar, temp_key, bundle_path, sidecar, key_path):
            path.unlink(missing_ok=True)
        raise
    return {
        "status": "prepared",
        "bundle_schema": BUNDLE_SCHEMA,
        "encrypted_bundle_sha256": digest,
        "source_file_count": len(sources),
        "source_profiles": sorted(source_profile(path.name) for path in sources),
        "key_file": str(key_path),
    }


def key_from_environment(name: str = "HRM_REAL_DATA_KEY") -> bytes:
    value = os.environ.get(name, "").strip().encode("ascii", errors="ignore")
    if not value:
        raise BundleError(f"Required protected environment secret {name} is missing.")
    try:
        Fernet(value)
    except (ValueError, TypeError) as exc:
        raise BundleError(f"Protected environment secret {name} is not a valid Fernet key.") from exc
    return value


def decrypt_bundle(bundle_path: Path, key: bytes, destination: Path) -> dict[str, object]:
    if not bundle_path.is_file():
        raise BundleError("Encrypted real-data bundle is missing.")
    if bundle_path.stat().st_size > MAX_ENCRYPTED_BYTES:
        raise BundleError("Encrypted real-data bundle exceeds the safety limit.")
    encrypted = bundle_path.read_bytes()
    if not encrypted.startswith(MAGIC):
        raise BundleError("Encrypted real-data bundle magic/schema is invalid.")
    sidecar = bundle_path.with_suffix(bundle_path.suffix + ".sha256")
    if not sidecar.is_file():
        raise BundleError("Encrypted real-data checksum sidecar is missing.")
    fields = sidecar.read_text(encoding="ascii").strip().split()
    if not fields or len(fields[0]) != 64:
        raise BundleError("Encrypted real-data checksum sidecar is invalid.")
    expected = fields[0].lower()
    actual = sha256_bytes(encrypted)
    if expected != actual:
        raise BundleError("Encrypted real-data bundle SHA-256 does not match its sidecar.")
    try:
        plaintext = Fernet(key).decrypt(encrypted[len(MAGIC):])
    except InvalidToken as exc:
        raise BundleError("Encrypted real-data bundle authentication failed.") from exc
    if len(plaintext) > MAX_PLAINTEXT_BYTES:
        raise BundleError("Decrypted real-data bundle exceeds the 512 MiB safety limit.")

    destination.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(io.BytesIO(plaintext), "r") as archive:
        infos = archive.infolist()
        if sum(info.file_size for info in infos) > MAX_PLAINTEXT_BYTES:
            raise BundleError("Real-data archive expansion exceeds the safety limit.")
        names = [info.filename for info in infos]
        if len(names) != len(set(names)) or len(names) != len({name.casefold() for name in names}):
            raise BundleError("Real-data archive contains duplicate paths.")
        for info in infos:
            pure = PurePosixPath(info.filename)
            if pure.is_absolute() or ".." in pure.parts or "\\" in info.filename or info.is_dir():
                raise BundleError("Real-data archive contains an unsafe path.")
        if "manifest.json" not in names:
            raise BundleError("Encrypted real-data manifest is missing.")
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        items = manifest.get("files")
        if manifest.get("bundle_schema") != BUNDLE_SCHEMA or manifest.get("file_count") != 4:
            raise BundleError("Encrypted real-data manifest contract is invalid.")
        if not isinstance(items, list) or len(items) != 4:
            raise BundleError("Encrypted real-data manifest file list is invalid.")
        expected_names = {"manifest.json"}
        expected_names.update(
            str(item.get("archive_name")) for item in items if isinstance(item, dict)
        )
        if set(names) != expected_names:
            raise BundleError("Encrypted real-data archive contains undeclared files.")
        profiles: list[str] = []
        for item in items:
            archive_name = item.get("archive_name") if isinstance(item, dict) else None
            if not isinstance(archive_name, str) or archive_name not in names:
                raise BundleError("Encrypted real-data manifest references a missing file.")
            pure = PurePosixPath(archive_name)
            if len(pure.parts) != 2 or pure.parts[0] != "input" or pure.suffix.lower() not in SUPPORTED_SUFFIXES:
                raise BundleError("Encrypted real-data manifest contains an invalid input path.")
            raw = archive.read(archive_name)
            if item.get("bytes") != len(raw) or item.get("sha256") != sha256_bytes(raw):
                raise BundleError("Encrypted real-data source hash/size validation failed.")
            profile = source_profile(pure.name)
            if item.get("profile") != profile:
                raise BundleError("Encrypted real-data source profile validation failed.")
            profiles.append(profile)
            (destination / pure.name).write_bytes(raw)
        if set(profiles) != REQUIRED_PROFILES or len(set(profiles)) != 4:
            raise BundleError("Encrypted real-data source profile set is incomplete.")
    normalized_manifest = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {
        "bundle_schema": BUNDLE_SCHEMA,
        "encrypted_bundle_sha256": actual,
        "source_manifest_sha256": sha256_bytes(normalized_manifest),
        "source_file_count": 4,
        "source_profiles": sorted(profiles),
    }
