"""Offline, conservative ledger rebuild with intact source bytes and explicit lineage."""
from __future__ import annotations
import fcntl
import gzip
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import shutil
from contextlib import contextmanager
import uuid
from .store import Store,atomic_write,canonical,digest,now


@contextmanager
def _open(path):
    with tempfile.TemporaryDirectory(prefix='skillobs-backup-') as tmp:
        selected=path.resolve()
        if selected.suffix=='.gz':
            expanded=Path(tmp)/'backup.sqlite3'
            with gzip.open(selected,'rb') as source,expanded.open('wb') as target:shutil.copyfileobj(source,target,1024*1024)
            expanded.chmod(0o600);selected=expanded
        connection=sqlite3.connect('file:'+str(selected)+'?mode=ro',uri=True)
        try:yield connection
        finally:connection.close()


def rebuild(root,backup,apply=False):
    """Recover known missing entity keys; never replay events/model attempts.

    The independent prior backup is required for every index-visible lost key.
    Unexplained loss, invalid event hashes or a live WAL prevents replacement.
    """
    root=Path(root).resolve();source=root/'state.sqlite3';backup=Path(backup)
    if source.is_symlink() or backup.is_symlink() or not backup.is_file():raise ValueError('RECOVERY_SOURCE_NOT_REGULAR')
    if backup.resolve()==source:raise ValueError('INDEPENDENT_BACKUP_REQUIRED')
    lock=root/'database.lock'
    with lock.open('a') as handle:
        try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as ex:raise ValueError('MAINTENANCE_BUSY') from ex
        wal=source.with_name(source.name+'-wal')
        if wal.exists() and wal.stat().st_size:raise ValueError('RECOVERY_REQUIRES_QUIESCENT_DATABASE')
        source_sha=digest(source.read_bytes());backup_sha=digest(backup.read_bytes())
        with _open(backup) as prior:
            if prior.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]:raise ValueError('RECOVERY_BACKUP_NOT_HEALTHY')
            old={(k,i):v for k,i,v in prior.execute('SELECT kind,id,data FROM entities NOT INDEXED')}
        with _open(source) as damaged:
            checks=[r[0] for r in damaged.execute('PRAGMA integrity_check(32)')]
            indexed=set(damaged.execute('SELECT kind,id FROM entities INDEXED BY sqlite_autoindex_entities_1'))
            good={};bad=[]
            for rowid,kind,id,data in damaged.execute('SELECT rowid,kind,id,data FROM entities NOT INDEXED'):
                try:
                    value=json.loads(data)
                    if not isinstance(kind,str) or not isinstance(id,str) or not isinstance(value,dict) or value.get('id')!=id:raise ValueError()
                    good[kind,id]=data
                except (ValueError,TypeError):bad.append(rowid)
            missing=indexed-set(good)
            if not missing.issubset(old):raise ValueError('RECOVERY_MISSING_KEYS_WITHOUT_TRUSTED_BACKUP')
            if set(good)-indexed:raise ValueError('RECOVERY_INDEX_LOSS_REQUIRES_OWNER_REVIEW')
            for key in missing:good[key]=old[key]
            receipt={'schema_version':1,'created_at':now(),'source_sha256':source_sha,'backup_sha256':backup_sha,
                'integrity_before':checks,'invalid_rowids':bad,'restored_keys':[list(k) for k in sorted(missing)],
                'entity_count':len(good),'applied':False,'replayed_model_requests':0}
            if not apply:return receipt
            snapshots=root/'recovery';snapshots.mkdir(mode=0o700,exist_ok=True)
            original=snapshots/(source_sha+'.sqlite3')
            if not original.exists():atomic_write(original,source.read_bytes())
            with tempfile.TemporaryDirectory(prefix='rebuild-',dir=root) as tmp:
                fresh=Store(Path(tmp)/'state')
                with fresh.connect() as dest:
                    dest.execute('BEGIN IMMEDIATE')
                    dest.executemany('INSERT INTO entities(kind,id,data) VALUES(?,?,?)',[(k,i,v) for (k,i),v in good.items()])
                    for table in ('events','jobs','settings'):
                        cols=[r[1] for r in damaged.execute('PRAGMA table_info('+table+')')]
                        fields=','.join(cols);dest.execute('DELETE FROM '+table)
                        rows=damaged.execute('SELECT '+fields+' FROM '+table+' NOT INDEXED')
                        count=0
                        for row in rows:
                            if table=='events':
                                value=json.loads(row[cols.index('data')])
                                if '_archive_event' in value:
                                    archived=damaged.execute('SELECT raw_sha256,data FROM archive_event_payloads WHERE id=?',(value['_archive_event'],)).fetchone()
                                    if archived is None:raise ValueError('RECOVERY_ARCHIVE_MISSING')
                                    raw=gzip.decompress(archived[1])
                                    if digest(raw)!=archived[0]:raise ValueError('RECOVERY_ARCHIVE_CORRUPT')
                                    value=json.loads(raw)
                                if value.get('id')!=row[cols.index('id')]:raise ValueError('RECOVERY_EVENT_IDENTITY_MISMATCH')
                                expected=digest(canonical({k:v for k,v in value.items() if k!='created_at'}))
                                if expected!=row[cols.index('hash')]:raise ValueError('RECOVERY_EVENT_HASH_MISMATCH')
                            dest.execute('INSERT INTO '+table+'('+fields+') VALUES('+','.join('?' for _ in cols)+')',row);count+=1
                        receipt[table+'_count']=count
                    # Revision is a derived UI invalidation counter, not evidence.
                    # Recompute it instead of importing malformed counter pages.
                    previous=damaged.execute('SELECT value FROM ledger_revision WHERE id=1').fetchone()
                    revision=previous[0] if previous and type(previous[0]) is int and previous[0]>=0 else 0
                    dest.execute('UPDATE ledger_revision SET value=? WHERE id=1',(revision+1,))
                    # Keep optional durable ledgers, including once-only final consumption.
                    known={'entities','events','jobs','settings','ledger_revision'}
                    for table,sql in damaged.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
                        if table in known:continue
                        if not table.replace('_','').isalnum():raise ValueError('RECOVERY_TABLE_NAME_INVALID')
                        dest.execute(sql)
                        rows=damaged.execute('SELECT * FROM "'+table+'" NOT INDEXED');columns=len(rows.description)
                        dest.executemany('INSERT INTO "'+table+'" VALUES('+','.join('?' for _ in range(columns))+')',rows)
                with fresh.connect() as dest:
                    if dest.execute('PRAGMA integrity_check').fetchall()[0][0]!='ok':raise ValueError('RECOVERY_OUTPUT_INVALID')
                    orphan=dest.execute("SELECT count(*) FROM jobs j LEFT JOIN entities e ON e.kind='runs' AND e.id=j.run_id WHERE e.id IS NULL").fetchone()[0]
                    if orphan:raise ValueError('RECOVERY_ORPHAN_JOB')
                    dest.execute('PRAGMA wal_checkpoint(TRUNCATE)')
                if digest(source.read_bytes())!=source_sha or (wal.exists() and wal.stat().st_size):raise ValueError('RECOVERY_SOURCE_DRIFT')
                # Ensure no writer is using the old inode while swapping the validated file.
                gate=sqlite3.connect(source,timeout=.2)
                try:
                    gate.execute('BEGIN EXCLUSIVE')
                    if digest(source.read_bytes())!=source_sha:raise ValueError('RECOVERY_SOURCE_DRIFT')
                    os.replace(fresh.db_path,source)
                    fd=os.open(root,os.O_RDONLY)
                    try:os.fsync(fd)
                    finally:os.close(fd)
                finally:gate.rollback();gate.close()
            receipt.update(applied=True,after_sha256=digest(source.read_bytes()))
            atomic_write(snapshots/(uuid.uuid4().hex+'.json'),canonical(receipt))
            return receipt
