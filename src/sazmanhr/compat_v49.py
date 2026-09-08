"""Compatibility view for the exact SazmanHR v4.9.0 frontend.

The compatibility layer never makes the old local application database the
source of truth.  It projects the current central Repository into the JSON
contracts expected by the locked v4.9 frontend, while supplemental read-only
UI datasets live inside the same server-side SQLite database.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

from . import __version__
from .database import Repository, utc_now

V49_DATASET_NAMES = frozenset({
    "initial-data",
    "position-catalog",
    "placement-models",
    "person-education",
    "person-details",
    "service-history",
    "training-history",
    "vacancy-audit",
    "gender-map",
})

_NO_SYNTHETIC_FALLBACK = object()

# Public CI/install databases intentionally contain no private v4.9 payloads.
# The locked frontend still requires these JSON contracts to exist.  Return
# structurally safe, PII-free values only when the database is explicitly
# marked synthetic and the compatibility store is completely empty.
_SYNTHETIC_V49_FALLBACKS: dict[str, Any] = {
    "initial-data": {
        "summary": {},
        "app": {"version": "4.9.0"},
        "change_log": [],
        "changelog": [],
        "people": [],
        "slides": [],
    },
    "position-catalog": {"positions": []},
    "placement-models": {
        # v4.9 mutates these two page maps unconditionally during startup.
        "org79PptTree": {
            "7": {"parent": {}},
            "10": {"parent": {}},
        },
        "ORG97_ACTIVITY_POST_PLACEMENTS": {},
        "ORG99_VERIFIED_MODEL": {"pages": {}},
        "ORG101_VERIFIED_MODEL": {"pages": {}},
        "ORG102_HEAD_MODEL": {"pages": {}},
        "ORG104_HEAD_MODEL": {"pages": {}},
        "ORG121_PLACEMENTS": {},
        "ORG152_ROLE_NODES": [],
        "ORG152_CORRECTIONS": {},
        "ORG153_PEOPLE": {},
    },
    "person-education": {"meta": {"categories": []}, "byPersonId": {}},
    "person-details": {},
    "service-history": {"meta": {"record_count": 0}, "byPersonnelNo": {}},
    "training-history": {"meta": {"records": 0}, "byPersonnelNo": {}},
    "vacancy-audit": [],
    "gender-map": {},
}


def _synthetic_dataset_fallback(repo: Repository, name: str) -> Any:
    with repo.connect() as conn:
        synthetic = conn.execute(
            """SELECT 1 FROM metadata
               WHERE key IN ('seed_mode','dataset_kind') AND value='synthetic-demo'
               LIMIT 1"""
        ).fetchone()
        protected = conn.execute(
            """SELECT 1 FROM metadata
               WHERE key IN ('ui_v49_reference_version','ui_v49_private_manifest_sha256')
               LIMIT 1"""
        ).fetchone()
        compat_count = int(conn.execute("SELECT COUNT(*) FROM ui_compat_datasets").fetchone()[0])
    if not synthetic or protected or compat_count != 0:
        return _NO_SYNTHETIC_FALLBACK
    value = _SYNTHETIC_V49_FALLBACKS.get(name, _NO_SYNTHETIC_FALLBACK)
    if value is _NO_SYNTHETIC_FALLBACK:
        return value
    # Match json.loads(payload_json): callers receive a fresh mutable object.
    return json.loads(json.dumps(value, ensure_ascii=False))


def legacy_permissions(repo: Repository, user: dict[str, Any]) -> dict[str, bool]:
    current = repo.permissions_for(user)
    return {
        "edit_data": bool({"edit_personnel", "manage_movements"} & current),
        "view_history": "view_audit" in current,
        "backup_restore": "backup" in current,
        "manage_users": "manage_users" in current,
        # The reference UI owns this visual permission.  The central service
        # deliberately does not implement a remote shutdown route.
        "shutdown": False,
    }


def legacy_user(repo: Repository, user: dict[str, Any]) -> dict[str, Any]:
    result = dict(user)
    result.update({
        "full_name": str(user.get("display_name", "")),
        "active": bool(user.get("is_active", 0)),
        "must_change": bool(user.get("must_change_password", 0)),
        "title": str(user.get("title", "") or ""),
        "phone": str(user.get("phone", "") or ""),
        "permissions": legacy_permissions(repo, user),
    })
    return result


def load_dataset(repo: Repository, name: str) -> Any:
    if name not in V49_DATASET_NAMES:
        raise KeyError("مجموعه داده در فهرست مجاز رابط 4.9 نیست.")
    with repo.connect() as conn:
        row = conn.execute(
            "SELECT payload_json FROM ui_compat_datasets WHERE name=?", (name,)
        ).fetchone()
    if not row:
        fallback = _synthetic_dataset_fallback(repo, name)
        if fallback is not _NO_SYNTHETIC_FALLBACK:
            return fallback
        raise KeyError(f"مجموعه داده رابط 4.9 بارگذاری نشده است: {name}")
    return json.loads(row[0])


def dataset_catalog(repo: Repository) -> list[dict[str, Any]]:
    with repo.connect() as conn:
        rows = conn.execute(
            "SELECT name,sha256,size_bytes,record_count,imported_at FROM ui_compat_datasets ORDER BY name"
        ).fetchall()
    return [dict(row) for row in rows]


def _legacy_person(row: dict[str, Any]) -> dict[str, Any]:
    try:
        extra = json.loads(row.get("extra_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        extra = {}
    if not isinstance(extra, dict):
        extra = {}
    extra.pop("_legacy_index", None)
    # Source extras first, live normalized fields last: edits and movements on
    # the central server therefore win over the immutable migration payload.
    person = dict(extra)
    person.update({
        "id": row.get("id", ""),
        "personnel_no": row.get("personnel_no", ""),
        "name": row.get("first_name", ""),
        "last_name": row.get("last_name", ""),
        "full_name": row.get("full_name", ""),
        "gender": row.get("gender", ""),
        "organizational_unit": row.get("organizational_unit", ""),
        "position_code": row.get("position_code", ""),
        "position_title": row.get("position_title", ""),
        "employment_group": row.get("employment_group", ""),
        "employment_subtype": row.get("employment_subtype", ""),
        "status": row.get("status", ""),
        "activity_area": row.get("activity_area", ""),
        "actual_location": row.get("actual_location", ""),
        "company": row.get("company", ""),
        "current_chart_page_v421": extra.get("current_chart_page_v421") or row.get("chart_page_no") or 0,
    })
    return person


def _legacy_slide(page: dict[str, Any]) -> dict[str, Any]:
    try:
        extra = json.loads(page.get("extra_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        extra = {}
    if not isinstance(extra, dict):
        extra = {}
    slide = dict(extra)
    slide.update({
        "page": int(page["page_no"]),
        "title": page.get("title", ""),
        "approved_fixed_posts": page.get("approved_fixed_posts"),
        "approved_named_posts": page.get("approved_named_posts"),
        "approved_total_posts": page.get("approved_total_posts"),
        "nodes": page.get("nodes", []),
        "lines": page.get("lines", []),
    })
    return slide


def build_bootstrap(repo: Repository) -> dict[str, Any]:
    """Build the v4.9 bootstrap shape from live central data.

    The old ``initial-data`` document is used only for presentation/audit
    metadata.  Personnel and chart objects are reconstructed from current
    normalized SQLite rows so the compatibility UI cannot become a stale copy.
    """
    try:
        reference = load_dataset(repo, "initial-data")
    except KeyError:
        reference = {}
    if not isinstance(reference, dict):
        reference = {}

    with repo.connect() as conn:
        people_rows = [dict(row) for row in conn.execute(
            "SELECT * FROM personnel ORDER BY rowid"
        ).fetchall()]
        page_rows = [dict(row) for row in conn.execute(
            "SELECT * FROM chart_pages ORDER BY page_no"
        ).fetchall()]
        node_rows = conn.execute(
            "SELECT page_no,node_json FROM chart_nodes ORDER BY page_no,rowid"
        ).fetchall()
        line_rows = conn.execute(
            "SELECT page_no,line_json FROM chart_lines ORDER BY page_no,rowid"
        ).fetchall()

    nodes: dict[int, list[Any]] = {}
    lines: dict[int, list[Any]] = {}
    for row in node_rows:
        nodes.setdefault(int(row["page_no"]), []).append(json.loads(row["node_json"]))
    for row in line_rows:
        lines.setdefault(int(row["page_no"]), []).append(json.loads(row["line_json"]))
    for page in page_rows:
        no = int(page["page_no"])
        page["nodes"] = nodes.get(no, [])
        page["lines"] = lines.get(no, [])

    people = [_legacy_person(row) for row in people_rows]
    slides = [_legacy_slide(row) for row in page_rows]

    summary = dict(reference.get("summary") or {})
    employment = Counter(str(p.get("employment_group", "") or "").strip() for p in people)
    formal = employment.get("رسمی", 0)
    named = sum(1 for p in people if bool(p.get("named_post")))
    hold = sum(1 for p in people if bool(p.get("is_hold_position")))
    page_one = next((s for s in slides if int(s.get("page", 0)) == 1), {})
    summary.update({
        "formal_count": formal,
        "nonofficial_count": max(0, len(people) - formal),
        "total_count": len(people),
        "named_count": named,
        "hold_count": hold,
        "pages": len(slides),
        "approved_posts_total": int(page_one.get("approved_total_posts") or 0),
        "approved_fixed_posts": int(page_one.get("approved_fixed_posts") or 0),
        "approved_named_posts_legacy": int(page_one.get("approved_named_posts") or 0),
        "nonofficial_groups": {
            key: count for key, count in employment.items() if key and key != "رسمی"
        },
        "generated_at": utc_now(),
    })

    app = dict(reference.get("app") or {})
    app.setdefault("title", "سامانه هوشمند معاونت منابع انسانی")
    app.setdefault("organization", "شرکت توزیع نیروی برق استان کرمانشاه")
    # Keep frontend identity explicit while exposing the actual backend release.
    app["version"] = "4.9.0"
    app["enterprise_backend_version"] = __version__

    with repo.connect() as conn:
        import_rows = conn.execute(
            """SELECT b.id,b.source_name,b.mode,b.summary_json,b.created_at,u.username,u.display_name
               FROM import_batches b LEFT JOIN users u ON u.id=b.created_by
               ORDER BY b.created_at DESC,b.id DESC LIMIT 50"""
        ).fetchall()
        try:
            monthly_rows = conn.execute(
                """SELECT person_id,personnel_no,assignment_type,target_page,target_node_id,reason,batch_id
                   FROM ui_monthly_assignments ORDER BY personnel_no,person_id"""
            ).fetchall()
        except Exception:
            # Read compatibility for databases that have not yet applied migration 9.
            monthly_rows = []
    import_history: list[dict[str, Any]] = []
    for row in import_rows:
        try:
            import_summary = json.loads(row["summary_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            import_summary = {}
        if not isinstance(import_summary, dict):
            import_summary = {}
        import_history.append({
            "batch_id": row["id"],
            "filename": row["source_name"],
            "actor": row["display_name"] or row["username"] or "سامانه",
            "applied_at": row["created_at"],
            "summary": import_summary,
            "backup_file": str(import_summary.get("backup") or import_summary.get("backup_file") or ""),
            "sha256": str(import_summary.get("sha256") or import_summary.get("source_digest") or ""),
        })

    return {
        "summary": summary,
        "people": people,
        "slides": slides,
        "app": app,
        "change_log": list(reference.get("change_log") or []),
        "changelog": list(reference.get("changelog") or []),
        "import_history": import_history,
        "monthly_assignments": ([dict(row) for row in monthly_rows]
                                if monthly_rows else list(reference.get("monthly_assignments") or [])),
    }


def health(repo: Repository) -> dict[str, Any]:
    with repo.connect() as conn:
        people_count = int(conn.execute("SELECT COUNT(*) FROM personnel").fetchone()[0])
        slide_count = int(conn.execute("SELECT COUNT(*) FROM chart_pages").fetchone()[0])
        duplicate_ids = int(conn.execute(
            "SELECT COUNT(*) FROM (SELECT id FROM personnel GROUP BY id HAVING COUNT(*)>1)"
        ).fetchone()[0])
        duplicate_personnel_numbers = int(conn.execute(
            "SELECT COUNT(*) FROM (SELECT personnel_no FROM personnel GROUP BY personnel_no HAVING COUNT(*)>1)"
        ).fetchone()[0])
        missing_unit = int(conn.execute(
            "SELECT COUNT(*) FROM personnel WHERE TRIM(organizational_unit)=''"
        ).fetchone()[0])
        missing_position = int(conn.execute(
            "SELECT COUNT(*) FROM personnel WHERE TRIM(position_code)='' AND TRIM(position_title)=''"
        ).fetchone()[0])
        audit_count = int(conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0])
        diagnostic_count = int(conn.execute(
            "SELECT COUNT(*) FROM operational_events WHERE level IN ('ERROR','CRITICAL')"
        ).fetchone()[0])
        last_backup = conn.execute(
            "SELECT created_at FROM backup_catalog WHERE integrity_ok=1 ORDER BY id DESC LIMIT 1"
        ).fetchone()
        schema = conn.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()
        migrations = conn.execute(
            "SELECT version,name FROM schema_migrations ORDER BY version DESC LIMIT 1"
        ).fetchone()
    quality = repo.analytics().get("quality", {})
    return {
        "people_count": people_count,
        "slide_count": slide_count,
        "duplicate_ids": duplicate_ids,
        "duplicate_personnel_numbers": duplicate_personnel_numbers,
        "missing_unit": missing_unit,
        "missing_position": missing_position,
        "audit_chain_ok": bool(repo.verify_audit_chain()),
        "audit_count": audit_count,
        "diagnostic_count": diagnostic_count,
        "last_backup_at": last_backup[0] if last_backup else "",
        "last_migration": f"{migrations['version']}:{migrations['name']}" if migrations else "",
        "source_of_truth": "sqlite",
        "schema_version": int(schema[0]) if schema else 0,
        "auth_schema_version": int(schema[0]) if schema else 0,
        "missing_gender": int(quality.get("missing_gender", 0) or 0),
        "missing_education": int(quality.get("missing_education", 0) or 0),
        "missing_age": int(quality.get("missing_age", 0) or 0),
    }


def history(repo: Repository, *, limit: int = 1500, q: str = "", username: str = "",
            action: str = "", from_value: str = "", to_value: str = "") -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 1500))
    clauses: list[str] = []
    params: list[Any] = []
    if q.strip():
        like = f"%{q.strip()}%"
        clauses.append("(a.action LIKE ? OR a.entity_type LIKE ? OR a.entity_id LIKE ? OR COALESCE(u.username,'') LIKE ?)")
        params.extend((like, like, like, like))
    if username.strip():
        clauses.append("u.username=? COLLATE NOCASE")
        params.append(username.strip())
    if action.strip():
        clauses.append("a.action=?")
        params.append(action.strip())
    if from_value.strip():
        clauses.append("a.occurred_at>=?")
        params.append(from_value.strip())
    if to_value.strip():
        clauses.append("a.occurred_at<=?")
        params.append(to_value.strip())
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    with repo.connect() as conn:
        rows = conn.execute(
            f"""SELECT a.id,a.occurred_at,u.username,u.display_name,a.action,a.entity_type,
                       a.entity_id,a.before_json,a.after_json,a.event_hash
                FROM audit_log a LEFT JOIN users u ON u.id=a.user_id
                {where} ORDER BY a.id DESC LIMIT ?""",
            (*params, limit),
        ).fetchall()
    result=[]
    for row in rows:
        details={}
        try:
            after=json.loads(row["after_json"] or "{}")
            if isinstance(after,dict): details={k:v for k,v in list(after.items())[:6]}
        except (TypeError,json.JSONDecodeError):
            pass
        result.append({
            "id": row["id"],
            "changed_at": row["occurred_at"],
            "username": row["username"] or "",
            "actor_name": row["display_name"] or row["username"] or "سامانه",
            "action": row["action"],
            "subject": f"{row['entity_type']} / {row['entity_id']}",
            "details": details,
            "entry_hash": row["event_hash"],
        })
    return result


def placement_reviews(repo: Repository) -> list[dict[str, Any]]:
    with repo.connect() as conn:
        rows = conn.execute(
            "SELECT rowid AS review_id,id,personnel_no,full_name,extra_json,updated_at FROM personnel ORDER BY rowid"
        ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        try:
            extra = json.loads(row["extra_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            extra = {}
        if not isinstance(extra, dict) or not extra.get("placement_review_required"):
            continue
        result.append({
            "id": int(row["review_id"]),
            "person_id": row["id"],
            "personnel_no": row["personnel_no"],
            "full_name": row["full_name"],
            "reason": str(extra.get("placement_review_reason") or "نیازمند بررسی جانمایی"),
            "created_at": str(extra.get("placement_review_created_at") or row["updated_at"] or ""),
        })
    return result


def resolve_placement_review(repo: Repository, review_id: int, actor_id: str) -> dict[str, Any]:
    now = utc_now()
    with repo.write() as conn:
        row = conn.execute("SELECT rowid,* FROM personnel WHERE rowid=?", (int(review_id),)).fetchone()
        if not row:
            raise KeyError("مورد بازبینی جانمایی پیدا نشد.")
        try:
            extra = json.loads(row["extra_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            extra = {}
        if not isinstance(extra, dict):
            extra = {}
        before = {
            "placement_review_required": bool(extra.get("placement_review_required")),
            "placement_review_reason": str(extra.get("placement_review_reason") or ""),
        }
        extra["placement_review_required"] = False
        extra["placement_review_reason"] = ""
        extra["placement_review_resolved_at"] = now
        extra["placement_review_resolved_by"] = actor_id
        new_version = int(row["row_version"]) + 1
        conn.execute(
            "UPDATE personnel SET extra_json=?,row_version=?,updated_at=?,updated_by=? WHERE id=?",
            (json.dumps(extra, ensure_ascii=False, sort_keys=True, separators=(",", ":")), new_version, now, actor_id, row["id"]),
        )
        repo._record(conn, actor_id, "placement_review_resolve", "personnel", row["id"], before,
                     {"placement_review_required": False}, new_version)
    return {"ok": True, "id": int(review_id), "person_id": row["id"]}


def record_client_log(repo: Repository, payload: dict[str, Any]) -> None:
    # Runtime Core already redacts common secret forms.  The server still keeps
    # only bounded diagnostic metadata and never request bodies or auth headers.
    safe={}
    for key,maxlen in (("kind",80),("message",2400),("stack",4800),("source",400),("page",120),("version",40)):
        value=str(payload.get(key,"") or "")[:maxlen]
        for needle in ("password", "authorization", "bearer ", "token", "secret"):
            if needle in value.lower():
                value="[REDACTED CLIENT DIAGNOSTIC]"
                break
        safe[key]=value
    safe["line"]=int(payload.get("line",0) or 0)
    safe["column"]=int(payload.get("column",0) or 0)
    repo.record_operational("ERROR", "v49-client", "client_error", safe.get("message") or safe.get("kind") or "client error", safe)
