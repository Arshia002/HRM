import shutil
import ssl
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sazmanhr.api_client import ApiClient, ApiError
from sazmanhr.database import Repository
from sazmanhr.server import ApiServer
from sazmanhr.tls import ensure_self_signed_certificate


ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "seed" / "sazmanhr-seed.sqlite"


def start_tls(repo, root, port=0):
    cert, key = ensure_self_signed_certificate(root)
    server = ApiServer(("127.0.0.1", port), repo, tls_enabled=True)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


class RcNetworkResilienceTests(unittest.TestCase):
    def test_six_clients_concurrently_operate_over_tls(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "hrm.sqlite"
            shutil.copy2(SEED, db)
            repo = Repository(db)
            password = "RC!Network1500"
            for i in range(6):
                repo.create_user(
                    f"rc.admin.{i}",
                    f"RC Admin {i}",
                    password,
                    "admin",
                    must_change_password=False,
                )

            server, thread = start_tls(repo, root)
            clients = [
                ApiClient(f"https://127.0.0.1:{server.server_address[1]}")
                for _ in range(6)
            ]
            try:
                for i, client in enumerate(clients):
                    client.login(f"rc.admin.{i}", password)
                people = clients[0].request(
                    "GET", "/api/personnel", query={"limit": 6}
                )["items"]

                def work(pair):
                    i, client = pair
                    detail = client.request(
                        "GET", f"/api/personnel/{people[i]['id']}"
                    )
                    detail["activity_area"] = f"RC-TLS-{i}"
                    return client.request("POST", "/api/personnel", detail)

                with ThreadPoolExecutor(max_workers=6) as pool:
                    out = list(pool.map(work, enumerate(clients)))
                self.assertEqual(len(out), 6)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)

    def test_disconnect_is_reported_and_reconnect_recovers(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "hrm.sqlite"
            shutil.copy2(SEED, db)
            repo = Repository(db)
            server, thread = start_tls(repo, root)
            port = server.server_address[1]
            client = ApiClient(f"https://127.0.0.1:{port}", timeout=0.5)

            self.assertEqual(client.health()["status"], "ok")
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

            with self.assertRaises(ApiError):
                client.health()

            server2, thread2 = start_tls(repo, root, port)
            try:
                self.assertEqual(client.health()["status"], "ok")
            finally:
                server2.shutdown()
                server2.server_close()
                thread2.join(timeout=3)

    def test_certificate_replacement_does_not_reintroduce_pinning(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "hrm.sqlite"
            shutil.copy2(SEED, db)
            repo = Repository(db)

            server, thread = start_tls(repo, root)
            port = server.server_address[1]
            client = ApiClient(f"https://127.0.0.1:{port}", timeout=1.0)
            self.assertEqual(client.health()["status"], "ok")
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

            (root / "tls" / "server.crt").unlink()
            (root / "tls" / "server.key").unlink()

            server2, thread2 = start_tls(repo, root, port)
            try:
                health = client.health()
                self.assertEqual(health["status"], "ok")
                self.assertTrue(health["tls"])
            finally:
                server2.shutdown()
                server2.server_close()
                thread2.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
