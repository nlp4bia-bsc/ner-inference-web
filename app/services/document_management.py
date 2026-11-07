"""Owner-only retained-document quota, persistent upload history and content erasure."""

import json
import shutil
import time

from app.auth.sessions import require_live
from app.errors import ServiceError
from app.permissions.policies import require_owner, user
from app.persistence.job_locks import job_lock
from app.storage import directory_bytes


def retained_count(connection, owner, now):
    return connection.execute(
        """SELECT count(*) FROM upload_ledger l JOIN jobs j ON j.id=l.job_id
           WHERE l.owner_user_id=? AND l.state='STORED'
           AND j.status NOT IN ('EXPIRED','DELETED')
           AND (j.expires_at IS NULL OR j.expires_at>?)""",
        (owner, now),
    ).fetchone()[0]


def quota(database, account):
    with database.connect() as connection:
        tier = connection.execute(
            "SELECT access_tier FROM users WHERE id=?", (account["id"],)
        ).fetchone()
        limit = {"STANDARD": 100, "EXTENDED": 1000, "UNLIMITED": None}[tier[0]]
        occupied = retained_count(connection, account["id"], time.time())
        uploaded = connection.execute(
            "SELECT count(*) FROM upload_ledger WHERE owner_user_id=?", (account["id"],)
        ).fetchone()[0]
    return {
        "occupied": occupied,
        "limit": limit,
        "remaining": max(0, limit - occupied) if limit is not None else None,
        "total_uploaded": uploaded,
    }


def upload_history(database, account, offset=0, limit=50, state=None, job_id=None):
    now = time.time()
    conditions, parameters = ["owner_user_id=?"], [account["id"]]
    if state:
        conditions.append("state=?")
        parameters.append(state)
    if job_id:
        conditions.append("job_id=?")
        parameters.append(job_id)
    where = " AND ".join(conditions)
    query = """WITH history AS (
      SELECT l.*,CASE WHEN l.state='STORED' AND
        (j.id IS NULL OR j.status='EXPIRED' OR j.expires_at<=?) THEN 'EXPIRED'
        ELSE l.state END AS effective_state
      FROM upload_ledger l LEFT JOIN jobs j ON j.id=l.job_id
    ), visible AS (SELECT id,owner_user_id,job_id,document_id,filename,language,size_bytes,
      uploaded_at,effective_state AS state,removed_at FROM history) """
    with database.connect() as connection:
        rows = connection.execute(
            query
            + f"SELECT * FROM visible WHERE {where} ORDER BY uploaded_at DESC,id DESC LIMIT ? OFFSET ?",  # nosec B608
            [now, *parameters, limit, offset],
        ).fetchall()
        total = connection.execute(
            query + f"SELECT count(*) FROM visible WHERE {where}",  # nosec B608
            [now, *parameters],
        ).fetchone()[0]
    return {
        "items": [{k: row[k] for k in row.keys() if k != "owner_user_id"} for row in rows],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


def delete_documents(service, token, document_id=None, *, document_ids=None):
    identities = (
        {document_id}
        if document_id is not None
        else set(document_ids)
        if document_ids is not None
        else None
    )
    if identities == set():
        raise ServiceError("Select at least one document.", 422)
    account = user()
    job = require_owner(service.db.get(token))
    with job_lock(service.settings, job["id"]):
        with service.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            require_live(connection, account, service.settings)
            current = dict(
                connection.execute(
                    "SELECT * FROM jobs WHERE id=? AND owner_user_id=?", (job["id"], account["id"])
                ).fetchone()
            )
            if current["status"] in ("EXPIRED", "DELETED"):
                if current["status"] == "DELETED":
                    return {"deleted": 0, "quota": quota(service.db, account)}
                raise ServiceError(
                    "Results have expired and downloads are no longer available.", 410
                )
            rows = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM documents WHERE job_id=?", (job["id"],)
                )
            ]
            selected = [
                row for row in rows if identities is None or row["document_id"] in identities
            ]
            if identities is not None and {row["document_id"] for row in selected} != identities:
                raise ServiceError("Document not found.", 404)
            selected = [row for row in selected if row["status"] != "DELETED"]
            if not selected:
                return {"deleted": 0, "quota": quota(service.db, account)}
            root = service.storage.job(job["id"])
            for row in selected:
                (root / "input" / row["filename"]).unlink(missing_ok=True)
                for suffix in ("", ".building"):
                    directory = root / "published" / (row["document_id"] + suffix)
                    if directory.exists():
                        shutil.rmtree(directory)
                connection.execute(
                    "UPDATE documents SET status='DELETED',annotation_count=0,entities_by_label='{}',statistics='{}',error_code=NULL,updated_at=? WHERE job_id=? AND document_id=?",
                    (time.time(), job["id"], row["document_id"]),
                )
                connection.execute(
                    "UPDATE upload_ledger SET state='DELETED',removed_at=? WHERE job_id=? AND document_id=? AND owner_user_id=?",
                    (time.time(), job["id"], row["document_id"], account["id"]),
                )
            for name in ("output", "building", "viewer"):
                if (root / name).exists():
                    shutil.rmtree(root / name)
            for name in ("worker-summary.json", "worker-summary.tmp"):
                (root / name).unlink(missing_ok=True)
            remaining = connection.execute(
                "SELECT count(*) FROM documents WHERE job_id=? AND status!='DELETED'", (job["id"],)
            ).fetchone()[0]
            status = current["status"]
            payload = json.loads(current["payload"])
            if not remaining:
                status = "DELETED"
                service.storage.delete(job["id"])
            elif status in ("COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED"):
                if connection.execute(
                    "SELECT 1 FROM documents WHERE job_id=? AND status='ANNOTATED' LIMIT 1",
                    (job["id"],),
                ).fetchone():
                    status = "QUEUED"
                    payload["repackage_only"] = True
                else:
                    status = "FAILED"
            connection.execute(
                """UPDATE jobs SET status=?,stage=?,payload=?,summary=NULL,error_summary=NULL,
                   content_version=content_version+1,storage_bytes=?,updated_at=?,
                   processed_documents=(SELECT count(*) FROM documents WHERE job_id=jobs.id AND status='ANNOTATED'),
                   attempts=CASE WHEN ?='QUEUED' THEN 0 ELSE attempts END,
                   reserved_bytes=CASE WHEN ?='DELETED' THEN 0 ELSE reserved_bytes END
                   WHERE id=?""",
                (
                    status,
                    "PREPARING_DOWNLOADS" if status == "QUEUED" else status,
                    json.dumps(payload),
                    directory_bytes(root),
                    time.time(),
                    status,
                    status,
                    job["id"],
                ),
            )
            if status == "DELETED":
                connection.execute(
                    "UPDATE jobs SET completed_at=?,expires_at=?,expired_at=? WHERE id=?",
                    (time.time(), time.time(), time.time(), job["id"]),
                )
            elif status == "QUEUED":
                size = connection.execute(
                    "SELECT COALESCE(sum(size_bytes),0) FROM documents WHERE job_id=? AND status!='DELETED'",
                    (job["id"],),
                ).fetchone()[0]
                connection.execute(
                    "UPDATE jobs SET reserved_bytes=? WHERE id=?",
                    (service.db.reservation(size), job["id"]),
                )
            service.db.event(connection, job["id"], "DOCUMENTS_DELETED", time.time())
    return {"deleted": len(selected), "quota": quota(service.db, account)}


