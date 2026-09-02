from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from cryptography.fernet import Fernet
from openpyxl import Workbook

from ci.real_data_bundle import BundleError, create_encrypted_bundle, decrypt_bundle
from ci.validate_v060b1_real_data import RealDataContract, validate_real_data


def _save_book(path: Path, rows: list[list[str]]) -> None:
    book = Workbook()
    sheet = book.active
    sheet.title = "Sheet1"
    for row in rows:
        sheet.append(row)
    book.save(path)
    book.close()


def _approved_fixture(root: Path) -> Path:
    source = root / "approved-input"
    source.mkdir()
    header = [
        "شماره پرسنلی", "نام", "نام خانوادگی", "شماره ملی", "شماره پست سازمانی",
        "عنوان پست", "نوع استخدام", "واحد سازمانی", "محل خدمت",
    ]
    _save_book(source / "اکسل رسمی.xlsx", [header,
        ["1", "آرش", "آزمایشی", "111", "P1", "مدیر", "رسمی", "مرکز", "کرمانشاه"],
        ["2", "بهار", "آزمایشی", "222", "P2", "کارشناس", "رسمی", "مرکز", "کرمانشاه"],
    ])
    _save_book(source / "اکسل شرکتی - حجمی - پیمانکاری.xlsx", [header,
        ["3", "پویان", "آزمایشی", "333", "P3", "کارشناس", "شرکتی", "غرب", "کرمانشاه"],
    ])
    _save_book(source / "شهرستان.xlsx", [
        ["شماره پرسنلی", "واحد سازمانی"], ["3", "ناحیه غرب"],
    ])
    _save_book(source / "اکسل پست با نام.xlsx", [
        ["شماره پست سازمانی", "عنوان پست", "شماره پرسنلی", "نوع پست"],
        ["P1", "مدیر", "1", "بانام"],
    ])
    return source


def _approved_scale_fixture(root: Path) -> Path:
    """Structurally exercise the exact official 1356/568/32 contract."""
    source = root / "approved-scale-input"
    source.mkdir()
    header = [
        "شماره پرسنلی", "نام", "نام خانوادگی", "شماره ملی", "شماره پست سازمانی",
        "عنوان پست", "نوع استخدام", "واحد سازمانی", "محل خدمت",
    ]

    def person(number: int, employment: str) -> list[str]:
        return [
            str(number), "آزمایشی", f"رکورد{number}", f"{number:010d}",
            f"P{number:04d}", "عنوان آزمایشی", employment, "واحد آزمایشی", "کرمانشاه",
        ]

    _save_book(
        source / "اکسل رسمی.xlsx",
        [header, *(person(number, "رسمی") for number in range(1, 1001))],
    )
    _save_book(
        source / "اکسل شرکتی - حجمی - پیمانکاری.xlsx",
        [header, *(person(number, "شرکتی") for number in range(1001, 1357))],
    )
    _save_book(
        source / "شهرستان.xlsx",
        [
            ["شماره پرسنلی", "واحد سازمانی"],
            *([str(number), "ناحیه آزمایشی"] for number in range(1001, 1357)),
        ],
    )
    _save_book(
        source / "اکسل پست با نام.xlsx",
        [
            ["شماره پست سازمانی", "عنوان پست", "شماره پرسنلی", "نوع پست"],
            *(
                [
                    f"P{number:04d}", "عنوان آزمایشی", str(number),
                    "بانام ایثار" if number <= 32 else "ثابت",
                ]
                for number in range(1, 569)
            ),
        ],
    )
    return source


class V060B1RealDataCiTests(unittest.TestCase):
    def test_encrypted_bundle_round_trip_and_wrong_key_rejection(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            bundle = root / "data.enc"
            key_file = root / "private" / "key.txt"
            result = create_encrypted_bundle(_approved_fixture(root), bundle, key_file)
            self.assertEqual(result["source_file_count"], 4)
            extracted = root / "decrypted"
            manifest = decrypt_bundle(bundle, key_file.read_bytes().strip(), extracted)
            self.assertEqual(manifest["source_file_count"], 4)
            self.assertEqual(len(list(extracted.iterdir())), 4)
            with self.assertRaisesRegex(BundleError, "authentication failed"):
                decrypt_bundle(bundle, Fernet.generate_key(), root / "wrong-key")

    def test_encrypted_bundle_tamper_is_rejected_before_decryption(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            bundle = root / "data.enc"
            key_file = root / "key.txt"
            create_encrypted_bundle(_approved_fixture(root), bundle, key_file)
            raw = bytearray(bundle.read_bytes())
            raw[-1] ^= 1
            bundle.write_bytes(raw)
            with self.assertRaisesRegex(BundleError, "SHA-256"):
                decrypt_bundle(bundle, key_file.read_bytes().strip(), root / "decrypted")

    def test_full_real_data_cycle_emits_aggregate_only_evidence(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            bundle = root / "data.enc"
            key_file = root / "key.txt"
            create_encrypted_bundle(_approved_fixture(root), bundle, key_file)
            output = root / "summary.json"
            result = validate_real_data(
                bundle, key_file.read_bytes().strip(), output,
                RealDataContract(personnel=3, fixed=0, named=1, total=1, page_16_total=24),
            )
            self.assertEqual(result["staging"]["personnel"], 3)
            self.assertTrue(result["production_shadow"]["rollback_verified"])
            self.assertTrue(result["production_shadow"]["replay_verified"])
            serialized = output.read_text(encoding="utf-8")
            for private_value in ("آرش", "بهار", "پویان", "111", "222", "333", "P1"):
                self.assertNotIn(private_value, serialized)
            payload = json.loads(serialized)
            self.assertFalse(payload["privacy"]["raw_identifiers"])
            self.assertFalse(payload["privacy"]["plaintext_artifact"])

    def test_prepare_refuses_incomplete_approved_profile_set(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = _approved_fixture(root)
            (source / "شهرستان.xlsx").unlink()
            with self.assertRaisesRegex(BundleError, "exactly four"):
                create_encrypted_bundle(source, root / "data.enc", root / "key.txt")

    def test_exact_official_scale_contract_completes_rollback_and_replay(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            bundle = root / "data.enc"
            key_file = root / "key.txt"
            create_encrypted_bundle(_approved_scale_fixture(root), bundle, key_file)
            result = validate_real_data(
                bundle, key_file.read_bytes().strip(), root / "summary.json", RealDataContract()
            )
            self.assertEqual(result["approved_contract"]["personnel"], 1356)
            self.assertEqual(result["staging"]["positions"], 568)
            self.assertEqual(result["reconciliation"]["errors"], 0)
            self.assertTrue(result["production_shadow"]["rollback_verified"])
            self.assertTrue(result["production_shadow"]["replay_verified"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
