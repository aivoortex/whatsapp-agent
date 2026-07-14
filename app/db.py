import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path


class Repository:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def initialize(self):
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS tenants (tenant_id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS knowledge_documents (tenant_id TEXT NOT NULL, url TEXT NOT NULL, title TEXT NOT NULL, text TEXT NOT NULL, fetched_at TEXT NOT NULL, PRIMARY KEY (tenant_id,url));
            CREATE TABLE IF NOT EXISTS conversations (id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL, contact_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL);
            """)

    def upsert_tenant(self, tenant):
        now = datetime.now(UTC).isoformat(); payload = tenant.model_dump_json()
        with self.connect() as db:
            row = db.execute("SELECT created_at FROM tenants WHERE tenant_id=?", (tenant.tenant_id,)).fetchone()
            created = row["created_at"] if row else now
            db.execute("INSERT INTO tenants VALUES (?,?,?,?) ON CONFLICT(tenant_id) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at", (tenant.tenant_id,payload,created,now))
        return {**json.loads(payload), "created_at":created, "updated_at":now}

    def get_tenant(self, tenant_id):
        with self.connect() as db:
            row=db.execute("SELECT payload,created_at,updated_at FROM tenants WHERE tenant_id=?",(tenant_id,)).fetchone()
        return None if not row else {**json.loads(row["payload"]),"created_at":row["created_at"],"updated_at":row["updated_at"]}

    def replace_documents(self, tenant_id, documents):
        with self.connect() as db:
            db.execute("DELETE FROM knowledge_documents WHERE tenant_id=?",(tenant_id,))
            db.executemany("INSERT INTO knowledge_documents VALUES (?,?,?,?,?)",[(tenant_id,d.url,d.title,d.text,d.fetched_at) for d in documents])

    def list_documents(self, tenant_id):
        with self.connect() as db:
            rows=db.execute("SELECT url,title,text,fetched_at FROM knowledge_documents WHERE tenant_id=? ORDER BY url",(tenant_id,)).fetchall()
        return [dict(r) for r in rows]

    def save_message(self, tenant_id, contact_id, role, content):
        with self.connect() as db:
            db.execute("INSERT INTO conversations (tenant_id,contact_id,role,content,created_at) VALUES (?,?,?,?,?)",(tenant_id,contact_id,role,content,datetime.now(UTC).isoformat()))

    def recent_messages(self, tenant_id, contact_id, limit=8):
        with self.connect() as db:
            rows=db.execute("SELECT role,content FROM conversations WHERE tenant_id=? AND contact_id=? ORDER BY id DESC LIMIT ?",(tenant_id,contact_id,limit)).fetchall()
        return [dict(r) for r in reversed(rows)]
