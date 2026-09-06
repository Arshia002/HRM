"""TLS-first LAN service used exclusively by native desktop clients."""

from __future__ import annotations

import argparse
import json
import logging
import os
import ssl
import sys
import tempfile
import threading
import time
import traceback
import uuid
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request, urlopen

from . import __version__
from .config import ServerConfig, default_data_dir, ensure_database
from .database import AuthenticationError, ConflictError, MfaRequired, PermissionDenied, Repository
from .compat_v49 import (
    build_bootstrap as build_v49_bootstrap, health as v49_health, history as v49_history,
    load_dataset as load_v49_dataset, legacy_permissions, legacy_user, placement_reviews as v49_placement_reviews,
    record_client_log, resolve_placement_review as v49_resolve_placement_review,
)
from .operations import BackupScheduler, close_logging, configure_logging, restore_database, sqlite_integrity
from .backup_package import create_package as create_backup_package, stage_database as stage_backup_database
from .monthly_import import MAX_IMPORT_BYTES, PREVIEW_TTL_MINUTES, apply_plan as apply_monthly_plan, preview_xlsx
from .security import generate_temporary_password
from .tls import ensure_self_signed_certificate, pem_fingerprint
from .windows_service_control import stop_windows_service

MAX_BODY = 4 * 1024 * 1024


class ApiServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], repository: Repository, logger: logging.Logger | None = None,
                 tls_enabled: bool = False, web_root: Path | None = None):
        super().__init__(address, ApiHandler)
        self.repository = repository
        self.logger = logger or logging.getLogger("sazmanhr")
        self.started_monotonic = time.monotonic()
        self.tls_enabled = tls_enabled
        self.web_root = web_root.resolve() if web_root else None
        self.import_previews: dict[str, dict[str, Any]] = {}
        self.import_preview_lock = threading.RLock()

    def handle_error(self, request, client_address) -> None:
        self.logger.warning("connection_closed_before_http", extra={"client": client_address[0]})


