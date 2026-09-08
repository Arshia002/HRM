from __future__ import annotations

import io
import json
import shutil
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from openpyxl import Workbook

from sazmanhr.compat_v49 import V49_DATASET_NAMES, load_dataset
from sazmanhr.database import Repository, utc_now
from sazmanhr.monthly_import import ASSIGNMENT_HEADERS, PERSONNEL_HEADERS, preview_xlsx
from sazmanhr.server import ApiServer


ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "seed" / "sazmanhr-seed.sqlite"
WEB = ROOT / "web"


class Rc3SyntheticV49FallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "synthetic.sqlite"
        shutil.copy2(SEED, self.db)
        self.repo = Repository(self.db)
        with self.repo.write() as conn:
            conn.execute("DELETE FROM ui_compat_datasets")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _insert_dataset(self, name: str, value: object) -> None:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self.repo.write() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO ui_compat_datasets
                   (name,payload_json,sha256,size_bytes,record_count,imported_at)
                   VALUES(?,?,?,?,?,?)""",
                (name, raw, "0" * 64, len(raw.encode("utf-8")), 0, utc_now()),
            )

    def test_empty_synthetic_store_returns_all_safe_contracts(self) -> None:
        values = {name: load_dataset(self.repo, name) for name in V49_DATASET_NAMES}
        self.assertEqual(set(values), set(V49_DATASET_NAMES))
        self.assertEqual(values["position-catalog"], {"positions": []})
        self.assertEqual(values["person-education"]["byPersonId"], {})
        self.assertEqual(values["service-history"]["byPersonnelNo"], {})
        self.assertEqual(values["training-history"]["byPersonnelNo"], {})
        self.assertEqual(values["vacancy-audit"], [])
        self.assertEqual(values["gender-map"], {})

        placement = values["placement-models"]
        self.assertIn("7", placement["org79PptTree"])
        self.assertIn("10", placement["org79PptTree"])
        self.assertEqual(placement["ORG99_VERIFIED_MODEL"], {"pages": {}})
        self.assertEqual(placement["ORG101_VERIFIED_MODEL"], {"pages": {}})
        self.assertEqual(placement["ORG102_HEAD_MODEL"], {"pages": {}})
        self.assertEqual(placement["ORG104_HEAD_MODEL"], {"pages": {}})
        self.assertEqual(placement["ORG121_PLACEMENTS"], {})
        self.assertEqual(placement["ORG152_ROLE_NODES"], [])
        self.assertEqual(placement["ORG152_CORRECTIONS"], {})
        self.assertEqual(placement["ORG153_PEOPLE"], {})

    def test_real_dataset_wins_over_synthetic_fallback(self) -> None:
        expected = {"sentinel": "real-dataset"}
        self._insert_dataset("placement-models", expected)
        self.assertEqual(load_dataset(self.repo, "placement-models"), expected)

    def test_partial_store_fails_closed_for_missing_dataset(self) -> None:
        self._insert_dataset("gender-map", {})
        self.assertEqual(load_dataset(self.repo, "gender-map"), {})
        with self.assertRaises(KeyError):
            load_dataset(self.repo, "person-education")

    def test_non_synthetic_database_fails_closed(self) -> None:
        with self.repo.write() as conn:
            conn.execute("DELETE FROM metadata WHERE key IN ('seed_mode','dataset_kind')")
            conn.execute(
                "INSERT OR REPLACE INTO metadata(key,value) VALUES('seed_mode','protected')"
            )
        with self.assertRaises(KeyError):
            load_dataset(self.repo, "person-education")

    def test_private_reference_marker_disables_fallback(self) -> None:
        with self.repo.write() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO metadata(key,value) "
                "VALUES('ui_v49_reference_version','4.9.0')"
            )
        with self.assertRaises(KeyError):
            load_dataset(self.repo, "person-education")

    def test_authenticated_http_startup_datasets_use_fallback(self) -> None:
        password = "Synthetic!Fallback1405"
        self.repo.create_user(
            "synthetic.fallback",
            "کاربر ساختگی آزمون fallback",
            password,
            "owner",
            must_change_password=False,
        )
        server = ApiServer(("127.0.0.1", 0), self.repo, web_root=WEB)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            body = json.dumps(
                {"username": "synthetic.fallback", "password": password}
            ).encode("utf-8")
            request = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/login",
                body,
                {"Content-Type": "application/json", "Accept": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                login = json.loads(response.read().decode("utf-8"))
            token = login["token"]

            def get(path: str) -> object:
                req = urllib.request.Request(
                    f"http://127.0.0.1:{port}{path}",
                    headers={"Accept": "application/json", "X-Token": token},
                )
                with urllib.request.urlopen(req, timeout=5) as response:
                    self.assertEqual(response.status, 200)
                    return json.loads(response.read().decode("utf-8"))

            placement = get("/api/private-data/placement-models")
            education = get("/api/private-data/person-education")
            self.assertIn("org79PptTree", placement)
            self.assertEqual(education["byPersonId"], {})
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_monthly_preview_can_use_synthetic_empty_position_catalog(self) -> None:
        with self.repo.connect() as conn:
            person = dict(
                conn.execute("SELECT * FROM personnel ORDER BY rowid LIMIT 1").fetchone()
            )
        wb = Workbook()
        ws = wb.active
        ws.title = "Personnel"
        ws.append(list(PERSONNEL_HEADERS))
        row = [""] * len(PERSONNEL_HEADERS)
        row[PERSONNEL_HEADERS.index("personnel_no")] = person["personnel_no"]
        row[PERSONNEL_HEADERS.index("action")] = "update"
        row[PERSONNEL_HEADERS.index("company")] = "شرکت نمونه fallback"
        ws.append(row)
        wa = wb.create_sheet("Assignments")
        wa.append(list(ASSIGNMENT_HEADERS))
        out = io.BytesIO()
        wb.save(out)

        preview, _ = preview_xlsx(self.repo, out.getvalue(), "synthetic-fallback.xlsx")
        self.assertTrue(preview["can_apply"], preview["errors"])
        self.assertEqual(preview["summary"]["updated_people"], 1)
        self.assertEqual(preview["summary"]["assignment_moves"], 0)


if __name__ == "__main__":
    unittest.main()
