"""Durable observation, attribution, reviews and recovery, without widening authority."""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import time
from .store import Store, atomic_write, canonical, digest, now

EVENTS = {"SessionStart","UserPromptSubmit","PreToolUse","PostToolUse","Stop","SessionEnd","SubagentStart","SubagentStop","Interrupt"}
TERMINAL = {"Stop","SessionEnd","SubagentStop","Interrupt"}
ORIGINS = {"user_run","review","candidate_dev","final_eval","activation_canary","maintenance"}
SENSITIVE = re.compile(r"(?i)(api[_-]?key|authorization|password|secret|access[_-]?token|refresh[_-]?token)")


def redact(v):
    if isinstance(v, dict): return {k: "[REDACTED]" if SENSITIVE.search(k) else redact(x) for k,x in v.items()}
    if isinstance(v, list): return [redact(x) for x in v]
    if isinstance(v,str):
        v=re.sub(r"(?i)bearer\s+[A-Za-z0-9._~-]+", "Bearer [REDACTED]",v)
        v=re.sub(r"\b(?:sk-|gh[pousr]_|github_pat_)[A-Za-z0-9_-]{12,}","[REDACTED]",v)
        v=re.sub(r"(?i)((?:api[_-]?key|password|access[_-]?token|secret)\s*[=:]\s*)[^\s,;]+",r"\1[REDACTED]",v)
        return v
    return v


def package_manifest(root):
    root=Path(root).resolve()
    if not (root/"SKILL.md").is_file(): raise ValueError("SKILL_ENTRY_MISSING")
    files={}
    for p in sorted(root.rglob("*")):
        if p.is_symlink(): raise ValueError("SYMLINK_OWNER_REQUIRED")
        if p.is_file() and not any(x in {".git","__pycache__",".venv","node_modules"} for x in p.relative_to(root).parts):
            if p.stat().st_size>8_000_000: raise ValueError("PACKAGE_FILE_TOO_LARGE")
            files[str(p.relative_to(root))]=digest(p.read_bytes())
    return {"files":files,"package_sha256":digest(canonical(files))}


def register(store, path, owner, source="user-owned", license=None):
    p=Path(path).resolve(); manifest=package_manifest(p)
    id="sk_"+digest(str(p).encode())[:24]
    s={"id":id,"name":p.name,"path":str(p),"owner":owner,"source":source,"license":license,"status":"observing","package_sha256":manifest['package_sha256'],"manifest":manifest,"created_at":now(),"auto_promote":False,"score":None,"missing":["independent_final_evidence"]}
    store.put("skills",s);return s


def spool(store, payload, source="codex-hook"):
    """Only declared scopes; hash excludes delivery time, and raw tool data stays out."""
    event=payload.get("hook_event_name",payload.get("event"))
    if event not in EVENTS: raise ValueError("UNSUPPORTED_EVENT")
    cwd=Path(payload.get("cwd") or ".").resolve()
    scopes=[Path(x).resolve() for x in store.settings().get("scopes",[])]
    if not any(cwd==s or s in cwd.parents for s in scopes): return {"status":"excluded","reason_code":"OUTSIDE_SCOPE"}
    origin=payload.get("origin","user_run")
    if origin not in ORIGINS: raise ValueError("INVALID_ORIGIN")
    body={k:payload.get(k) for k in ("session_id","turn_id","agent_id","parent_session_id","tool_use_id","tool_name","transcript_path") if payload.get(k) is not None}
    body.update(event=event,cwd=str(cwd),source=source,origin=origin)
    # Persist minimum metadata, not prompt, command or output. Bind original redacted
    # event hash for collision diagnosis; identities provided upstream win.
    body['input_sha256']=digest(canonical(redact(payload)))
    if source in {'codex-desktop','codex-cli','codex-subagent'} and payload.get('verified_attributions'):
        body['attributions']=payload['verified_attributions']
    for s in store.list('skills'):
        raw=canonical(payload).decode()
        if str(Path(s['path'])/'SKILL.md') in raw:
            body.setdefault('attributions',[]).append({"skill_id":s['id'],"package_sha256":s['package_sha256'],"attribution":"inferred"})
    identity={k:body.get(k) for k in ('source','session_id','turn_id','agent_id','tool_use_id','event','input_sha256')}
    body['id']='ev_'+digest(canonical(identity));body['created_at']=now()
    path=store.root/'spool'/f"{body['id']}.json"
    if not path.exists(): atomic_write(path,canonical(body))
    return {"status":"spooled","id":body['id']}


