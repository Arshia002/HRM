"""TLS-first LAN service used exclusively by native desktop clients."""

from __future__ import annotations

import argparse
import json
import logging
import os
import ssl
import sys
import time
import traceback
import uuid
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from . import __version__
from .config import ServerConfig, default_data_dir, ensure_database
from .database import AuthenticationError, ConflictError, MfaRequired, PermissionDenied, Repository
from .operations import BackupScheduler, close_logging, configure_logging, restore_database, sqlite_integrity
from .security import generate_temporary_password
from .tls import ensure_self_signed_certificate, pem_fingerprint
from .windows_service_control import stop_windows_service

MAX_BODY = 4 * 1024 * 1024


class ApiServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], repository: Repository, logger: logging.Logger | None = None,
                 tls_enabled: bool = False):
        super().__init__(address, ApiHandler)
        self.repository = repository
        self.logger = logger or logging.getLogger("sazmanhr")
        self.started_monotonic = time.monotonic()
        self.tls_enabled = tls_enabled

    def handle_error(self, request, client_address) -> None:
        self.logger.warning("connection_closed_before_http", extra={"client": client_address[0]})


class ApiHandler(BaseHTTPRequestHandler):
    server_version = "HRM/0.4"
    sys_version = ""

    @property
    def repo(self) -> Repository:
        return self.server.repository  # type: ignore[attr-defined]

    @property
    def logger(self) -> logging.Logger:
        return self.server.logger  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: Any) -> None:
        self.logger.info("http_request", extra={"client": self.client_address[0], "detail": fmt % args})

    def do_GET(self) -> None:  # noqa: N802
        self._execute("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._execute("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._execute("PUT")

    def do_DELETE(self) -> None:  # noqa: N802
        self._execute("DELETE")

    def _execute(self, method: str) -> None:
        self.request_id = uuid.uuid4().hex
        try:
            self._dispatch(method)
        except MfaRequired as exc:
            self._json(HTTPStatus.UNAUTHORIZED, {"error": str(exc), "code": "mfa_required"})
        except AuthenticationError as exc:
            self._json(HTTPStatus.UNAUTHORIZED, {"error": str(exc), "code": "authentication_failed"})
        except PermissionDenied as exc:
            self._json(HTTPStatus.FORBIDDEN, {"error": str(exc), "code": "permission_denied"})
        except ConflictError as exc:
            self._json(HTTPStatus.CONFLICT, {"error": str(exc), "code": "version_conflict"})
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc), "code": "bad_request"})
        except Exception:
            self.logger.exception("unhandled_api_error", extra={"request_id": self.request_id})
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "خطای داخلی سرویس.", "code": "internal_error"})

    def _dispatch(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)
        if method == "GET" and path == "/api/health":
            self._json(HTTPStatus.OK, {
                "status": "ok", "version": __version__, "database": "ready",
                "tls": bool(self.server.tls_enabled),  # type: ignore[attr-defined]
                "uptime_seconds": int(time.monotonic() - self.server.started_monotonic),  # type: ignore[attr-defined]
            })
            return
        if method == "POST" and path == "/api/login":
            body = self._body()
            result = self.repo.authenticate(
                str(body.get("username", "")), str(body.get("password", "")),
                self.client_address[0], str(body.get("otp", "")),
            )
            self._json(HTTPStatus.OK, result)
            return

        token, user = self._authenticated()
        if method == "POST" and path == "/api/logout":
            self.repo.logout(token)
            self._json(HTTPStatus.OK, {"ok": True})
            return
        if method == "GET" and path == "/api/me":
            self._json(HTTPStatus.OK, {"user": user, "permissions": sorted(self.repo.permissions_for(user)),
                                       "mfa": self.repo.mfa_status(user["id"])})
            return
        if method == "POST" and path == "/api/change-password":
            body = self._body()
            self.repo.change_password(user["id"], str(body.get("current_password", "")), str(body.get("new_password", "")))
            self._json(HTTPStatus.OK, {"ok": True})
            return
        if user.get("must_change_password"):
            raise PermissionDenied("پیش از ادامه باید رمز عبور موقت تغییر کند.")

        if method == "POST" and path == "/api/mfa/setup":
            self._json(HTTPStatus.OK, self.repo.begin_mfa(
                user["id"], user["username"], str(self._body().get("current_password", ""))))
            return
        if method == "POST" and path == "/api/mfa/confirm":
            codes = self.repo.confirm_mfa(user["id"], str(self._body().get("code", "")))
            self._json(HTTPStatus.OK, {"ok": True, "recovery_codes": codes})
            return

        if method == "GET" and path == "/api/dashboard":
            self.repo.require(user, "read")
            self._json(HTTPStatus.OK, {"stats": self.repo.stats(), "widgets": self.repo.list_widgets()})
            return
        if method in {"POST", "PUT"} and path == "/api/dashboard/widgets":
            self.repo.require(user, "edit_dashboard")
            self._json(HTTPStatus.OK, self.repo.save_widget(self._body(), user["id"]))
            return
        if method == "DELETE" and path.startswith("/api/dashboard/widgets/"):
            self.repo.require(user, "edit_dashboard")
            widget_id = path.rsplit("/", 1)[1]
            self.repo.delete_widget(widget_id, int(query.get("version", ["0"])[0]), user["id"])
            self._json(HTTPStatus.OK, {"ok": True})
            return

        if method == "GET" and path == "/api/personnel":
            self.repo.require(user, "read")
            self._json(HTTPStatus.OK, self.repo.list_personnel(
                query.get("q", [""])[0], int(query.get("limit", ["200"])[0]), int(query.get("offset", ["0"])[0]),
                unit=query.get("unit", [""])[0], employment=query.get("employment", [""])[0],
                status=query.get("status", [""])[0], location=query.get("location", [""])[0],
            ))
            return
        if method == "GET" and path.startswith("/api/personnel/"):
            self.repo.require(user, "read")
            person = self.repo.get_person(path.rsplit("/", 1)[1])
            self._json(HTTPStatus.OK, person) if person else self._json(
                HTTPStatus.NOT_FOUND, {"error": "رکورد پیدا نشد.", "code": "not_found"})
            return
        if method in {"POST", "PUT"} and path == "/api/personnel":
            self.repo.require(user, "edit_personnel")
            self._json(HTTPStatus.OK, self.repo.save_person(self._body(), user["id"]))
            return
        if method == "DELETE" and path.startswith("/api/personnel/"):
            self.repo.require(user, "delete_personnel")
            self.repo.delete_person(path.rsplit("/", 1)[1], int(query.get("version", ["0"])[0]), user["id"])
            self._json(HTTPStatus.OK, {"ok": True})
            return

        if method == "GET" and path == "/api/organization/summary":
            self.repo.require(user, "read")
            self._json(HTTPStatus.OK, self.repo.organization_summary())
            return
        if method == "GET" and path == "/api/units":
            self.repo.require(user, "read")
            self._json(HTTPStatus.OK, {"items": self.repo.list_units(query.get("q", [""])[0])})
            return
        if method == "GET" and path.startswith("/api/units/"):
            self.repo.require(user, "read")
            unit = self.repo.get_unit(path.rsplit("/", 1)[1])
            self._json(HTTPStatus.OK, unit) if unit else self._json(
                HTTPStatus.NOT_FOUND, {"error": "واحد سازمانی پیدا نشد.", "code": "not_found"})
            return
        if method == "GET" and path == "/api/positions":
            self.repo.require(user, "read")
            self._json(HTTPStatus.OK, self.repo.list_positions(
                query.get("q", [""])[0], query.get("unit_id", [""])[0], query.get("occupancy", [""])[0]
            ))
            return
        if method == "GET" and path.startswith("/api/positions/"):
            self.repo.require(user, "read")
            position = self.repo.get_position(path.rsplit("/", 1)[1])
            self._json(HTTPStatus.OK, position) if position else self._json(
                HTTPStatus.NOT_FOUND, {"error": "پست سازمانی پیدا نشد.", "code": "not_found"})
            return

        if method == "GET" and path == "/api/chart/pages":
            self.repo.require(user, "read")
            self._json(HTTPStatus.OK, {"items": self.repo.list_chart_pages()})
            return
        if method == "GET" and path.startswith("/api/chart/pages/"):
            self.repo.require(user, "read")
            page = self.repo.get_chart_page(int(path.rsplit("/", 1)[1]))
            self._json(HTTPStatus.OK, page) if page else self._json(
                HTTPStatus.NOT_FOUND, {"error": "صفحه چارت پیدا نشد.", "code": "not_found"})
            return
        if method == "PUT" and path.startswith("/api/chart/pages/"):
            self.repo.require(user, "edit_chart")
            page_no = int(path.rsplit("/", 1)[1])
            self._json(HTTPStatus.OK, self.repo.save_chart_page(page_no, self._body(), user["id"]))
            return

        if method == "GET" and path == "/api/workflows":
            self.repo.require(user, "read")
            self._json(HTTPStatus.OK, {"items": self.repo.list_workflows(query.get("state", [""])[0])})
            return
        if method == "POST" and path == "/api/workflows":
            self.repo.require(user, "manage_workflows")
            self._json(HTTPStatus.CREATED, self.repo.create_workflow(self._body(), user["id"]))
            return
        if method == "POST" and path.startswith("/api/workflows/") and path.endswith("/transition"):
            self.repo.require(user, "manage_workflows")
            workflow_id = path.split("/")[-2]
            body = self._body()
            self._json(HTTPStatus.OK, self.repo.transition_workflow(
                workflow_id, str(body.get("state", "")), str(body.get("note", "")), user["id"],
                int(body.get("row_version", 0))))
            return
        if method == "GET" and path == "/api/notifications":
            self.repo.require(user, "read")
            self._json(HTTPStatus.OK, {"items": self.repo.notifications(
                user["id"], query.get("unread", ["0"])[0] == "1")})
            return
        if method == "POST" and path.startswith("/api/notifications/") and path.endswith("/read"):
            self.repo.mark_notification_read(path.split("/")[-2], user["id"])
            self._json(HTTPStatus.OK, {"ok": True})
            return

        if method == "GET" and path == "/api/changes":
            self.repo.require(user, "read")
            self._json(HTTPStatus.OK, self.repo.changes(int(query.get("since", ["0"])[0])))
            return
        if method == "GET" and path == "/api/audit":
            self.repo.require(user, "view_audit")
            self._json(HTTPStatus.OK, {"items": self.repo.audit(int(query.get("limit", ["200"])[0])),
                                       "chain_valid": self.repo.verify_audit_chain()})
            return
        if method == "GET" and path == "/api/monitoring":
            self.repo.require(user, "view_monitoring")
            self._json(HTTPStatus.OK, {"metrics": self.repo.monitoring(), "events": self.repo.operational_events(100)})
            return
        if method == "GET" and path == "/api/users":
            self.repo.require(user, "manage_users")
            self._json(HTTPStatus.OK, {"items": self.repo.list_users()})
            return
        if method == "POST" and path == "/api/users":
            self.repo.require(user, "manage_users")
            body = self._body()
            self._json(HTTPStatus.CREATED, self.repo.create_user(
                str(body.get("username", "")), str(body.get("display_name", "")),
                str(body.get("password", "")), str(body.get("role", "viewer")), actor_id=user["id"]))
            return
        if method == "PUT" and path.startswith("/api/users/") and path.endswith("/permissions"):
            self.repo.require(user, "manage_users")
            target_id = path.split("/")[-2]
            overrides = self._body().get("overrides", {})
            if not isinstance(overrides, dict):
                raise ValueError("ساختار ریزدسترسی معتبر نیست.")
            self._json(HTTPStatus.OK, self.repo.set_user_permissions(target_id, overrides, user["id"]))
            return
        if method == "POST" and path == "/api/backup":
            self.repo.require(user, "backup")
            backup_dir = self.repo.path.parent / "backups"
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            target = self.repo.backup(backup_dir / f"manual-{stamp}.sqlite", user["id"], "manual")
            self._json(HTTPStatus.OK, {"ok": True, "filename": target.name})
            return
        if method == "GET" and path == "/api/backups":
            self.repo.require(user, "backup")
            self._json(HTTPStatus.OK, {"items": self.repo.list_backups()})
            return

        self._json(HTTPStatus.NOT_FOUND, {"error": "مسیر سرویس پیدا نشد.", "code": "not_found"})

    def _authenticated(self) -> tuple[str, dict[str, Any]]:
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            raise AuthenticationError("نشست معتبر نیست.")
        token = header[7:].strip()
        return token, self.repo.session_user(token)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        if length > MAX_BODY:
            raise ValueError("حجم درخواست بیش از حد مجاز است.")
        if not self.headers.get("Content-Type", "").lower().startswith("application/json"):
            raise ValueError("Content-Type باید application/json باشد.")
        data = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("بدنه درخواست باید یک شیء JSON باشد.")
        return data

    def _json(self, status: HTTPStatus, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        try:
            self.send_response(status.value)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Request-ID", getattr(self, "request_id", ""))
            if bool(self.server.tls_enabled):  # type: ignore[attr-defined]
                self.send_header("Strict-Transport-Security", "max-age=31536000")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            self.logger.warning("client_disconnected", extra={"request_id": getattr(self, "request_id", "")})


def ensure_initial_owner(repo: Repository, username: str, display_name: str, password: str | None,
                         tls_fingerprint: str = "") -> str | None:
    if repo.has_users():
        return None
    temporary = password or "13811381"
    owner = repo.create_user(username, display_name, temporary, "owner", must_change_password=True, bootstrap_password=(temporary == "13811381"))
    with repo.write() as conn:
        conn.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES('initial_owner_id',?)", (owner["id"],))
    notice = repo.path.parent / "FIRST_LOGIN.txt"
    notice.write_text(
        "HRM - اطلاعات ورود یک‌بارمصرف\n"
        f"Server: https://127.0.0.1:8765\nUsername: {username}\nPassword: {temporary}\n"
        f"TLS SHA-256: {tls_fingerprint}\n"
        "در نخستین ورود، تغییر رمز عبور اجباری است. پس از تغییر رمز این فایل حذف می‌شود.\n",
        encoding="utf-8",
    )
    try:
        os.chmod(notice, 0o600)
    except OSError:
        pass
    return temporary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="HRM central LAN service")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--data-dir", type=Path, default=default_data_dir())
    parser.add_argument("--seed", type=Path)
    parser.add_argument("--tls-mode", choices=("auto", "custom", "off"))
    parser.add_argument("--tls-cert", type=Path)
    parser.add_argument("--tls-key", type=Path)
    parser.add_argument("--initial-user", default="arshia.shahbazi")
    parser.add_argument("--initial-display-name", default="ارشیا شهبازی")
    parser.add_argument("--initial-password", default=os.environ.get("SAZMANHR_INITIAL_PASSWORD"))
    parser.add_argument("--backup-now", action="store_true")
    parser.add_argument("--restore", type=Path)
    parser.add_argument("--verify-database", action="store_true")
    parser.add_argument("--init-only", action="store_true")
    parser.add_argument("--health-check", metavar="URL")
    parser.add_argument("--health-timeout", type=int, default=30)
    parser.add_argument("--stop-windows-service", metavar="NAME")
    parser.add_argument("--service-stop-timeout", type=int, default=30)
    parser.add_argument("--service-state-file", type=Path)
    parser.add_argument("--diagnostic-log", type=Path)
    return parser


