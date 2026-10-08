"""Private transactional state and content-addressed evidence."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
        dfd = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(dfd)
        finally: os.close(dfd)
    finally:
        tmp.unlink(missing_ok=True)


class Store:
    def __init__(self, root=None):
        self.root = Path(root or os.environ.get("SKILLOBS_STATE", Path.home() / ".local/state/skill-observatory")).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        self.db_path = self.root / "state.sqlite3"
        with self.connect() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS entities(kind TEXT,id TEXT,data TEXT,PRIMARY KEY(kind,id));
            CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,hash TEXT NOT NULL,data TEXT NOT NULL,created_at TEXT);
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,run_id TEXT NOT NULL,status TEXT,lease_until REAL DEFAULT 0,attempts INTEGER DEFAULT 0,reason_code TEXT,created_at TEXT);
            CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY CHECK(id=1),data TEXT);
            """)
            db.execute("INSERT OR IGNORE INTO settings VALUES(1,?)", (json.dumps({"locale":"zh-CN","timezone":"Asia/Shanghai","paused":False,"scopes":[],"automatic_review":True,"auto_promote":False}),))
        os.chmod(self.db_path, 0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=30000")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback(); raise
        finally: db.close()

    def put(self, kind, value, db=None):
        def write(d):
            d.execute("INSERT INTO entities VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET data=excluded.data", (kind,value["id"],canonical(value).decode()))
        if db is not None: write(db)
        else:
            with self.connect() as d: write(d)
        return value

    def get(self, kind, id, db=None):
        def read(d):
            r=d.execute("SELECT data FROM entities WHERE kind=? AND id=?",(kind,id)).fetchone()
            return json.loads(r[0]) if r else None
        if db is not None: return read(db)
        with self.connect() as d: return read(d)

    def list(self, kind):
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT data FROM entities WHERE kind=? ORDER BY rowid DESC",(kind,))]

    def settings(self, update=None):
        with self.connect() as db:
            current=json.loads(db.execute("SELECT data FROM settings WHERE id=1").fetchone()[0])
            if update:
                current.update(update); db.execute("UPDATE settings SET data=? WHERE id=1",(canonical(current).decode(),))
            return current

    def artifact(self, data):
        h=digest(data); p=self.root/"artifacts"/h
        if not p.exists(): atomic_write(p,data)
        elif digest(p.read_bytes())!=h: raise ValueError("ARTIFACT_CORRUPT")
        return h

    def read_artifact(self, h):
        if len(h)!=64 or any(c not in "0123456789abcdef" for c in h): raise ValueError("INVALID_ARTIFACT_ID")
        b=(self.root/"artifacts"/h).read_bytes()
        if digest(b)!=h: raise ValueError("ARTIFACT_CORRUPT")
        return b

    def lease(self, seconds=120):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
            # Unknown model side effects are never replayed after lease expiry.
            db.execute("UPDATE jobs SET status='hold',reason_code='INTERRUPTED_ATTEMPT' WHERE status='running' AND lease_until<?",(time.time(),))
            if not row: return None
            db.execute("UPDATE jobs SET status='running',lease_until=?,attempts=attempts+1 WHERE id=?",(time.time()+seconds,row['id']))
            return dict(row)

    def jobs(self):
        with self.connect() as db: return [dict(r) for r in db.execute("SELECT * FROM jobs ORDER BY created_at DESC")]