class ApiHandler(BaseHTTPRequestHandler):
    server_version = "HRM/0.7"
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
        if method == "GET" and getattr(self.server, "web_root", None) and (
            path in {"/", "/web"} or path.startswith("/web/") or path.startswith("/assets/")
        ):
            self._web_asset(path)
            return
        if method == "GET" and path == "/api/status":
            self._json(HTTPStatus.OK, {
                "server": True, "portable": False, "network_enabled": True,
                "version": __version__, "tls": bool(self.server.tls_enabled),  # type: ignore[attr-defined]
            })
            return
        if method == "GET" and path == "/api/setup/status":
            # Enterprise installs are provisioned before the listener starts.
            # The exact v4.9 login shell still probes this route.
            self._json(HTTPStatus.OK, {"required": not self.repo.has_users(), "mode": "enterprise"})
            return
        if method == "GET" and path == "/api/health":
            details = v49_health(self.repo)
            details.update({
                "status": "ok", "version": __version__, "database": "ready",
                "tls": bool(self.server.tls_enabled),  # type: ignore[attr-defined]
                "uptime_seconds": int(time.monotonic() - self.server.started_monotonic),  # type: ignore[attr-defined]
            })
            self._json(HTTPStatus.OK, details)
            return
        if method == "POST" and path == "/api/client-log":
            # Runtime Core can report pre-auth failures. Only bounded/redacted
            # diagnostic metadata is retained; headers and request context are not.
            record_client_log(self.repo, self._body())
            self._json(HTTPStatus.OK, {"ok": True})
            return
        if method == "POST" and path == "/api/login":
            body = self._body()
            result = self.repo.authenticate(
                str(body.get("username", "")), str(body.get("password", "")),
                self.client_address[0], str(body.get("otp", "")),
            )
            result["user"] = legacy_user(self.repo, result["user"])
            result["permissions"] = legacy_permissions(self.repo, result["user"])
            result["must_change"] = bool(result["user"].get("must_change_password"))
            # v4.9 pre-auth shell requires a non-empty CSRF value. Central API
            # mutations are protected by bearer/X-Token sessions and do not use
            # the portable CSRF transport; this opaque value is client state only.
            result["csrf"] = uuid.uuid4().hex
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
            new_password = str(body.get("new_password") or body.get("password") or "")
            self.repo.change_password(user["id"], str(body.get("current_password", "")), new_password)
            self._json(HTTPStatus.OK, {"ok": True})
            return
        if method == "GET" and path == "/api/auth-state":
            self._json(HTTPStatus.OK, {
                "temporary_password_file": bool(user.get("must_change_password")),
                "must_change": bool(user.get("must_change_password")),
            })
            return
        if user.get("must_change_password"):
            raise PermissionDenied("پیش از ادامه باید رمز عبور موقت تغییر کند.")

        if method == "GET" and path == "/api/bootstrap":
            self.repo.require(user, "read")
            self._json(HTTPStatus.OK, build_v49_bootstrap(self.repo))
            return
        if method == "GET" and path.startswith("/api/private-data/"):
            self.repo.require(user, "read")
            name = path.rsplit("/", 1)[1]
            self._json(HTTPStatus.OK, load_v49_dataset(self.repo, name))
            return

        if method == "POST" and path in {"/api/import/preview", "/portable-api/import/preview"}:
            self.repo.require(user, "edit_personnel")
            self.repo.require(user, "manage_movements")
            raw = self._raw_body(
                max_bytes=MAX_IMPORT_BYTES,
                content_types=("application/octet-stream",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            )
            filename = Path(unquote(self.headers.get("X-Filename", "monthly.xlsx"))).name[:180] or "monthly.xlsx"
            preview, plan = preview_xlsx(self.repo, raw, filename)
            plan["expires_at_epoch"] = time.time() + PREVIEW_TTL_MINUTES * 60
            with self.server.import_preview_lock:  # type: ignore[attr-defined]
                expired = [key for key, item in self.server.import_previews.items()  # type: ignore[attr-defined]
                           if float(item.get("expires_at_epoch", 0)) <= time.time()]
                for key in expired:
                    self.server.import_previews.pop(key, None)  # type: ignore[attr-defined]
                self.server.import_previews[preview["preview_id"]] = plan  # type: ignore[attr-defined]
            self._json(HTTPStatus.OK, preview)
            return
        if method == "POST" and path in {"/api/import/apply", "/portable-api/import/apply"}:
            self.repo.require(user, "edit_personnel")
            self.repo.require(user, "manage_movements")
            preview_id = str(self._body().get("preview_id", "")).strip()
            if not preview_id:
                raise ValueError("شناسه Dry Run ارسال نشده است.")
            with self.server.import_preview_lock:  # type: ignore[attr-defined]
                plan = self.server.import_previews.get(preview_id)  # type: ignore[attr-defined]
            if not plan or float(plan.get("expires_at_epoch", 0)) <= time.time():
                with self.server.import_preview_lock:  # type: ignore[attr-defined]
                    self.server.import_previews.pop(preview_id, None)  # type: ignore[attr-defined]
                raise ValueError("اعتبار Dry Run پایان یافته است؛ فایل را دوباره بررسی کنید.")
            backup_dir = self.repo.path.parent / "backups"
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = self.repo.backup(backup_dir / f"pre-monthly-import-{stamp}.sqlite", user["id"], "pre-monthly-import")
            result = apply_monthly_plan(self.repo, plan, user["id"], backup_filename=backup.name)
            with self.server.import_preview_lock:  # type: ignore[attr-defined]
                self.server.import_previews.pop(preview_id, None)  # type: ignore[attr-defined]
            self._json(HTTPStatus.OK, result)
            return

        if method == "POST" and path == "/portable-api/backup":
            self.repo.require(user, "backup")
            package, meta = create_backup_package(self.repo, user["id"])
            self._binary(HTTPStatus.OK, package, "application/zip", headers={
                "Content-Disposition": f'attachment; filename="{meta["filename"]}"',
                "X-SazmanHR-Backup-File": str(meta["filename"]),
                "X-SazmanHR-Backup-SHA256": str(meta["package_sha256"]),
            })
            return
        if method == "POST" and path == "/portable-api/backup/inspect":
            self.repo.require(user, "restore")
            raw = self._raw_body(max_bytes=512 * 1024 * 1024, content_types=("application/zip",))
            with tempfile.TemporaryDirectory(prefix="hrm-backup-inspect-") as temp_dir:
                staged = Path(temp_dir) / "database.sqlite"
                meta = stage_backup_database(raw, staged)
            self._json(HTTPStatus.OK, {
                "format": meta["format"], "app_version": meta.get("app_version", ""),
                "created_at": meta.get("created_at", ""), "people": meta["people"], "slides": meta["slides"],
            })
            return
        if method == "POST" and path == "/portable-api/backup/restore":
            self.repo.require(user, "restore")
            raw = self._raw_body(max_bytes=512 * 1024 * 1024, content_types=("application/zip",))
            with tempfile.TemporaryDirectory(prefix="hrm-backup-restore-") as temp_dir:
                staged = Path(temp_dir) / "database.sqlite"
                meta = stage_backup_database(raw, staged)
                with self.repo._write_lock:
                    safety = restore_database(self.repo.path, staged)
                    self.repo.initialize()
                    self.repo.record_operational("INFO", "backup", "interactive_restore",
                                                 "Interactive verified backup restore completed.",
                                                 {"safety_backup": safety.name})
            self._json(HTTPStatus.OK, {
                "ok": True, "people": meta["people"], "slides": meta["slides"],
                "safety_backup": safety.name, "require_relogin": True,
            })
            return
        if method == "GET" and path == "/api/history":
            self.repo.require(user, "view_audit")
            self._json(HTTPStatus.OK, v49_history(
                self.repo, limit=int(query.get("limit", ["1500"])[0]),
                q=query.get("q", [""])[0], username=query.get("username", [""])[0],
                action=query.get("action", [""])[0], from_value=query.get("from", [""])[0],
                to_value=query.get("to", [""])[0],
            ))
            return

        if method == "GET" and path == "/api/snapshots":
            self.repo.require(user, "read")
            self._json(HTTPStatus.OK, self.repo.list_status_snapshots(
                query.get("engine", [""])[0], int(query.get("limit", ["96"])[0])
            ))
            return
        if method == "POST" and path == "/api/snapshot":
            self.repo.require(user, "read")
            self._json(HTTPStatus.CREATED, self.repo.add_status_snapshot(self._body(), user["id"]))
            return
        if method == "GET" and path == "/api/placement-reviews":
            self.repo.require(user, "edit_personnel")
            self._json(HTTPStatus.OK, v49_placement_reviews(self.repo))
            return
        if method == "POST" and path == "/api/placement-review/resolve":
            self.repo.require(user, "edit_personnel")
            self._json(HTTPStatus.OK, v49_resolve_placement_review(
                self.repo, int(self._body().get("id", 0)), user["id"]
            ))
            return

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
        if method == "GET" and path == "/api/analytics":
            self.repo.require(user, "read")
            self._json(HTTPStatus.OK, self.repo.analytics())
            return
        if method == "GET" and path == "/api/migration/status":
            self.repo.require(user, "read")
            self._json(HTTPStatus.OK, self.repo.migration_status())
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

        if method == "POST" and path == "/api/person/save":
            self.repo.require(user, "edit_personnel")
            legacy = self._body()
            person_id = str(legacy.get("id", "")).strip()
            current = self.repo.get_person(person_id) if person_id else None
            payload = {
                "id": person_id,
                "personnel_no": str(legacy.get("personnel_no", "")).strip(),
                "first_name": str(legacy.get("name") or legacy.get("first_name") or "").strip(),
                "last_name": str(legacy.get("last_name", "")).strip(),
                "full_name": str(legacy.get("full_name", "")).strip(),
                "gender": str(legacy.get("gender") or (current or {}).get("gender") or "").strip(),
                "organizational_unit": str(legacy.get("organizational_unit", "")).strip(),
                "position_code": str(legacy.get("position_code", "")).strip(),
                "position_title": str(legacy.get("position_title", "")).strip(),
                "employment_group": str(legacy.get("employment_group", "")).strip(),
                "employment_subtype": str(legacy.get("employment_subtype", "")).strip(),
                "status": str(legacy.get("status", "")).strip(),
                "activity_area": str(legacy.get("activity_area", "")).strip(),
                "actual_location": str(legacy.get("actual_location", "")).strip(),
                "company": str(legacy.get("company") or (current or {}).get("company") or "").strip(),
                "chart_node_id": str((current or {}).get("chart_node_id") or "").strip(),
                "chart_page_no": (current or {}).get("chart_page_no"),
                "extra": dict((current or {}).get("extra") or {}),
            }
            if current:
                payload["row_version"] = int(current["row_version"])
                movement_fields = ("organizational_unit", "position_code", "position_title", "actual_location", "status")
                changed = [field for field in movement_fields
                           if str(payload.get(field, "") or "").strip() != str(current.get(field, "") or "").strip()]
                if changed:
                    self._json(HTTPStatus.CONFLICT, {
                        "error": "تغییر واحد، پست، محل خدمت یا وضعیت باید از مسیر ثبت جابه‌جایی پرسنلی انجام شود.",
                        "code": "movement_required", "fields": changed,
                    })
                    return
            else:
                payload.pop("id", None)
            self._json(HTTPStatus.OK, self.repo.save_person(payload, user["id"]))
            return

        if method == "GET" and path == "/api/personnel":
            self.repo.require(user, "read")
            self._json(HTTPStatus.OK, self.repo.list_personnel(
                query.get("q", [""])[0], int(query.get("limit", ["200"])[0]), int(query.get("offset", ["0"])[0]),
                unit=query.get("unit", [""])[0], employment=query.get("employment", [""])[0],
                status=query.get("status", [""])[0], location=query.get("location", [""])[0],
            ))
            return
        if method == "GET" and path.startswith("/api/personnel/") and path.endswith("/movements"):
            self.repo.require(user, "read")
            person_id = path.split("/")[-2]
            self._json(HTTPStatus.OK, {"items": self.repo.list_personnel_movements(person_id)})
            return
        if method == "POST" and path.startswith("/api/personnel/") and path.endswith("/movements"):
            self.repo.require(user, "manage_movements")
            person_id = path.split("/")[-2]
            self._json(HTTPStatus.CREATED, self.repo.register_personnel_movement(person_id, self._body(), user["id"]))
            return
        if method == "POST" and path.startswith("/api/movements/") and path.endswith("/reverse"):
            self.repo.require(user, "reverse_movements")
            movement_id = path.split("/")[-2]
            self._json(HTTPStatus.OK, self.repo.reverse_personnel_movement(
                movement_id, str(self._body().get("reason", "")), user["id"]))
            return
        if method == "GET" and path.startswith("/api/personnel/"):
            self.repo.require(user, "read")
            person = self.repo.get_person(path.rsplit("/", 1)[1])
            self._json(HTTPStatus.OK, person) if person else self._json(
                HTTPStatus.NOT_FOUND, {"error": "رکورد پیدا نشد.", "code": "not_found"})
            return
        if method in {"POST", "PUT"} and path == "/api/personnel":
            self.repo.require(user, "edit_personnel")
            payload = self._body()
            person_id = str(payload.get("id", "")).strip()
            if person_id:
                current = self.repo.get_person(person_id)
                if current:
                    movement_fields = ("organizational_unit", "position_code", "position_title", "actual_location", "status")
                    changed = [field for field in movement_fields
                               if field in payload and str(payload.get(field, "") or "").strip() != str(current.get(field, "") or "").strip()]
                    if changed:
                        self._json(HTTPStatus.CONFLICT, {
                            "error": "تغییر واحد، پست، محل خدمت یا وضعیت باید از مسیر ثبت جابه‌جایی پرسنلی انجام شود.",
                            "code": "movement_required",
                            "fields": changed,
                        })
                        return
            self._json(HTTPStatus.OK, self.repo.save_person(payload, user["id"]))
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
        if method == "POST" and path == "/api/users/create":
            self.repo.require(user, "manage_users")
            body = self._body()
            temporary = generate_temporary_password()
            created = self.repo.create_user(
                str(body.get("username", "")), str(body.get("full_name") or body.get("display_name") or ""),
                temporary, "admin", actor_id=user["id"], must_change_password=True,
            )
            created = self.repo.update_user_profile(created["username"], body, user["id"])
            requested = body.get("permissions") if isinstance(body.get("permissions"), dict) else {}
            overrides = {}
            legacy_groups = {
                "edit_data": ("edit_personnel", "manage_movements"),
                "view_history": ("view_audit",),
                "backup_restore": ("backup",),
            }
            for legacy_key, current_keys in legacy_groups.items():
                if legacy_key in requested:
                    for current_key in current_keys:
                        overrides[current_key] = "allow" if bool(requested[legacy_key]) else "deny"
            if overrides:
                self.repo.set_user_permissions(created["id"], overrides, user["id"])
            public = next(item for item in self.repo.list_users() if item["id"] == created["id"])
            self._json(HTTPStatus.CREATED, {
                "user": legacy_user(self.repo, public), "temporary_password": temporary,
            })
            return
        if method == "POST" and path == "/api/users/update":
            self.repo.require(user, "manage_users")
            body = self._body()
            updated = self.repo.update_user_profile(str(body.get("username", "")), body, user["id"])
            requested = body.get("permissions") if isinstance(body.get("permissions"), dict) else {}
            legacy_groups = {
                "edit_data": ("edit_personnel", "manage_movements"),
                "view_history": ("view_audit",),
                "backup_restore": ("backup",),
            }
            overrides = {}
            for legacy_key, current_keys in legacy_groups.items():
                if legacy_key in requested:
                    for current_key in current_keys:
                        overrides[current_key] = "allow" if bool(requested[legacy_key]) else "deny"
            if overrides and updated.get("role") != "owner":
                self.repo.set_user_permissions(updated["id"], overrides, user["id"])
            current = next(item for item in self.repo.list_users() if item["id"] == updated["id"])
            self._json(HTTPStatus.OK, {"user": legacy_user(self.repo, current)})
            return
        if method == "POST" and path == "/api/users/toggle":
            self.repo.require(user, "manage_users")
            body = self._body()
            updated = self.repo.set_user_active(str(body.get("username", "")), bool(body.get("active")), user["id"])
            current = next(item for item in self.repo.list_users() if item["id"] == updated["id"])
            self._json(HTTPStatus.OK, {"user": legacy_user(self.repo, current)})
            return
        if method == "POST" and path == "/api/users/reset-password":
            self.repo.require(user, "manage_users")
            body = self._body()
            updated, temporary = self.repo.reset_user_password(str(body.get("username", "")), user["id"])
            current = next(item for item in self.repo.list_users() if item["id"] == updated["id"])
            self._json(HTTPStatus.OK, {
                "user": legacy_user(self.repo, current), "temporary_password": temporary,
            })
            return

        if method == "GET" and path == "/api/users":
            self.repo.require(user, "manage_users")
            users = self.repo.list_users()
            if self.headers.get("X-Token"):
                self._json(HTTPStatus.OK, [legacy_user(self.repo, item) for item in users])
            else:
                self._json(HTTPStatus.OK, {"items": users})
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

    def _web_asset(self, path: str) -> None:
        web_root = getattr(self.server, "web_root", None)
        if not web_root:
            self._json(HTTPStatus.NOT_FOUND, {"error": "Web UI disabled", "code": "not_found"})
            return
        if path in {"/", "/web"}:
            relative = "index.html"
        elif path.startswith("/web/"):
            relative = path[len("/web/"):]
        else:
            relative = path.lstrip("/")
        if not relative or relative.endswith("/"):
            relative += "index.html"
        candidate = (web_root / relative).resolve()
        try:
            candidate.relative_to(web_root)
        except ValueError:
            self._json(HTTPStatus.NOT_FOUND, {"error": "مسیر نامعتبر است.", "code": "not_found"})
            return
        if not candidate.is_file():
            self._json(HTTPStatus.NOT_FOUND, {"error": "فایل وب پیدا نشد.", "code": "not_found"})
            return
        mime = {
            ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml",
            ".png": "image/png", ".webp": "image/webp", ".ico": "image/x-icon",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }.get(candidate.suffix.lower(), "application/octet-stream")
        body = candidate.read_bytes()
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def _authenticated(self) -> tuple[str, dict[str, Any]]:
        header = self.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            token = header[7:].strip()
        else:
            # Exact v4.9 Runtime Core sends X-Token.  Binary compatibility
            # modules (Excel/backup) send X-Portable-Token even when hosted by
            # the central Enterprise server.  Both remain ordinary validated
            # session tokens; this changes transport only, not authorization.
            token = (self.headers.get("X-Token", "").strip() or
                     self.headers.get("X-Portable-Token", "").strip())
        if not token:
            raise AuthenticationError("نشست معتبر نیست.")
        return token, self.repo.session_user(token)

    def _raw_body(self, *, max_bytes: int, content_types: tuple[str, ...]) -> bytes:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            raise ValueError("بدنه درخواست خالی است.")
        if length > max_bytes:
            raise ValueError("حجم درخواست بیش از حد مجاز است.")
        content_type = self.headers.get("Content-Type", "").lower().split(";", 1)[0].strip()
        if content_type not in content_types:
            raise ValueError("Content-Type درخواست معتبر نیست.")
        data = self.rfile.read(length)
        if len(data) != length:
            raise ValueError("بدنه درخواست ناقص دریافت شد.")
        return data

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

    def _binary(self, status: HTTPStatus, body: bytes, content_type: str, *, headers: dict[str, str] | None = None) -> None:
        try:
            self.send_response(status.value)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Request-ID", getattr(self, "request_id", ""))
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            if bool(self.server.tls_enabled):  # type: ignore[attr-defined]
                self.send_header("Strict-Transport-Security", "max-age=31536000")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            self.logger.warning("client_disconnected", extra={"request_id": getattr(self, "request_id", "")})

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
    temporary = password or generate_temporary_password()
    owner = repo.create_user(
        username, display_name, temporary, "owner",
        must_change_password=True, bootstrap_password=password is None,
    )
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
    parser.add_argument("--web-root", type=Path, help="Serve the optional browser test UI from this directory.")
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
        print(f"Protected one-time login notice created: {db_path.parent / 'FIRST_LOGIN.txt'}")
    if args.backup_now:
        scheduler = BackupScheduler(repo, config.backup_interval_hours, config.backup_retention, config.backup_secondary_dir, config.backup_secondary_retention)
        print(scheduler.run_once())
        return 0
    if args.init_only:
        return 0
    host, port = args.host or config.host, args.port or config.port
    server = ApiServer((host, port), repo, logger, tls_enabled=bool(cert), web_root=args.web_root)
    if cert and key:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(cert, key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    scheduler = BackupScheduler(repo, config.backup_interval_hours, config.backup_retention, config.backup_secondary_dir, config.backup_secondary_retention)
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
