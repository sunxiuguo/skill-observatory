"""Small independent progress receipts, available when the ledger is unreadable."""
from __future__ import annotations
import json
import time
from pathlib import Path
from .store import atomic_write, canonical

LANES = ('daemon', 'review_worker', 'evolution_worker')


def read_lane(root, lane):
    if lane not in LANES:raise ValueError('INVALID_WORKER_LANE')
    path=Path(root)/'health'/(lane+'.json')
    try:
        if path.is_symlink():raise ValueError('HEALTH_NOT_REGULAR')
        return json.loads(path.read_text())
    except (OSError,ValueError):return {}


def write_lane(store,lane,**changes):
    row={**read_lane(store.root,lane),**changes,'id':lane}
    atomic_write(store.root/'health'/(lane+'.json'),canonical(row))
    return row


def failure(store,lane,reason):
    old=read_lane(store.root,lane);count=old.get('consecutive_failures',0)+1
    row=write_lane(store,lane,status='failed',reason_code=reason,
        consecutive_failures=count,last_failure_at=time.time(),
        first_failure_at=old.get('first_failure_at') or time.time())
    try:store.put('runtime_errors',{'id':lane,'reason_code':reason,'created_at':time.time()})
    except Exception:pass  # The independent receipt is authoritative for this failure.
    return min(60,2**min(count-1,6))


def snapshot(root,now=None):
    stamp=time.time() if now is None else now;workers=[]
    for lane in LANES:
        row=read_lane(root,lane)
        age=stamp-row['heartbeat'] if row.get('heartbeat') else None
        active_limit=row.get('deadline_at',0)
        stale=age is None or age>90
        if row.get('phase')!='idle' and active_limit:
            stale=stale or stamp>active_limit
        workers.append({**row,'heartbeat_age':age,'healthy':bool(row.get('last_success_at')) and not stale and row.get('status')!='failed'})
    return {'status':'healthy' if all(w['healthy'] for w in workers) else 'degraded',
        'workers':workers,'claim':'worker_progress_only_not_task_improvement'}
