import ssl
import tempfile
import threading
import unittest
from pathlib import Path

from sazmanhr.api_client import ApiClient
from sazmanhr.database import Repository
from sazmanhr.demo_data import create_demo_seed
from sazmanhr.server import ApiServer, ensure_initial_owner
from sazmanhr.tls import ensure_self_signed_certificate


class TlsIntegrationTests(unittest.TestCase):
    def test_pinned_tls_health_and_login(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db = root / "hrm.sqlite"
            create_demo_seed(db)
            repo = Repository(db)
            cert, key, fingerprint = ensure_self_signed_certificate(root)
            ensure_initial_owner(repo, "owner.test", "مدیر آزمایشی", "Initial!Password1500", fingerprint)
            server = ApiServer(("127.0.0.1", 0), repo, tls_enabled=True)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(cert, key)
            server.socket = context.wrap_socket(server.socket, server_side=True)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                client = ApiClient(f"https://127.0.0.1:{server.server_address[1]}", tls_fingerprint=fingerprint)
                self.assertEqual(client.health()["status"], "ok")
                self.assertTrue(client.login("owner.test", "Initial!Password1500")["token"])
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=3)