def resolve_tls(args: argparse.Namespace, config: ServerConfig) -> tuple[Path | None, Path | None, str]:
    mode = args.tls_mode or config.tls_mode
    if mode == "off":
        return None, None, ""
    cert = args.tls_cert or (Path(config.tls_cert) if config.tls_cert else None)
    key = args.tls_key or (Path(config.tls_key) if config.tls_key else None)
    if mode == "custom":
        if not cert or not key or not cert.is_file() or not key.is_file():
            raise ValueError("Custom TLS requires valid --tls-cert and --tls-key files.")
        return cert, key, pem_fingerprint(cert)
    return ensure_self_signed_certificate(args.data_dir)


def wait_for_health(url: str, timeout_seconds: int = 30) -> dict[str, Any]:
    """Wait for the installed service without relying on PowerShell or curl."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    deadline = time.monotonic() + max(1, min(120, timeout_seconds))
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            request = Request(url.rstrip("/") + "/api/health", headers={"Accept": "application/json"})
            with urlopen(request, timeout=3, context=context) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload.get("status") == "ok" and payload.get("tls") is True:
                return payload
            last_error = RuntimeError(f"Unhealthy response: {payload!r}")
        except Exception as exc:
            last_error = exc
        time.sleep(0.5)
    raise RuntimeError(f"Central service health check timed out: {last_error!r}")


def write_startup_failure(data_dir: Path, exc: BaseException, target: Path | None = None) -> Path | None:
    """Persist a traceback that remains available when Setup runs the EXE hidden."""
    try:
        path = (target or (data_dir / "logs" / "startup-failure.log")).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"\n[{datetime.now().astimezone().isoformat(timespec='seconds')}] ")
            handle.write(f"HRM {__version__}\n")
            handle.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
        return path
    except OSError:
        return None


def run_server(args: argparse.Namespace) -> int:
    config = ServerConfig.load(args.data_dir)
    logger = configure_logging(args.data_dir, config.log_level)
    try:
        return run_server_with_logger(args, config, logger)
    finally:
        close_logging(logger)


def run_server_with_logger(args: argparse.Namespace, config: ServerConfig, logger: logging.Logger) -> int:
    db_path = ensure_database(args.data_dir, args.seed)
    if args.restore:
        safety = restore_database(db_path, args.restore.resolve())
        logger.warning("database_restored", extra={"safety_backup": str(safety)})
    if args.verify_database:
        ok, detail = sqlite_integrity(db_path)
        print(json.dumps({"ok": ok, "detail": detail, "database": str(db_path)}, ensure_ascii=False))
        return 0 if ok else 2
    cert, key, fingerprint = resolve_tls(args, config)
    repo = Repository(db_path)
    temporary = ensure_initial_owner(repo, args.initial_user, args.initial_display_name, args.initial_password, fingerprint)
    repo.record_operational("INFO", "server", "startup", "Server initialization completed",
                            {"version": __version__, "tls": bool(cert)})
    if temporary:
        print(f"Initial username: {args.initial_user}")
        print(f"One-time password: {temporary}")
        print(f"TLS fingerprint: {fingerprint}")
        print(f"Saved to: {db_path.parent / 'FIRST_LOGIN.txt'}")
    if args.backup_now:
        scheduler = BackupScheduler(repo, config.backup_interval_hours, config.backup_retention)
        print(scheduler.run_once())
        return 0
    if args.init_only:
        return 0
    host, port = args.host or config.host, args.port or config.port
    server = ApiServer((host, port), repo, logger, tls_enabled=bool(cert))
    if cert and key:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(cert, key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    scheduler = BackupScheduler(repo, config.backup_interval_hours, config.backup_retention)
    scheduler.start()
    logger.info("server_listening", extra={"host": host, "port": port, "tls": bool(cert)})
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        scheduler.stop()
        server.server_close()
        repo.record_operational("INFO", "server", "shutdown", "Server stopped")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.data_dir = args.data_dir.resolve()
    try:
        if args.stop_windows_service:
            state = stop_windows_service(args.stop_windows_service, args.service_stop_timeout)
            if args.service_state_file:
                state_file = args.service_state_file.resolve()
                state_file.parent.mkdir(parents=True, exist_ok=True)
                state_file.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(state))
            return 0
        if args.health_check:
            payload = wait_for_health(args.health_check, args.health_timeout)
            print(json.dumps(payload, ensure_ascii=False))
            return 0
        return run_server(args)
    except Exception as exc:
        diagnostic = write_startup_failure(args.data_dir, exc, args.diagnostic_log)
        print(f"HRM startup failed: {exc}", file=sys.stderr)
        if diagnostic:
            print(f"Diagnostic log: {diagnostic}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
