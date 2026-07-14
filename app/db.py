import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class Repository:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def initialize(self) -> None:
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS tenants (
                tenant_id TEXT PRIMARY KEY, payload TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS knowledge_documents (
                tenant_id TEXT NOT NULL, url TEXT NOT NULL, title TEXT NOT NULL,
                text TEXT NOT NULL, fetched_at TEXT NOT NULL,
                PRIMARY KEY (tenant_id, url)
            );
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL,
                contact_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_conversation_contact
                ON conversations(tenant_id, contact_id, id);
            CREATE TABLE IF NOT EXISTS contacts (
                tenant_id TEXT NOT NULL, contact_id TEXT NOT NULL,
                profile TEXT NOT NULL DEFAULT '{}', last_intent TEXT,
                language TEXT, updated_at TEXT NOT NULL,
                PRIMARY KEY (tenant_id, contact_id)
            );
            CREATE TABLE IF NOT EXISTS processed_messages (
                tenant_id TEXT NOT NULL, message_id TEXT NOT NULL,
                response TEXT NOT NULL, created_at TEXT NOT NULL,
                PRIMARY KEY (tenant_id, message_id)
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL,
                contact_id TEXT, trace_id TEXT, event_type TEXT NOT NULL,
                payload TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_events_tenant
                ON events(tenant_id, event_type, created_at);
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL,
                trace_id TEXT NOT NULL, rating INTEGER NOT NULL,
                resolved INTEGER, comment TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
            );
            """)

    def upsert_tenant(self, tenant) -> dict:
        now, payload = utc_now(), tenant.model_dump_json()
        with self.connect() as db:
            row = db.execute("SELECT created_at FROM tenants WHERE tenant_id=?", (tenant.tenant_id,)).fetchone()
            created = row["created_at"] if row else now
            db.execute(
                "INSERT INTO tenants VALUES (?,?,?,?) ON CONFLICT(tenant_id) "
                "DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at",
                (tenant.tenant_id, payload, created, now),
            )
        return {**json.loads(payload), "created_at": created, "updated_at": now}

    def get_tenant(self, tenant_id: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT payload,created_at,updated_at FROM tenants WHERE tenant_id=?", (tenant_id,)).fetchone()
        return None if not row else {**json.loads(row["payload"]), "created_at": row["created_at"], "updated_at": row["updated_at"]}

    def replace_documents(self, tenant_id: str, documents) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM knowledge_documents WHERE tenant_id=?", (tenant_id,))
            db.executemany("INSERT INTO knowledge_documents VALUES (?,?,?,?,?)", [(tenant_id, d.url, d.title, d.text, d.fetched_at) for d in documents])

    def list_documents(self, tenant_id: str) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT url,title,text,fetched_at FROM knowledge_documents WHERE tenant_id=? ORDER BY url", (tenant_id,)).fetchall()
        return [dict(row) for row in rows]

    def save_message(self, tenant_id: str, contact_id: str, role: str, content: str) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO conversations (tenant_id,contact_id,role,content,created_at) VALUES (?,?,?,?,?)", (tenant_id, contact_id, role, content, utc_now()))

    def recent_messages(self, tenant_id: str, contact_id: str, limit: int = 12) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT role,content,created_at FROM conversations WHERE tenant_id=? AND contact_id=? ORDER BY id DESC LIMIT ?", (tenant_id, contact_id, limit)).fetchall()
        return [dict(row) for row in reversed(rows)]

    def get_contact(self, tenant_id: str, contact_id: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT profile,last_intent,language,updated_at FROM contacts WHERE tenant_id=? AND contact_id=?", (tenant_id, contact_id)).fetchone()
        return {"profile": {}, "last_intent": None, "language": None} if not row else {"profile": json.loads(row["profile"]), "last_intent": row["last_intent"], "language": row["language"], "updated_at": row["updated_at"]}

    def update_contact(self, tenant_id: str, contact_id: str, fields: dict, intent: str, language: str) -> dict:
        current = self.get_contact(tenant_id, contact_id)["profile"]
        current.update({key: value for key, value in fields.items() if value})
        with self.connect() as db:
            db.execute(
                "INSERT INTO contacts VALUES (?,?,?,?,?,?) ON CONFLICT(tenant_id,contact_id) "
                "DO UPDATE SET profile=excluded.profile,last_intent=excluded.last_intent,language=excluded.language,updated_at=excluded.updated_at",
                (tenant_id, contact_id, json.dumps(current, ensure_ascii=False), intent, language, utc_now()),
            )
        return current

    def get_processed(self, tenant_id: str, message_id: str | None) -> dict | None:
        if not message_id:
            return None
        with self.connect() as db:
            row = db.execute("SELECT response FROM processed_messages WHERE tenant_id=? AND message_id=?", (tenant_id, message_id)).fetchone()
        return json.loads(row["response"]) if row else None

    def save_processed(self, tenant_id: str, message_id: str | None, response: dict) -> None:
        if not message_id:
            return
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO processed_messages VALUES (?,?,?,?)", (tenant_id, message_id, json.dumps(response, ensure_ascii=False), utc_now()))

    def save_event(self, tenant_id: str, event_type: str, *, contact_id: str | None = None, trace_id: str | None = None, payload: dict | None = None) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO events (tenant_id,contact_id,trace_id,event_type,payload,created_at) VALUES (?,?,?,?,?,?)", (tenant_id, contact_id, trace_id, event_type, json.dumps(payload or {}, ensure_ascii=False), utc_now()))

    def save_feedback(self, tenant_id: str, trace_id: str, rating: int, resolved: bool | None, comment: str) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO feedback (tenant_id,trace_id,rating,resolved,comment,created_at) VALUES (?,?,?,?,?,?)", (tenant_id, trace_id, rating, resolved, comment, utc_now()))

    def analytics(self, tenant_id: str) -> dict:
        with self.connect() as db:
            event_rows = db.execute("SELECT event_type,COUNT(*) count FROM events WHERE tenant_id=? GROUP BY event_type", (tenant_id,)).fetchall()
            feedback = db.execute("SELECT AVG(rating) average_rating,AVG(resolved) resolution_rate,COUNT(*) count FROM feedback WHERE tenant_id=?", (tenant_id,)).fetchone()
            intents = db.execute("SELECT json_extract(payload,'$.intent') intent,COUNT(*) count FROM events WHERE tenant_id=? AND event_type='message_processed' GROUP BY intent ORDER BY count DESC", (tenant_id,)).fetchall()
        counts = {row["event_type"]: row["count"] for row in event_rows}
        total = counts.get("message_processed", 0)
        return {
            "messages_processed": total,
            "handoffs": counts.get("handoff", 0),
            "handoff_rate": round(counts.get("handoff", 0) / total, 3) if total else 0,
            "average_rating": round(feedback["average_rating"], 2) if feedback["average_rating"] is not None else None,
            "resolution_rate": round(feedback["resolution_rate"], 3) if feedback["resolution_rate"] is not None else None,
            "feedback_count": feedback["count"],
            "top_intents": [{"intent": row["intent"] or "general", "count": row["count"]} for row in intents],
        }
