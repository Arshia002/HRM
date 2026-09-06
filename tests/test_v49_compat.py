import hashlib
import json
import shutil
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from sazmanhr.compat_v49 import build_bootstrap
from sazmanhr.database import Repository, canonical, utc_now
from sazmanhr.server import ApiServer

PROJECT = Path(__file__).resolve().parents[1]
SEED = PROJECT / "data" / "seed" / "sazmanhr-seed.sqlite"
WEB = PROJECT / "web"


class V49CompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.db = Path(cls.temp.name) / "compat.sqlite"
        shutil.copy2(SEED, cls.db)
        cls.repo = Repository(cls.db)
        cls.password = "Compat!Password1405"
        cls.owner = cls.repo.create_user(
            "compat.owner", "مدیر آزمون", cls.password, "owner", must_change_password=False
        )
        with cls.repo.write() as conn:
            minimal = {
                "summary": {"formal_count": 0, "total_count": 0},
                "app": {"title": "سامانه هوشمند معاونت منابع انسانی", "version": "4.9.0"},
                "change_log": [], "changelog": [], "people": [], "slides": [],
            }
            for name, value in {
                "initial-data": minimal,
                "placement-models": {"test": True},
                "person-education": {"meta": {}, "byPersonId": {}},
            }.items():
                raw = canonical(value)
                conn.execute(
                    "INSERT INTO ui_compat_datasets(name,payload_json,sha256,size_bytes,record_count,imported_at) VALUES(?,?,?,?,?,?)",
                    (name, raw, hashlib.sha256(raw.encode()).hexdigest(), len(raw.encode()), 0, utc_now()),
                )
        cls.server = ApiServer(("127.0.0.1", 0), cls.repo, web_root=WEB)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
        cls.temp.cleanup()

    def json_request(self, method, path, data=None, token=None, legacy=True):
        body = None if data is None else json.dumps(data).encode("utf-8")
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if token:
            headers["X-Token" if legacy else "Authorization"] = token if legacy else f"Bearer {token}"
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", body, headers, method=method)
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_exact_v49_static_root_and_assets_are_served(self):
        for path, source, content_type in (
            ("/", WEB / "index.html", "text/html"),
            ("/assets/styles.css", WEB / "assets" / "styles.css", "text/css"),
            ("/assets/login-power-final.webp", WEB / "assets" / "login-power-final.webp", "image/webp"),
        ):
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=5) as response:
                raw = response.read()
                self.assertTrue(response.headers.get_content_type().startswith(content_type.split(";")[0]))
            self.assertEqual(hashlib.sha256(raw).hexdigest(), hashlib.sha256(source.read_bytes()).hexdigest())

    def test_v49_status_login_x_token_bootstrap_and_private_dataset(self):
        status, runtime = self.json_request("GET", "/api/status")
        self.assertEqual(status, 200)
        self.assertTrue(runtime["server"])
        self.assertFalse(runtime["portable"])
        status, setup = self.json_request("GET", "/api/setup/status")
        self.assertEqual(status, 200)
        self.assertFalse(setup["required"])
        status, login = self.json_request("POST", "/api/login", {
            "username": "compat.owner", "password": self.password,
        })
        self.assertEqual(status, 200)
        self.assertTrue(login["token"])
        self.assertTrue(login["csrf"])
        self.assertFalse(login["must_change"])
        self.assertEqual(login["user"]["full_name"], "مدیر آزمون")
        self.assertTrue(login["permissions"]["manage_users"])
        token = login["token"]
        status, bootstrap = self.json_request("GET", "/api/bootstrap", token=token)
        self.assertEqual(status, 200)
        self.assertEqual(len(bootstrap["people"]), 36)
        self.assertEqual(len(bootstrap["slides"]), 53)
        self.assertEqual(bootstrap["app"]["version"], "4.9.0")
        status, placement = self.json_request("GET", "/api/private-data/placement-models", token=token)
        self.assertEqual(status, 200)
        self.assertEqual(placement, {"test": True})

    def test_legacy_password_field_alias_keeps_current_password_proof(self):
        status, login = self.json_request("POST", "/api/login", {
            "username": "compat.owner", "password": self.password,
        })
        token = login["token"]
        status, result = self.json_request("POST", "/api/change-password", {
            "current_password": self.password, "password": "Compat!Changed1406",
        }, token=token)
        self.assertEqual(status, 200)
        self.assertTrue(result["ok"])
        # Restore for other test methods; direct repository call still requires proof.
        self.repo.change_password(self.owner["id"], "Compat!Changed1406", self.password)

    def test_bootstrap_projects_live_normalized_data_not_stale_initial_people(self):
        bootstrap = build_bootstrap(self.repo)
        self.assertEqual(len(bootstrap["people"]), 36)
        self.assertEqual(bootstrap["summary"]["total_count"], 36)
        self.assertEqual(len(bootstrap["slides"]), 53)

    def test_v49_snapshot_round_trip(self):
        _, login = self.json_request("POST", "/api/login", {
            "username": "compat.owner", "password": self.password,
        })
        token = login["token"]
        payload = {"engine": "activity-area-test", "label": "QA", "scopes": {"company": {"approved": 568}}}
        status, created = self.json_request("POST", "/api/snapshot", payload, token=token)
        self.assertEqual(status, 201)
        self.assertEqual(created["engine"], "activity-area-test")
        status, rows = self.json_request("GET", "/api/snapshots?engine=activity-area-test", token=token)
        self.assertEqual(status, 200)
        self.assertTrue(rows)
        self.assertEqual(rows[-1]["scopes"]["company"]["approved"], 568)

    def test_v49_owner_user_management_lifecycle(self):
        _, login = self.json_request("POST", "/api/login", {
            "username": "compat.owner", "password": self.password,
        })
        token = login["token"]
        username = "compat.hr.gate2"
        status, created = self.json_request("POST", "/api/users/create", {
            "username": username, "full_name": "کاربر تست گیت دو", "title": "کارشناس منابع انسانی",
            "phone": "09000000000",
            "permissions": {"edit_data": True, "view_history": True, "backup_restore": True},
        }, token=token)
        self.assertEqual(status, 201)
        self.assertEqual(created["user"]["username"], username)
        self.assertTrue(created["temporary_password"] and len(created["temporary_password"]) >= 12)
        self.assertNotIn(created["temporary_password"], json.dumps(self.repo.audit(100), ensure_ascii=False))
        status, updated = self.json_request("POST", "/api/users/update", {
            "username": username, "full_name": "کاربر تست ویرایش‌شده", "title": "HR Admin",
            "phone": "09120000000",
            "permissions": {"edit_data": True, "view_history": False, "backup_restore": True},
        }, token=token)
        self.assertEqual(status, 200)
        self.assertEqual(updated["user"]["full_name"], "کاربر تست ویرایش‌شده")
        status, toggled = self.json_request("POST", "/api/users/toggle", {
            "username": username, "active": False,
        }, token=token)
        self.assertFalse(toggled["user"]["active"])
        status, toggled = self.json_request("POST", "/api/users/toggle", {
            "username": username, "active": True,
        }, token=token)
        self.assertTrue(toggled["user"]["active"])
        status, reset = self.json_request("POST", "/api/users/reset-password", {
            "username": username,
        }, token=token)
        self.assertEqual(status, 200)
        self.assertTrue(reset["user"]["must_change"])
        self.assertGreaterEqual(len(reset["temporary_password"]), 12)
        self.assertNotIn(reset["temporary_password"], json.dumps(self.repo.audit(100), ensure_ascii=False))

    def test_v49_person_save_alias_keeps_movement_boundary(self):
        _, login = self.json_request("POST", "/api/login", {
            "username": "compat.owner", "password": self.password,
        })
        token = login["token"]
        person = self.repo.list_personnel(limit=1)["items"][0]
        payload = {
            "id": person["id"], "personnel_no": person["personnel_no"],
            "name": person["first_name"], "last_name": person["last_name"],
            "full_name": person["full_name"], "employment_group": person["employment_group"],
            "employment_subtype": person["employment_subtype"], "position_title": person["position_title"],
            "position_code": person["position_code"], "organizational_unit": person["organizational_unit"],
            "actual_location": person["actual_location"], "activity_area": "QA Gate2",
            "status": person["status"],
        }
        status, saved = self.json_request("POST", "/api/person/save", payload, token=token)
        self.assertEqual(status, 200)
        self.assertEqual(saved["activity_area"], "QA Gate2")
        payload["organizational_unit"] = "تغییر غیرمجاز مستقیم"
        import urllib.error
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.json_request("POST", "/api/person/save", payload, token=token)
        self.assertEqual(cm.exception.code, 409)

    def test_v49_placement_review_queue_and_resolve(self):
        _, login = self.json_request("POST", "/api/login", {
            "username": "compat.owner", "password": self.password,
        })
        token = login["token"]
        person = self.repo.list_personnel(limit=1)["items"][0]
        detail = self.repo.get_person(person["id"])
        extra = dict(detail.get("extra") or {})
        extra["placement_review_required"] = True
        extra["placement_review_reason"] = "QA نیازمند بازبینی"
        with self.repo.write() as conn:
            conn.execute("UPDATE personnel SET extra_json=? WHERE id=?", (canonical(extra), person["id"]))
        status, rows = self.json_request("GET", "/api/placement-reviews", token=token)
        self.assertEqual(status, 200)
        row = next(item for item in rows if item["person_id"] == person["id"] )
        status, result = self.json_request("POST", "/api/placement-review/resolve", {"id": row["id"]}, token=token)
        self.assertEqual(status, 200)
        self.assertTrue(result["ok"])
        _, rows_after = self.json_request("GET", "/api/placement-reviews", token=token)
        self.assertFalse(any(item["person_id"] == person["id"] for item in rows_after))


if __name__ == "__main__":
    unittest.main()