def ingest(store):
    count=0
    for p in sorted((store.root/'spool').glob('*.json')):
        try:
            b=p.read_bytes();e=json.loads(b)
            normalized={k:v for k,v in e.items() if k!='created_at'}; h=digest(canonical(normalized))
            with store.connect() as db:
                old=db.execute('SELECT hash FROM events WHERE id=?',(e['id'],)).fetchone()
                if old and old[0]!=h: raise ValueError('EVENT_ID_COLLISION')
                if not old:
                    db.execute('INSERT INTO events VALUES(?,?,?,?)',(e['id'],h,b.decode(),e['created_at']))
                    run_id='run_'+digest(canonical([e.get('source'),e.get('session_id'),e.get('turn_id') or 'turn_unknown',e.get('agent_id')]))[:32]
                    # SessionEnd has no turn_id: supplement the last observed run.
                    if e['event']=='SessionEnd' and not e.get('turn_id'):
                        rows=db.execute("SELECT data FROM entities WHERE kind='runs' ORDER BY rowid DESC").fetchall()
                        recent=next((json.loads(x[0]) for x in rows if json.loads(x[0]).get('session_id')==e.get('session_id') and json.loads(x[0]).get('agent_id')==e.get('agent_id')),None)
                        if recent:run_id=recent['id']
                    r=store.get('runs',run_id,db) or {"id":run_id,"session_id":e.get('session_id'),"turn_id":e.get('turn_id'),"agent_id":e.get('agent_id'),"origin":e['origin'],"created_at":e['created_at'],"event_ids":[],"status":"evidence_pending","outcome":"unverified","attributions":[],"missing":[]}
                    r['event_ids'].append(e['id']); r['last_event']=e['event'];r['updated_at']=e['created_at']
                    for a in e.get('attributions',[]):
                        if a not in r['attributions']: r['attributions'].append(a)
                    if not e.get('turn_id'): r['missing']=list(set(r['missing']+['UPSTREAM_TURN_ID_MISSING']))
                    if e['event']=='Interrupt': r['outcome']='partial'
                    if e['event'] in TERMINAL:
                        r['status']='ready';jid='job_'+run_id
                        db.execute("INSERT OR IGNORE INTO jobs(id,run_id,status,created_at) VALUES(?,?,'queued',?)",(jid,run_id,now()))
                        # A later SessionEnd must not create a second review or overwrite reviewed.
                        if store.get('reviews','rv_'+run_id,db): r['status']='reviewed'
                    store.put('runs',r,db)
                    count+=1
            p.unlink()
        except Exception as ex:
            atomic_write(store.root/'quarantine'/p.name,canonical({"reason_code":str(ex),"sha256":digest(p.read_bytes())}))
            p.rename(store.root/'quarantine'/('raw-'+p.name))
    return count


def process_one(store, reviewer=None):
    if store.settings().get('paused') or not store.settings().get('automatic_review'): return None
    job=store.lease()
    if not job:return None
    r=store.get('runs',job['run_id'])
    if reviewer:
        try:return reviewer.review(store,r)
        except Exception as ex:
            with store.connect() as db:db.execute("UPDATE jobs SET status='hold',reason_code=?,lease_until=0 WHERE id=?",(str(ex),job['id']))
            store.put('review_attempts',{'id':'failed_'+job['id']+'_'+str(job['attempts']),'run_id':r['id'],'status':'hold','reason_code':str(ex),'money':None,'tokens':None,'created_at':now()})
            return None
    # Deterministic evidence triage is explicitly not a model semantic review.
    # A schema-valid HOLD preserves interrupted/missing evidence without fabricating truth.
    eid=store.artifact(canonical(r))
    receipt={"id":"rv_"+r['id'],"created_at":now(),"schema_version":1,"review_id":"rv_"+r['id'],"run_id":r['id'],"skill_id":None,"skill_package_sha256":None,"attribution":"unknown","coverage":{"tools":"partial","outcome":"unverified"},"outcome":{"status":r['outcome'],"source":"runtime_only"},"findings":[],"decision":"HOLD","missing":list(set(r['missing']+['SEMANTIC_REVIEW_REQUIRED','OUTCOME_TRUTH_REQUIRED','ATTRIBUTION_UNKNOWN'])),"evidence_manifest_sha256":eid,"reviewer_version":"evidence-triage-v1","status":"triaged","reason_code":"SEMANTIC_REVIEW_REQUIRED"}
    with store.connect() as db:
        store.put('reviews',receipt,db); r['status']='triaged';store.put('runs',r,db)
        db.execute("UPDATE jobs SET status='hold',reason_code='SEMANTIC_REVIEW_REQUIRED',lease_until=0 WHERE id=?",(job['id'],))
    return receipt


