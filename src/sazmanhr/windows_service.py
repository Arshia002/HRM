"""Windows Service host for the central server (built only on Windows)."""

from __future__ import annotations

import os
import ssl
import threading

import servicemanager
import win32event
import win32service
import win32serviceutil

from .config import ServerConfig, default_data_dir, ensure_database
from .database import Repository
from .operations import BackupScheduler, close_logging, configure_logging
from .server import ApiServer, ensure_initial_owner, write_startup_failure
from .tls import ensure_self_signed_certificate


class SazmanHRService(win32serviceutil.ServiceFramework):
    _svc_name_ = "HRMCentralService"
    _svc_display_name_ = "HRM Central Service"
    _svc_description_ = "Central data and synchronization service for HRM clients"

    def __init__(self, args):
        super().__init__(args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.httpd: ApiServer | None = None
        self.thread: threading.Thread | None = None
        self.scheduler: BackupScheduler | None = None

    def SvcStop(self):  # noqa: N802
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        if self.httpd:
            self.httpd.shutdown()
        if self.scheduler:
            self.scheduler.stop()
        win32event.SetEvent(self.stop_event)

    def SvcDoRun(self):  # noqa: N802
        logger = None
        try:
            data_dir = default_data_dir()
            config = ServerConfig.load(data_dir)
            logger = configure_logging(data_dir, config.log_level)
            repository = Repository(ensure_database(data_dir))
            cert = key = None
            fingerprint = ""
            if config.tls_mode == "auto":
                cert, key, fingerprint = ensure_self_signed_certificate(data_dir)
            elif config.tls_mode == "custom":
                cert, key = __import__("pathlib").Path(config.tls_cert), __import__("pathlib").Path(config.tls_key)
                from .tls import pem_fingerprint
                fingerprint = pem_fingerprint(cert)
            ensure_initial_owner(repository, "arshia.shahbazi", "ارشیا شهبازی",
                                 os.environ.get("SAZMANHR_INITIAL_PASSWORD"), fingerprint)
            self.httpd = ApiServer((config.host, config.port), repository, logger, tls_enabled=bool(cert))
            if cert and key:
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                context.minimum_version = ssl.TLSVersion.TLSv1_2
                context.load_cert_chain(cert, key)
                self.httpd.socket = context.wrap_socket(self.httpd.socket, server_side=True)
            self.scheduler = BackupScheduler(repository, config.backup_interval_hours, config.backup_retention, config.backup_secondary_dir, config.backup_secondary_retention)
            self.scheduler.start()
            self.thread = threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.5}, daemon=True)
            self.thread.start()
            servicemanager.LogInfoMsg("HRM Central Service started on port 8765")
            win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE)
            if self.thread:
                self.thread.join(timeout=10)
            if self.httpd:
                self.httpd.server_close()
            if self.scheduler:
                self.scheduler.stop()
            servicemanager.LogInfoMsg("HRM Central Service stopped")
        except Exception as exc:
            write_startup_failure(default_data_dir(), exc)
            servicemanager.LogErrorMsg(f"HRM Central Service failed: {exc!r}")
            raise
        finally:
            close_logging(logger)


def main() -> None:
    if len(__import__("sys").argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(SazmanHRService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(SazmanHRService)


if __name__ == "__main__":
    main()
