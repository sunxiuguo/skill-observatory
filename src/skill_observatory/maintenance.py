"""Bounded lossless maintenance; identity and replay barriers remain hot."""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime,timezone,timedelta
import fcntl
import gzip
import json
import os
from pathlib import Path
import time
from .store import atomic_write,canonical,digest,now


@contextmanager
def _lock(store):
    with (store.root/'maintenance.lock').open('a') as file:
        try:fcntl.flock(file,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as ex:raise ValueError('MAINTENANCE_BUSY') from ex
        yield


def storage_inventory(store):
    groups={}
    for name in ('artifacts','spool','quarantine','recovery'):
        files=[p for p in (store.root/name).glob('*') if p.is_file() and not p.is_symlink()]
        groups[name]={'files':len(files),'bytes':sum(p.stat().st_size for p in files)}
    with store.connect() as db:
        groups['database']={'bytes':store.db_path.stat().st_size,'page_count':db.execute('PRAGMA page_count').fetchone()[0],
            'free_pages':db.execute('PRAGMA freelist_count').fetchone()[0]}
        groups['wal']={'bytes':store.db_path.with_name('state.sqlite3-wal').stat().st_size if store.db_path.with_name('state.sqlite3-wal').exists() else 0}
    return {'groups':groups,'total_bytes':sum(x['bytes'] for x in groups.values()),'claim':'allocated_bytes_not_logical_evidence_count'}


def compress_artifacts(store,limit=1000,apply=False,min_age_seconds=0):
    if type(limit) is not int or not 1<=limit<=10000:raise ValueError('MAINTENANCE_LIMIT_INVALID')
    count=0;before=0;after=0
    with _lock(store):
        for p in sorted((store.root/'artifacts').glob('*')):
            if count>=limit:break
            if p.is_symlink() or not p.is_file() or len(p.name)!=64 or any(c not in '0123456789abcdef' for c in p.name):continue
            if time.time()-p.stat().st_mtime<min_age_seconds:continue
            raw=p.read_bytes()
            if digest(raw)!=p.name:raise ValueError('ARTIFACT_CORRUPT')
            packed=gzip.compress(raw,compresslevel=6,mtime=0)
            if len(packed)>=len(raw):continue
            if apply:
                target=p.with_suffix('.gz')
                if target.exists():
                    if target.is_symlink() or gzip.decompress(target.read_bytes())!=raw:raise ValueError('ARTIFACT_ARCHIVE_DRIFT')
                else:atomic_write(target,packed)
                if digest(gzip.decompress(target.read_bytes()))!=p.name:raise ValueError('ARTIFACT_ARCHIVE_CORRUPT')
                if digest(p.read_bytes())!=p.name:raise ValueError('ARTIFACT_SOURCE_DRIFT')
                p.unlink()
            count+=1;before+=len(raw);after+=len(packed)
    return {'operation':'artifact_compression','applied':apply,'files':count,'before_bytes':before,'after_bytes':after,'saved_bytes':before-after,'lossless':True}


def _cutoff(value):
    stamp=datetime.fromisoformat(value.replace('Z','+00:00'))
    if stamp.tzinfo is None or stamp>datetime.now(timezone.utc):raise ValueError('ARCHIVE_CUTOFF_INVALID')
    return stamp.astimezone(timezone.utc).isoformat()


def archive_events(store,before,limit=1000,apply=False):
    cutoff=_cutoff(before)
    if type(limit) is not int or not 1<=limit<=10000:raise ValueError('MAINTENANCE_LIMIT_INVALID')
    selected=[];skipped=0
    with _lock(store),store.connect() as db:
        db.execute('BEGIN IMMEDIATE' if apply else 'BEGIN')
        rows=db.execute("SELECT id,hash,data,created_at FROM events WHERE created_at<? AND json_type(data,'$._archive_event') IS NULL ORDER BY created_at,id LIMIT ?",(cutoff,min(limit*4,40000)))
        for row in rows:
            if len(selected)>=limit:break
            try:
                created=datetime.fromisoformat(row['created_at'].replace('Z','+00:00'))
                if created.tzinfo is None:raise ValueError()
                event=store.event_data(row['data'],db)
                execution=event.get('execution_session_id',event.get('agent_id') or event.get('session_id'))
                run_id='run_'+digest(canonical([execution,event.get('turn_id') or 'turn_unknown',event.get('agent_id')]))[:32]
                if event.get('event')=='SessionEnd' and not event.get('turn_id'):
                    envelope=store.get('session_envelopes',row['id'],db) or {};run_id=envelope.get('run_id')
                run=store.get('runs',run_id,db) if run_id else None
                if not run or not run.get('terminal') or row['id'] not in run.get('event_ids',[]):raise ValueError()
                if db.execute("SELECT 1 FROM jobs WHERE run_id=? AND status IN ('queued','running','deferred') LIMIT 1",(run_id,)).fetchone():raise ValueError()
                if db.execute("SELECT 1 FROM entities WHERE kind='experiments' AND json_extract(data,'$.run_id')=? AND COALESCE(json_extract(data,'$.state'),'unknown') NOT IN ('rejected','live_verified','rolled_back') LIMIT 1",(run_id,)).fetchone():raise ValueError()
                raw=row['data'].encode()
                if digest(canonical({k:v for k,v in event.items() if k!='created_at'}))!=row['hash']:raise ValueError('EVENT_HASH_MISMATCH')
                selected.append((row['id'],raw,row['created_at']))
            except (ValueError,TypeError,KeyError):skipped+=1
        if apply and selected:
            db.execute('CREATE TABLE IF NOT EXISTS archive_event_payloads(id TEXT PRIMARY KEY,raw_sha256 TEXT NOT NULL,data BLOB NOT NULL)')
            for id,raw,_ in selected:
                packed=gzip.compress(raw,compresslevel=6,mtime=0)
                if gzip.decompress(packed)!=raw:raise ValueError('EVENT_ARCHIVE_VERIFY_FAILED')
                db.execute('INSERT INTO archive_event_payloads VALUES(?,?,?)',(id,digest(raw),packed))
                db.execute('UPDATE events SET data=? WHERE id=? AND data=?',(canonical({'_archive_event':id}).decode(),id,raw.decode()))
        result={'operation':'event_archive','applied':apply,'cutoff':cutoff,'count':len(selected),'skipped_unfinished_or_unknown':skipped,
            'window_start':min((v[2] for v in selected),default=None),'window_end':max((v[2] for v in selected),default=None),
            'identity_manifest_sha256':digest(canonical([v[0] for v in selected])),'coverage':'selected_terminal_event_payloads_only','lossless':True,
            'global_denominator':None,'created_at':now()}
        if apply and selected:store.put('storage_archives',{'id':'archive_'+result['identity_manifest_sha256'][:32],**result},db)
    return result


def automatic_maintenance(store):
    settings=store.settings();policy=settings.get('storage_policy') or {}
    if policy.get('enabled') is not True:return None
    today=now()[:10];id='maintenance_'+today
    if store.get('storage_maintenance',id):return None
    days=policy.get('hot_days',30)
    if type(days) is not int or days<30:raise ValueError('RETENTION_REQUIRES_AT_LEAST_30_HOT_DAYS')
    cutoff=(datetime.now(timezone.utc)-timedelta(days=days)).isoformat()
    result={'id':id,'created_at':now(),'artifacts':compress_artifacts(store,limit=500,apply=True,min_age_seconds=7*86400),
        'events':archive_events(store,cutoff,limit=500,apply=True),'next_action':'next_utc_day','model_calls':0}
    store.put('storage_maintenance',result);return result


def compact_database(store,apply=False):
    before=store.db_path.stat().st_size
    if not apply:return {'operation':'database_compaction','applied':False,'before_bytes':before}
    from .health import read_lane
    for lane in ('daemon','review_worker','evolution_worker'):
        pid=read_lane(store.root,lane).get('pid')
        if pid:
            try:os.kill(pid,0)
            except ProcessLookupError:pass
            else:raise ValueError('COMPACTION_REQUIRES_STOPPED_SERVICE')
    with _lock(store),store.connect() as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('COMPACTION_REQUIRES_HEALTHY_LEDGER')
        checkpoint=db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
        if checkpoint[0]:raise ValueError('COMPACTION_BUSY')
        db.execute('VACUUM')
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('COMPACTION_READBACK_FAILED')
    return {'operation':'database_compaction','applied':True,'before_bytes':before,'after_bytes':store.db_path.stat().st_size}
