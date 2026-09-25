import shutil
import ssl
import tempfile
import threading
import unittest
from pathlib import Path

from sazmanhr.api_client import ApiClient
from sazmanhr.database import Repository
from sazmanhr.server import ApiServer, ensure_initial_owner
from sazmanhr.tls import ensure_self_signed_certificate


PROJECT = Path(__file__).resolve().parents[1]
SEED = PROJECT / "data" / "seed" / "sazmanhr-seed.sqlite"


class TlsIntegrationTests(unittest.TestCase):
    def test_tls_health_and_login_without_fingerprint_pinning(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db = root / "sazmanhr.sqlite"
            shutil.copy2(SEED, db)
            repo = Repository(db)
            cert, key = ensure_self_signed_certificate(root)
            ensure_initial_owner(
                repo,
                "arshia.shahbazi",
                "Arshia Shahbazi",
                "Initial!Password1500",
            )
            server = ApiServer(("127.0.0.1", 0), repo, tls_enabled=True)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(cert, key)
            server.socket = context.wrap_socket(server.socket, server_side=True)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                client = ApiClient(f"https://127.0.0.1:{server.server_address[1]}")
                health = client.health()
                self.assertEqual(health["status"], "ok")
                self.assertTrue(health["tls"])
                self.assertTrue(
                    client.login("arshia.shahbazi", "Initial!Password1500")["token"]
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
