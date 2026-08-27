"""Generate a small, synthetic database for tests and public CI builds.

The records in this module are intentionally fictional. Production data is
injected into the Windows builder from a path outside the Git repository.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import sqlite3
from pathlib import Path

from .config import PRODUCT_ID, SCHEMA_GENERATION
from .database import Repository, canonical, utc_now


DEMO_PERSONNEL_COUNT = 12
DEMO_CHART_PAGE_COUNT = 3


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_demo_seed(target: Path, *, overwrite: bool = False) -> dict[str, object]:
    """Create a deterministic seed containing no real people or identifiers."""
    target = Path(target).resolve()
    if target.exists() and not overwrite:
        raise FileExistsError(f"Demo seed already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.unlink(missing_ok=True)

    with contextlib.closing(sqlite3.connect(target)) as connection:
        connection.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.executemany(
            "INSERT INTO metadata(key,value) VALUES(?,?)",
            (("product_id", PRODUCT_ID), ("schema_generation", SCHEMA_GENERATION)),
        )
        connection.commit()

    repository = Repository(target)
    now = utc_now()
    with repository.write() as connection:
        for index in range(1, DEMO_PERSONNEL_COUNT + 1):
            page_no = ((index - 1) % DEMO_CHART_PAGE_COUNT) + 1
            connection.execute(
                """INSERT INTO personnel(
                    id,personnel_no,first_name,last_name,full_name,gender,
                    organizational_unit,position_code,position_title,
                    employment_group,employment_subtype,status,activity_area,
                    actual_location,company,chart_page_no,chart_node_id,extra_json,
                    row_version,updated_at,updated_by
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    f"demo-person-{index:03d}",
                    f"DEMO-{index:04d}",
                    "کارمند",
                    f"آزمایشی {index:02d}",
                    f"کارمند آزمایشی {index:02d}",
                    "آزمایشی",
                    f"واحد نمونه {page_no}",
                    f"DEMO-POS-{index:03d}",
                    "پست نمونه",
                    "داده ساختگی",
                    "آزمون CI",
                    "فعال",
                    "ستاد نمونه",
                    "محل نمونه",
                    "شرکت نمونه",
                    page_no,
                    f"demo-node-{page_no}",
                    canonical({"synthetic": True}),
                    1,
                    now,
                    None,
                ),
            )

        for page_no in range(1, DEMO_CHART_PAGE_COUNT + 1):
            connection.execute(
                """INSERT INTO chart_pages(
                    page_no,title,approved_fixed_posts,approved_named_posts,
                    approved_total_posts,extra_json,row_version,updated_at,updated_by
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (page_no, f"صفحه آزمایشی {page_no}", 4, 0, 4,
                 canonical({"synthetic": True}), 1, now, None),
            )
            connection.execute(
                """INSERT INTO chart_nodes(
                    id,page_no,node_json,row_version,updated_at,updated_by
                ) VALUES(?,?,?,?,?,?)""",
                (
                    f"demo-node-{page_no}",
                    page_no,
                    canonical({
                        "id": f"demo-node-{page_no}",
                        "title": f"واحد نمونه {page_no}",
                        "x": 120,
                        "y": 80,
                        "width": 240,
                        "height": 90,
                        "synthetic": True,
                    }),
                    1,
                    now,
                    None,
                ),
            )

        widgets = (
            ("demo-welcome", "خوش‌آمدید", "text", {"text": "داده کاملاً ساختگی برای آزمون"}, 1),
            ("demo-sync", "همگام‌سازی", "text", {"text": "تغییرات همه مدیران ثبت می‌شود"}, 2),
        )
        for widget_id, title, widget_type, config, position in widgets:
            connection.execute(
                """INSERT INTO dashboard_widgets(
                    id,title,widget_type,config_json,position,is_enabled,
                    row_version,updated_at,updated_by
                ) VALUES(?,?,?,?,?,1,1,?,NULL)""",
                (widget_id, title, widget_type, canonical(config), position, now),
            )
        connection.execute(
            "INSERT OR REPLACE INTO metadata(key,value) VALUES('dataset_kind','synthetic-demo')"
        )

    with repository.connect() as connection:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        users = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        sessions = connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    if integrity != "ok" or users or sessions:
        raise RuntimeError("Generated demo database did not pass safety validation.")

    manifest: dict[str, object] = {
        "kind": "synthetic-demo",
        "contains_real_personnel": False,
        "contains_accounts": False,
        "contains_sessions": False,
        "personnel": DEMO_PERSONNEL_COUNT,
        "chart_pages": DEMO_CHART_PAGE_COUNT,
        "database_sha256": file_sha256(target),
    }
    target.with_name("manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest
