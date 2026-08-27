import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from sazmanhr.config import ensure_database
from sazmanhr.database import Repository
from sazmanhr.demo_data import DEMO_PERSONNEL_COUNT, create_demo_seed
from sazmanhr.server import ApiServer, ensure_initial_owner


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(cls.temp.name)
        seed = root / "api-seed.sqlite"
        create_demo_seed(seed)
        repo = Repository(ensure_database(root / "operational", seed))
        ensure_initial_owner(repo, "owner.test", "مدیر آزمایشی", "Initial!Password1400")
        cls.server = ApiServer(("127.0.0.1", 0), repo)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
        cls.temp.cleanup()

    def request(self, method, path, data=None, token=None):
        body = None if data is None else json.dumps(data).encode()
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", body, headers, method=method)
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, json.loads(response.read().decode())

    def test_health_login_and_shared_data(self):
        status, health = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(health["status"], "ok")
        self.assertEqual(health["database"], "ready")
        self.assertEqual(len(health["deployment"]["id"]), 32)
        self.assertEqual(health["deployment"]["users"], 1)
        self.assertEqual(health["deployment"]["personnel"], DEMO_PERSONNEL_COUNT)
        status, login = self.request("POST", "/api/login", {
            "username": "owner.test", "password": "Initial!Password1400",
        })
        self.assertEqual(status, 200)
        token = login["token"]
        status, _ = self.request("POST", "/api/change-password", {
            "current_password": "Initial!Password1400", "new_password": "Changed!Password1401",
        }, token)
        self.assertEqual(status, 200)
        status, result = self.request("GET", "/api/personnel?limit=5", token=token)
        self.assertEqual(status, 200)
        self.assertEqual(result["total"], DEMO_PERSONNEL_COUNT)
        self.assertEqual(len(result["items"]), 5)


if __name__ == "__main__":
    unittest.main()