def accept_review(store, receipt, reviewer):
    """Controlled verifier ingress; caller must be trusted, never a UI claim button."""
    from jsonschema import validate
    from importlib.resources import files
    schema=json.loads((files('skill_observatory')/'review.schema.json').read_text())
    validate(receipt,schema)
    r=store.get('runs',receipt['run_id'])
    if not r:raise ValueError('RUN_NOT_FOUND')
    if receipt['reviewer_version']!=reviewer:raise ValueError('REVIEWER_ID_MISMATCH')
    evidence=store.read_artifact(receipt['evidence_manifest_sha256'])
    if digest(canonical(r))!=digest(evidence):raise ValueError('REVIEW_EVIDENCE_DRIFT')
    if receipt['outcome']['source'] not in {'runtime_only','unknown'} or receipt['coverage']['outcome']=='verified' or receipt['outcome']['status']=='accepted':raise ValueError('INDEPENDENT_OUTCOME_RECEIPT_REQUIRED')
    if receipt['skill_id']:
        if not any(a['skill_id']==receipt['skill_id'] and a['package_sha256']==receipt['skill_package_sha256'] and a['attribution']==receipt['attribution'] for a in r['attributions']):raise ValueError('ATTRIBUTION_NOT_BOUND')
    receipt={**receipt,"id":receipt['review_id'],"status":"reviewed","created_at":now()}
    with store.connect() as db:
        store.put('reviews',receipt,db);r['status']='reviewed';store.put('runs',r,db)
        db.execute("UPDATE jobs SET status='completed',reason_code=NULL WHERE run_id=?",(r['id'],))
    return receipt


def tick(store,reviewer=None):
    from .transcripts import observe_session
    for selected in store.list('selected_sessions'):
        try:observe_session(store,selected['path'],selected['session_id'],selected['source'])
        except Exception as ex:store.put('adapter_errors',{'id':selected['id'],'reason_code':str(ex),'created_at':now()})
    n=ingest(store); review=process_one(store,reviewer)
    store.put('runtime',{"id":"daemon","status":"running","created_at":now(),"pid":os.getpid(),"heartbeat":time.time()})
    return {"ingested":n,"processed":bool(review)}


def state(store):
    d={k:store.list(k) for k in ('skills','runs','reviews','experiments','installations','environments')}
    d['jobs']=store.jobs();d['settings']=store.settings()
    reviewed=sum(x['status']=='reviewed' for x in d['reviews'])
    daemon=store.get('runtime','daemon') or {}
    d['metrics']={"observed_runs":len(d['runs']),"reviewed_runs":reviewed,"triaged_runs":sum(x['status']=='triaged' for x in d['reviews']),"global_coverage":None,"coverage_reason":"GLOBAL_DENOMINATOR_UNKNOWN","queued_jobs":sum(x['status']=='queued' for x in d['jobs']),"daemon_running":time.time()-daemon.get('heartbeat',0)<10,"window_start":min((x['created_at'] for x in d['runs']),default=None),"window_end":now()}
    d['capabilities']={"semantic_review":(store.get('runtime','reviewer') or {}).get('status','unconfigured'),"strong_sandbox":"requires_current_environment_receipt","promotion":"requires_frozen_independent_final","hook_trust":"native_review_required","recursive_gain":"UNVERIFIED"}
    return d