def delete_all_documents(service):
    account = user()
    with service.db.connect() as connection:
        identities = [
            row[0]
            for row in connection.execute(
                "SELECT id FROM jobs WHERE owner_user_id=? AND status NOT IN ('DELETED','EXPIRED')",
                (account["id"],),
            )
        ]
    deleted = 0
    for identity in identities:
        try:
            deleted += delete_documents(service, identity)["deleted"]
        except ServiceError as exc:
            if exc.status not in (404, 410):
                raise
    return {"deleted": deleted, "quota": quota(service.db, account)}


def delete_selected_documents(service, documents):
    """Authorize the whole selection, then erase once per project/generation."""
    groups = {}
    for row in documents:
        groups.setdefault(row.job_id, set()).add(row.document_id)
    account = user()
    resolved = {}
    # No mutation if the selection contains a foreign project or unknown document.
    for identity, selected in groups.items():
        job = require_owner(service.db.get(identity))
        with service.db.connect() as connection:
            require_live(connection, account, service.settings)
            available = {
                row[0]
                for row in connection.execute(
                    "SELECT document_id FROM documents WHERE job_id=?", (job["id"],)
                )
            }
        if not selected <= available:
            raise ServiceError("Document not found.", 404)
        resolved.setdefault(job["id"], set()).update(selected)
    deleted = 0
    for identity, selected in resolved.items():
        try:
            deleted += delete_documents(service, identity, document_ids=selected)["deleted"]
        except ServiceError as exc:
            if exc.status not in (404, 410):
                raise
    return {"deleted": deleted, "quota": quota(service.db, account)}
