import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from sazmanhr.api_client import ApiClient, ApiError
from sazmanhr.database import PermissionDenied, Repository
from sazmanhr.demo_data import create_demo_seed
from sazmanhr.server import ApiServer


class MovementHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=Path(self.temp.name)/"hrm.sqlite"
        create_demo_seed(self.db)
        self.repo=Repository(self.db)
        self.owner=self.repo.create_user("super.one","سوپر ادمین","Super!Admin1500","owner",must_change_password=False)
        self.hr=self.repo.create_user("hr.admin","ادمین منابع انسانی","HrAdmin!Pass1500","admin",must_change_password=False)

    def tearDown(self): self.temp.cleanup()

    def test_hr_admin_can_move_but_cannot_restore_delete_or_manage_users(self):
        self.repo.require(self.hr,"manage_movements")
        self.repo.require(self.hr,"backup")
        for permission in ("restore","delete_personnel","manage_users","manage_security","reverse_movements"):
            with self.assertRaises(PermissionDenied): self.repo.require(self.hr,permission)
        for permission in ("restore","delete_personnel","manage_users","manage_security","reverse_movements"):
            self.repo.require(self.owner,permission)

    def test_movement_preserves_assignment_history_and_audit(self):
        person=self.repo.get_person(self.repo.list_personnel(limit=1)["items"][0]["id"])
        old_assignment=person["assignment"]["assignment_id"] if person["assignment"] else None
        result=self.repo.register_personnel_movement(person["id"],{
            "movement_type":"transfer","effective_date":"1405/07/01","order_no":"12345","order_date":"1405/06/25",
            "reason":"انتقال سازمانی","organizational_unit":"دفتر برنامه‌ریزی","position_code":"P-HIST-001",
            "position_title":"کارشناس برنامه‌ریزی","actual_location":"ستاد","status":"شاغل","row_version":person["row_version"],
        },self.hr["id"])
        self.assertEqual(result["person"]["organizational_unit"],"دفتر برنامه‌ریزی")
        history=self.repo.list_personnel_movements(person["id"])
        self.assertEqual(len(history),1); self.assertEqual(history[0]["order_no"],"12345")
        with self.repo.connect() as conn:
            if old_assignment:
                old=conn.execute("SELECT end_date FROM personnel_assignments WHERE id=?",(old_assignment,)).fetchone()
                self.assertEqual(old[0],"1405/07/01")
            active=conn.execute("SELECT COUNT(*) FROM personnel_assignments WHERE person_id=? AND end_date=''",(person["id"],)).fetchone()[0]
            total=conn.execute("SELECT COUNT(*) FROM personnel_assignments WHERE person_id=?",(person["id"],)).fetchone()[0]
        self.assertEqual(active,1); self.assertGreaterEqual(total,2); self.assertTrue(self.repo.verify_audit_chain())

    def test_latest_movement_can_be_reversed_without_erasing_event(self):
        person=self.repo.get_person(self.repo.list_personnel(limit=1)["items"][0]["id"])
        original=(person["organizational_unit"],person["position_code"],person["position_title"])
        moved=self.repo.register_personnel_movement(person["id"],{
            "movement_type":"position_change","effective_date":"1405/08/01","organizational_unit":"واحد جدید",
            "position_code":"P-NEW-800","position_title":"پست جدید","row_version":person["row_version"]},self.owner["id"])
        reversed_result=self.repo.reverse_personnel_movement(moved["movement"]["id"],"اصلاح حکم",self.owner["id"])
        current=reversed_result["person"]
        self.assertEqual((current["organizational_unit"],current["position_code"],current["position_title"]),original)
        self.assertTrue(reversed_result["movement"]["is_reversed"])
        self.assertEqual(reversed_result["movement"]["reversal_reason"],"اصلاح حکم")

    def test_movement_api_and_static_web_are_same_origin(self):
        web=Path(self.temp.name)/"web"; web.mkdir(); (web/"index.html").write_text("<html>HRM WEB TEST</html>",encoding="utf-8")
        server=ApiServer(("127.0.0.1",0),self.repo,web_root=web); thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        base=f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with urlopen(base+"/",timeout=3) as response:
                self.assertIn(b"HRM WEB TEST",response.read())
                self.assertIn("default-src 'self'",response.headers["Content-Security-Policy"])
            client=ApiClient(base); client.login("hr.admin","HrAdmin!Pass1500")
            person=client.request("GET","/api/personnel",query={"limit":1})["items"][0]
            detail=client.request("GET",f"/api/personnel/{person['id']}")
            bypass=dict(detail); bypass["organizational_unit"]="دور زدن تاریخچه"
            with self.assertRaisesRegex(ApiError,"ثبت جابه‌جایی"):
                client.request("POST","/api/personnel",bypass)
            created=client.request("POST",f"/api/personnel/{person['id']}/movements",{
                "movement_type":"unit_change","effective_date":"1405/09/01","organizational_unit":"وب تست",
                "position_code":"P-WEB-1","position_title":"کارشناس وب","row_version":detail["row_version"]})
            history=client.request("GET",f"/api/personnel/{person['id']}/movements")
            self.assertEqual(history["items"][0]["id"],created["movement"]["id"])
            with self.assertRaises(ApiError):
                client.request("POST",f"/api/movements/{created['movement']['id']}/reverse",{"reason":"غیرمجاز"})
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)

if __name__ == "__main__": unittest.main()
