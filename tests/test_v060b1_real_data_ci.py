from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from cryptography.fernet import Fernet
from openpyxl import Workbook

from ci.real_data_bundle import BundleError, create_encrypted_bundle, decrypt_bundle
from ci.validate_v060b1_real_data import RealDataContract, validate_real_data


def _visible_text_values(value: object, *, field_name: str = ""):
    """Yield report text that can carry PII, excluding cryptographic digests."""
    if isinstance(value, dict):
        for name, item in value.items():
            if name.endswith("_sha256"):
                continue
            yield from _visible_text_values(item, field_name=name)
    elif isinstance(value, list):
        for item in value:
            yield from _visible_text_values(item, field_name=field_name)
    elif isinstance(value, str):
        yield value


def _sha256_values(value: object):
    if isinstance(value, dict):
        for name, item in value.items():
            if name.endswith("_sha256") and isinstance(item, str):
                yield item
            else:
                yield from _sha256_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _sha256_values(item)


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
    """Exercise the real topology: 1356 people, 590 enrichments and 185 assignments.

    The approved 536/32/568 chart counts live in the Enterprise target and are
    intentionally not manufactured as rows in the named-position workbook.
    """
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
            *([str(number), "ناحیه آزمایشی"] for number in range(767, 1357)),
        ],
    )
    _save_book(
        source / "اکسل پست با نام.xlsx",
        [
            ["شماره پست سازمانی", "عنوان پست", "شماره پرسنلی", "نوع پست"],
            *([
                f"P{number:04d}", "عنوان آزمایشی", str(number),
                "بانام ایثار" if number <= 32 else "بانام",
            ] for number in range(1, 186)),
            ["P1356", "ردیف قدیمی", "1356", "0"],
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
                RealDataContract(
                    personnel=3, county_enrichments=1, active_named_positions=1,
                    ignored_legacy_type_zero=0, fixed=0, named=1, total=1,
                    page_16_total=24,
                ),
            )
            self.assertEqual(result["staging"]["personnel"], 3)
            self.assertTrue(result["production_shadow"]["rollback_verified"])
            self.assertTrue(result["production_shadow"]["replay_verified"])
            serialized = output.read_text(encoding="utf-8")
            payload = json.loads(serialized)
            visible_report_text = "\n".join(_visible_text_values(payload))
            for private_value in ("آرش", "بهار", "پویان", "111", "222", "333", "P1"):
                self.assertNotIn(private_value, visible_report_text)
            digests = list(_sha256_values(payload))
            self.assertGreaterEqual(len(digests), 3)
            self.assertTrue(all(re.fullmatch(r"[0-9a-f]{64}", digest) for digest in digests))
            self.assertFalse(payload["privacy"]["raw_identifiers"])
            self.assertFalse(payload["privacy"]["plaintext_artifact"])

    def test_privacy_scan_does_not_treat_digest_coincidence_as_pii(self):
        digest_with_short_private_number = "a" * 20 + "111" + "b" * 41
        safe_payload = {
            "status": "pass",
            "encrypted_bundle_sha256": digest_with_short_private_number,
        }
        self.assertNotIn("111", "\n".join(_visible_text_values(safe_payload)))
        self.assertEqual(list(_sha256_values(safe_payload)), [digest_with_short_private_number])

        leaked_payload = {**safe_payload, "message": "raw national identifier 111 leaked"}
        self.assertIn("111", "\n".join(_visible_text_values(leaked_payload)))

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
            self.assertEqual(result["source_contract"]["county_enrichments"], 590)
            self.assertEqual(result["source_contract"]["active_named_positions"], 185)
            self.assertEqual(result["source_contract"]["ignored_legacy_type_zero"], 1)
            self.assertEqual(result["staging"]["positions"], 185)
            self.assertEqual(result["production_shadow"]["named_position_assignments"], 185)
            self.assertEqual(result["production_shadow"]["postflight"]["approved_total_posts"], 568)
            self.assertEqual(result["reconciliation"]["errors"], 0)
            self.assertTrue(result["production_shadow"]["rollback_verified"])
            self.assertTrue(result["production_shadow"]["replay_verified"])

    def test_chart_capacity_is_not_compared_to_source_assignment_rows(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            bundle = root / "data.enc"
            key_file = root / "key.txt"
            create_encrypted_bundle(_approved_fixture(root), bundle, key_file)
            result = validate_real_data(
                bundle, key_file.read_bytes().strip(), root / "summary.json",
                RealDataContract(
                    personnel=3, county_enrichments=1, active_named_positions=1,
                    ignored_legacy_type_zero=0,
                    fixed=536, named=32, total=568, page_16_total=24,
                ),
            )
            self.assertEqual(result["staging"]["positions"], 1)
            self.assertEqual(result["approved_contract"]["total_posts"], 568)
            self.assertNotIn("FIXED_POSITION_COUNT_MISMATCH", result["reconciliation"]["issue_codes"])
            self.assertNotIn("NAMED_POSITION_COUNT_MISMATCH", result["reconciliation"]["issue_codes"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
