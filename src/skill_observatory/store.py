"""Private transactional state and content-addressed evidence."""
from __future__ import annotations
import hashlib
import gzip
import fcntl
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


def list_projection(value):
    value=dict(value)
    if 'event_ids' in value:value['event_count']=len(value['event_ids'])
    return {k:v for k,v in value.items() if k not in {'event_ids','manifest','calls','evidence_ids','observation_ids','trials','arm_files','stdout','stderr','snapshot'}}


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
        self._progress = {}
        self._catalog_cache = {}
        # Hook processes open this ledger frequently. Migrations belong to a
        # schema transition, not every tool event (and not every read command).
        with self.connect() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
        if version == 3:
            return
        if version > 3:
            raise ValueError('DATABASE_SCHEMA_NEWER_THAN_RUNTIME')
        with self.connect() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS entities(kind TEXT,id TEXT,data TEXT,PRIMARY KEY(kind,id));
            CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,hash TEXT NOT NULL,data TEXT NOT NULL,created_at TEXT);
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,run_id TEXT NOT NULL,status TEXT,lease_until REAL DEFAULT 0,attempts INTEGER DEFAULT 0,reason_code TEXT,created_at TEXT);
            CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY CHECK(id=1),data TEXT);
            CREATE TABLE IF NOT EXISTS ledger_revision(id INTEGER PRIMARY KEY CHECK(id=1),value INTEGER NOT NULL);
            INSERT OR IGNORE INTO ledger_revision VALUES(1,0);
            """)
            columns={r[1] for r in db.execute('PRAGMA table_info(jobs)')}
            if 'eligible_at' not in columns:
                db.execute('ALTER TABLE jobs ADD COLUMN eligible_at REAL DEFAULT 0')
            db.execute('CREATE INDEX IF NOT EXISTS jobs_ready ON jobs(status,eligible_at,created_at)')
            for table in ('entities','events','jobs','settings'):
                for op in ('INSERT','UPDATE','DELETE'):
                    db.execute(f'CREATE TRIGGER IF NOT EXISTS revision_{table}_{op} AFTER {op} ON {table} BEGIN UPDATE ledger_revision SET value=value+1 WHERE id=1; END')
            db.execute("CREATE INDEX IF NOT EXISTS invocation_capability ON entities(kind,json_extract(data,'$.capability_id'))")
            db.execute("CREATE INDEX IF NOT EXISTS entity_run ON entities(kind,json_extract(data,'$.run_id'))")
            db.execute("CREATE INDEX IF NOT EXISTS entity_execution ON entities(kind,COALESCE(json_extract(data,'$.execution_session_id'),json_extract(data,'$.session_id')))")
            db.execute('CREATE INDEX IF NOT EXISTS events_created ON events(created_at,id)')
            db.execute('CREATE INDEX IF NOT EXISTS job_run ON jobs(run_id,status)')
            db.execute("INSERT OR IGNORE INTO settings VALUES(1,?)", (json.dumps({"locale":"zh-CN","timezone":"Asia/Shanghai","paused":False,"scopes":[],"automatic_review":True,"auto_promote":False}),))
            db.execute('PRAGMA user_version=3')
        os.chmod(self.db_path, 0o600)

    @contextmanager
    def connect(self):
        # An offline recovery owns EX on this file. Readers cannot keep an old
        # SQLite inode alive across its atomic replacement.
        with (self.root/'database.lock').open('a') as gate:
            fcntl.flock(gate,fcntl.LOCK_SH)
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
        if kind in {'skills','capability_catalog'}:self._catalog_cache.pop(kind,None)
        def write(d):
            d.execute("INSERT INTO entities VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET data=excluded.data WHERE entities.data!=excluded.data", (kind,value["id"],canonical(value).decode()))
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
        if kind in {'skills','capability_catalog'}:
            entry=self._catalog_cache.get(kind)
            if entry and time.monotonic()-entry[0]<1:return json.loads(entry[1])
        with self.connect() as db:
            result=[json.loads(r[0]) for r in db.execute("SELECT data FROM entities WHERE kind=? ORDER BY rowid DESC",(kind,))]
        if kind in {'skills','capability_catalog'}:self._catalog_cache[kind]=(time.monotonic(),json.dumps(result))
        return result

    def settings(self, update=None):
        with self.connect() as db:
            current=json.loads(db.execute("SELECT data FROM settings WHERE id=1").fetchone()[0])
            if update:
                current.update(update); encoded=canonical(current).decode()
                db.execute("UPDATE settings SET data=? WHERE id=1 AND data!=?",(encoded,encoded))
            return current

    def artifact(self, data):
        h=digest(data); p=self.root/"artifacts"/h
        if p.exists() or p.with_suffix('.gz').exists():
            if self.read_artifact(h)!=data:raise ValueError('ARTIFACT_CORRUPT')
        else: atomic_write(p,data)
        return h

    def read_artifact(self, h):
        if len(h)!=64 or any(c not in "0123456789abcdef" for c in h): raise ValueError("INVALID_ARTIFACT_ID")
        p=self.root/"artifacts"/h
        if p.is_symlink() or p.with_suffix('.gz').is_symlink():raise ValueError('ARTIFACT_NOT_REGULAR')
        try:
            # Maintenance publishes gzip before removing raw bytes. A reader
            # racing that unlink must retry the published representation.
            try:b=p.read_bytes()
            except FileNotFoundError:b=gzip.decompress(p.with_suffix('.gz').read_bytes())
        except (OSError,EOFError) as ex:raise ValueError('ARTIFACT_CORRUPT') from ex
        if digest(b)!=h: raise ValueError("ARTIFACT_CORRUPT")
        return b

    def event_data(self, data, db=None):
        """Read hot or losslessly archived bytes without changing event identity."""
        value=json.loads(data)
        if '_archive_event' not in value:return value
        def read(conn):
            row=conn.execute('SELECT raw_sha256,data FROM archive_event_payloads WHERE id=?',(value['_archive_event'],)).fetchone()
            if row is None:raise ValueError('ARCHIVE_EVENT_MISSING')
            try:raw=gzip.decompress(row['data'])
            except (OSError,EOFError) as ex:raise ValueError('ARCHIVE_EVENT_CORRUPT') from ex
            if digest(raw)!=row['raw_sha256']:raise ValueError('ARCHIVE_EVENT_CORRUPT')
            result=json.loads(raw)
            if result.get('id')!=value['_archive_event']:raise ValueError('ARCHIVE_EVENT_IDENTITY_MISMATCH')
            return result
        if db is not None:return read(db)
        with self.connect() as conn:return read(conn)

    def lease(self, seconds=120):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            # Legacy budget HOLDs had no dispatch. Preserve all admitted/unknown attempts.
            db.execute("""UPDATE jobs SET status='deferred',eligible_at=0
                WHERE status='hold' AND reason_code='DAILY_REVIEW_ATTEMPT_BUDGET_HOLD'
                AND NOT EXISTS(SELECT 1 FROM entities WHERE kind='review_attempts'
                    AND json_extract(data,'$.run_id')=jobs.run_id
                    AND json_extract(data,'$.admission_sha256') IS NOT NULL)""")
            db.execute("UPDATE jobs SET status='queued' WHERE status='deferred' AND eligible_at<=?",(time.time(),))
            # Unknown model side effects are never replayed after lease expiry.
            db.execute("UPDATE jobs SET status='hold',reason_code='INTERRUPTED_ATTEMPT' WHERE status='running' AND lease_until<?",(time.time(),))
            row=db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created_at,id LIMIT 1").fetchone()
            if not row: return None
            db.execute("UPDATE jobs SET status='running',lease_until=?,attempts=attempts+1 WHERE id=?",(time.time()+seconds,row['id']))
            return dict(row)

    def revision(self):
        with self.connect() as db:
            return db.execute('SELECT value FROM ledger_revision WHERE id=1').fetchone()[0]

    def page(self,kind,offset=0,limit=50,status=None,query=None):
        where='kind=?';args=[kind]
        if status:
            where+=" AND COALESCE(json_extract(data,'$.status'),json_extract(data,'$.state'))=?";args.append(status)
        if query:
            where+=' AND data LIKE ? ESCAPE \'\\\'';args.append('%'+query.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%')
        with self.connect() as db:
            total=db.execute('SELECT count(*) FROM entities WHERE '+where,args).fetchone()[0]
            rows=db.execute('SELECT data FROM entities WHERE '+where+' ORDER BY rowid DESC LIMIT ? OFFSET ?',[*args,limit,offset]).fetchall()
        return {'items':[json.loads(x[0]) for x in rows],'total':total,'offset':offset,'limit':limit}

    def entity_page(self,kind,offset,limit,status,query,stage,project,capability_id,canary,order,capability_kind,bucket=None):
        where='1=1' if kind=='jobs' else 'kind=?';args=[] if kind=='jobs' else [kind]
        for field,value in (('status',status),('cwd',project),('capability_id',capability_id),('kind',capability_kind)):
            if value and value!='all':
                if field=='status' and value=='held':value='hold'
                if kind=='jobs' and field=='status':where+=' AND status=?'
                elif field=='cwd':where+=" AND COALESCE(json_extract(data,'$.cwd'),json_extract(data,'$.origin.project'))=?"
                elif field=='status':where+=" AND COALESCE(json_extract(data,'$.status'),json_extract(data,'$.state'))=?"
                else:where+=f" AND json_extract(data,'$.{field}')=?"
                args.append(value)
        if query:
            where+=' AND '+('id || run_id' if kind=='jobs' else 'data')+" LIKE ? ESCAPE '\\'"
            args.append('%'+query.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%')
        if stage and stage!='all' and kind!='jobs':
            where+=" AND EXISTS(SELECT 1 FROM json_each(data,'$.stages') WHERE value=?)";args.append(stage)
        if canary in {'only','exclude'} and kind!='jobs':
            where+=" AND COALESCE(json_extract(data,'$.origin'),'')"+('=' if canary=='only' else '!=')+"'activation_canary'"
        if bucket and kind=='runs':
            # Mirrors the existing UI categories using the full job/review ledger.
            # Correlated lookups are indexed by run identity rather than first-page joins.
            expr="""CASE
              WHEN EXISTS(SELECT 1 FROM jobs j WHERE j.run_id=entities.id AND j.status IN ('hold','deferred'))
                OR EXISTS(SELECT 1 FROM entities r WHERE r.kind='reviews' AND json_extract(r.data,'$.run_id')=entities.id AND json_extract(r.data,'$.decision')='HOLD') THEN 'held'
              WHEN EXISTS(SELECT 1 FROM entities r WHERE r.kind='reviews' AND json_extract(r.data,'$.run_id')=entities.id AND json_extract(r.data,'$.status')='reviewed') THEN 'reviewed'
              WHEN EXISTS(SELECT 1 FROM jobs j WHERE j.run_id=entities.id AND j.status IN ('running','queued','waiting')) THEN 'running'
              WHEN json_extract(data,'$.status') IN ('dev_evaluating','final_evaluating') THEN 'running'
              WHEN json_extract(data,'$.status')='evidence_pending' THEN 'held'
              ELSE 'ready' END"""
            where+=' AND ('+expr+')=?';args.append(bucket)
        table='jobs' if kind=='jobs' else 'entities'
        sort='ASC' if order=='oldest' else 'DESC'
        with self.connect() as db:
            db.execute('BEGIN')
            total=db.execute('SELECT count(*) FROM '+table+' WHERE '+where,args).fetchone()[0]
            rows=db.execute(('SELECT *' if kind=='jobs' else 'SELECT data')+' FROM '+table+' WHERE '+where+' ORDER BY '+('created_at' if kind=='jobs' else "json_extract(data,'$.created_at')")+' '+sort+',rowid '+sort+' LIMIT ? OFFSET ?',[*args,limit,offset]).fetchall()
            revision=db.execute('SELECT value FROM ledger_revision WHERE id=1').fetchone()[0]
            items=[dict(r) if kind=='jobs' else json.loads(r[0]) for r in rows]
            if kind=='capability_catalog':
                from .capabilities import capability_projection
                items=[capability_projection(self,c,db) for c in items]
            if kind=='experiments':
                for value in items:
                    if value.get('state'):value['status']=value['state']
        return {'items':[list_projection(x) for x in items],'total':total,'offset':offset,'limit':limit,'revision':revision}

    def jobs(self):
        with self.connect() as db: return [dict(r) for r in db.execute("SELECT * FROM jobs ORDER BY created_at DESC")]
