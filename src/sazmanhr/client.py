"""Windows desktop shell for the exact SazmanHR v4.9 web UI.

The enterprise backend remains authoritative for authentication, RBAC, MFA,
audit, movements, backup and persistence.  The desktop shell intentionally
renders the server-served reference web UI instead of maintaining a divergent
native reimplementation.
"""
from __future__ import annotations

import argparse
import os
import sys
import urllib.parse
from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView

from . import __version__
from .api_client import ApiClient, ApiError
from .branding import APP_NAME, COMPANY_NAME, PRODUCT_TITLE, logo_path
from .config import ClientConfig, default_client_config
from .tls import certificate_fingerprint

REFERENCE_PAGE_IDS = (
    "formalChart", "statusChart", "personnelDirectory", "personnelEducation",
    "jobFamilies", "personnelAge", "reports", "imports", "users", "history",
    "systemHealth", "settings",
)


def _web_root() -> Path:
    candidates = [
        Path(__file__).resolve().parents[2] / "web",
        Path(getattr(sys, "_MEIPASS", "")) / "web",
    ]
    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate
    raise RuntimeError("Bundled v4.9 web reference assets are missing.")


def _verify_reference_assets() -> None:
    root = _web_root()
    required = (
        "index.html", "assets/styles.css", "assets/app.js", "assets/logo.svg",
        "assets/login-power-final.webp", "assets/modules/auth-shell.js",
        "assets/modules/enterprise-bridge.js",
    )
    missing = [relative for relative in required if not (root / relative).is_file()]
    if missing:
        raise RuntimeError(f"Missing v4.9 UI assets: {missing}")
    html = (root / "index.html").read_text(encoding="utf-8")
    absent = [page for page in REFERENCE_PAGE_IDS if page not in html]
    if absent:
        raise RuntimeError(f"v4.9 page coverage failed: {absent}")


class PinnedPage(QWebEnginePage):
    """Accept a private/self-signed TLS certificate only after API pin preflight."""

    def __init__(self, profile: QWebEngineProfile, allowed_origin: str, parent=None):
        super().__init__(profile, parent)
        parsed = urllib.parse.urlparse(allowed_origin)
        self.allowed_host = (parsed.hostname or "").lower()
        self.allowed_port = parsed.port or (443 if parsed.scheme == "https" else 80)
        self.preflight_succeeded = False
        self.allowed_fingerprint = ""
        # Qt 6 exposes certificateError as a signal, not a virtual override.
        self.certificateError.connect(self._on_certificate_error)

    @staticmethod
    def _normalize_fingerprint(value: str) -> str:
        raw = "".join(ch for ch in str(value or "").upper() if ch in "0123456789ABCDEF")
        return ":".join(raw[index:index + 2] for index in range(0, len(raw), 2))

    def _on_certificate_error(self, error) -> None:
        accept = False
        try:
            url = error.url()
            port = url.port(443 if url.scheme().lower() == "https" else 80)
            same_endpoint = url.host().lower() == self.allowed_host and port == self.allowed_port
            if self.preflight_succeeded and same_endpoint and error.isOverridable():
                chain = error.certificateChain()
                if chain:
                    actual = certificate_fingerprint(bytes(chain[0].toDer()))
                    expected = self._normalize_fingerprint(self.allowed_fingerprint)
                    accept = bool(expected) and actual == expected
        except Exception:
            accept = False
        if accept:
            error.acceptCertificate()
        else:
            error.rejectCertificate()


class EnterpriseWebWindow(QMainWindow):
    def __init__(self, config: ClientConfig, config_path: Path):
        super().__init__()
        self.config = config
        self.config_path = config_path
        self.setWindowTitle(f"{PRODUCT_TITLE} — {COMPANY_NAME}")
        self.setWindowIcon(QIcon(str(logo_path())))
        self.setMinimumSize(1180, 700)
        self.resize(1440, 900)

        self.view = QWebEngineView(self)
        profile = QWebEngineProfile.defaultProfile()
        profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies)
        self.page = PinnedPage(profile, config.server_url, self.view)
        self.view.setPage(self.page)
        self.setCentralWidget(self.view)

    def _certificate_prompt(self, fingerprint: str) -> bool:
        message = (
            "این نخستین اتصال این کلاینت به سرور HRM است.\n\n"
            "اثر انگشت TLS زیر را با FIRST_LOGIN.txt سرور مقایسه کنید:\n\n"
            f"{fingerprint}\n\n"
            "آیا این گواهی متعلق به سرور سازمان است؟"
        )
        return QMessageBox.question(
            self, "تأیید هویت سرور", message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes

    def connect_and_load(self) -> None:
        client = ApiClient(
            self.config.server_url,
            tls_fingerprint=self.config.tls_fingerprint,
            certificate_prompt=self._certificate_prompt,
        )
        health = client.health()
        if health.get("status") != "ok" or health.get("database") != "ready":
            raise ApiError("سرور HRM آماده نیست.")
        self.config.tls_fingerprint = client.tls_fingerprint
        self.config.save(self.config_path)
        self.page.allowed_fingerprint = client.tls_fingerprint
        self.page.preflight_succeeded = True
        self.view.load(QUrl(self.config.server_url.rstrip("/") + "/"))


def _parse(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HRM v4.9-compatible enterprise desktop shell")
    parser.add_argument("--server")
    parser.add_argument("--tls-fingerprint", default="")
    parser.add_argument("--config")
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--ui-smoke-test", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse(argv)
    _verify_reference_assets()

    # PyInstaller/Windows CI invokes these before Setup creation.  The first
    # proves the frozen QtWebEngine runtime imports; the second proves the exact
    # reference page inventory and bundled UI payload are present.
    if args.smoke_test:
        print(f"HRM QtWebEngine smoke test OK: {__version__}")
        return 0
    if args.ui_smoke_test:
        print(f"HRM exact v4.9 web UI smoke test OK: {__version__} ({len(REFERENCE_PAGE_IDS)} pages)")
        return 0

    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-features=Translate")
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName("HRM")
    app.setApplicationVersion(__version__)
    app.setWindowIcon(QIcon(str(logo_path())))
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

    config_path = default_client_config() if not args.config else Path(args.config)
    config = ClientConfig.load(config_path)
    if args.server:
        config.server_url = args.server.rstrip("/")
    if args.tls_fingerprint:
        config.tls_fingerprint = args.tls_fingerprint.upper().strip()

    window = EnterpriseWebWindow(config, config_path)
    try:
        window.connect_and_load()
    except ApiError as exc:
        QMessageBox.critical(window, "خطای اتصال HRM", str(exc))
        return 2
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
