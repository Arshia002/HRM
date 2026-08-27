import shutil
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sazmanhr.api_client import ApiClient
from sazmanhr.database import Repository
from sazmanhr.server import ApiServer


PROJECT = Path(__file__).resolve().parents[1]
SEED = PROJECT / "data" / "seed" / "sazmanhr-seed.sqlite"


class FiveClientNetworkTests(unittest.TestCase):
    def test_five_admin_clients_share_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "network.sqlite"
            shutil.copy2(SEED, db)
            repo = Repository(db)
            password = "Network!Admin1500"
            for index in range(5):
                repo.create_user(f"admin.{index + 1}", f"مدیر {index + 1}", password, "admin",
                                 must_change_password=False)
            server = ApiServer(("127.0.0.1", 0), repo)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_address[1]}"
            clients = [ApiClient(base) for _ in range(5)]
            try:
                for index, client in enumerate(clients):
                    client.login(f"admin.{index + 1}", password)
                people = clients[0].request("GET", "/api/personnel", query={"limit": 5})["items"]

                def update(args):
                    index, client = args
                    detail = client.request("GET", f"/api/personnel/{people[index]['id']}")
                    detail["actual_location"] = f"مکان مدیر {index + 1}"
                    return client.request("POST", "/api/personnel", detail)

                with ThreadPoolExecutor(max_workers=5) as pool:
                    results = list(pool.map(update, enumerate(clients)))
                self.assertEqual(len(results), 5)
                for client in clients:
                    changes = client.request("GET", "/api/changes", query={"since": 0})
                    personnel_changes = [item for item in changes["items"] if item["entity_type"] == "personnel"]
                    self.assertGreaterEqual(len(personnel_changes), 5)
            finally:
                for client in clients:
                    client.logout()
                server.shutdown(); server.server_close(); thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()

