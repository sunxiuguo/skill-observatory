"""Durable observation, attribution, reviews and recovery, without widening authority."""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from datetime import datetime, timezone
from .store import Store, atomic_write, canonical, digest, now

EVENTS = {"SessionStart","UserPromptSubmit","PreToolUse","PostToolUse","Stop","SessionEnd","SubagentStart","SubagentStop","Interrupt"}
TERMINAL = {"Stop","SessionEnd","SubagentStop","Interrupt"}
ORIGINS = {"user_run","review","candidate_dev","final_eval","activation_canary","maintenance"}
SENSITIVE = re.compile(r"(?i)(api[_-]?key|private[_-]?key|credential|authorization|password|secret|access[_-]?token|refresh[_-]?token)")


def redact(v):
    if isinstance(v, dict): return {k: "[REDACTED]" if SENSITIVE.search(k) else redact(x) for k,x in v.items()}
    if isinstance(v, list): return [redact(x) for x in v]
    if isinstance(v,str):
        v=re.sub(r'-----BEGIN (?:[A-Z ]*PRIVATE KEY)-----.*?-----END (?:[A-Z ]*PRIVATE KEY)-----','[REDACTED PRIVATE KEY]',v,flags=re.S)
        v=re.sub(r'\b(?:xox[baprs]-[A-Za-z0-9-]{10,}|AKIA[A-Z0-9]{16}|AIza[A-Za-z0-9_-]{30,})','[REDACTED]',v)
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
    previous=store.get("skills",id) or {}
    s={"id":id,"name":p.name,"path":str(p),"owner":owner,"source":source,"license":license,"status":"observing","package_sha256":manifest['package_sha256'],"manifest":manifest,"created_at":previous.get("created_at",now()),"updated_at":now(),"auto_promote":False,"score":None,"missing":["independent_final_evidence"]}
    store.put("skills",s)
    from .capabilities import register_capability
    roots=store.settings().get('scopes',[])
    if roots:
        cap=register_capability(store,p,owner,kind='skill',scope=roots[0])
        s=store.get('skills',id)
    return s


def spool(store, payload, source="codex-hook"):
    """Only declared scopes; hash excludes delivery time, and raw tool data stays out."""
    event=payload.get("hook_event_name",payload.get("event"))
    if event not in EVENTS: raise ValueError("UNSUPPORTED_EVENT")
    cwd=Path(payload.get("cwd") or ".").resolve()
    scopes=[Path(x).resolve() for x in store.settings().get("scopes",[])]
    if not any(cwd==s or s in cwd.parents for s in scopes): return {"status":"excluded","reason_code":"OUTSIDE_SCOPE"}
    origin=payload.get("origin","user_run")
    if origin not in ORIGINS: raise ValueError("INVALID_ORIGIN")
    body={k:payload.get(k) for k in ("session_id","turn_id","agent_id","parent_session_id","root_session_id","tool_use_id","tool_name","transcript_path") if payload.get(k) is not None}
    body.update(event=event,cwd=str(cwd),source=source,origin=origin)
    body['execution_session_id']=payload.get('execution_session_id') or payload.get('agent_id') or payload.get('session_id')
    if payload.get('agent_id'):
        body['parent_session_id']=payload.get('parent_session_id') or (payload.get('session_id') if payload.get('session_id')!=payload.get('agent_id') else None)
    stamp=payload.get('occurred_at',payload.get('timestamp'))
    if stamp:
        try:
            parsed=datetime.fromisoformat(stamp.replace('Z','+00:00'))
            if parsed.tzinfo:body['occurred_at']=parsed.astimezone(timezone.utc).isoformat()
        except (ValueError,TypeError,AttributeError):pass
    if type(payload.get('source_sequence')) is int and payload['source_sequence']>=0:
        body['source_sequence']=payload['source_sequence']
    if source in {'codex-desktop','codex-cli','codex-subagent'} and payload.get('transcript_record_sha256'):
        body['transcript_record_sha256']=payload['transcript_record_sha256']
    # Persist minimum metadata, not prompt, command or output. Bind original redacted
    # event hash for collision diagnosis; identities provided upstream win.
    body['input_sha256']=digest(canonical(redact(payload)))
    # Only path-level facts from the current event. No transcript scan or execution.
    # Names visible in a prompt/tool catalog are not actual Skill use. Attribute
    # path mentions only to the current tool input, never every injected entry.
    raw=canonical(payload.get('tool_input',payload.get('tool_arguments',{}))).decode()
    for cap in store.list('capability_catalog'):
        entry=str(Path(cap['path'])/('SKILL.md' if cap['kind']=='skill' else 'command.json'))
        if entry in raw:
            body.setdefault('capability_observations',[]).append({'capability_id':cap['id'],'version_id':cap['version_id'],'stage':'mentioned'})
    if source in {'codex-desktop','codex-cli','codex-subagent'} and payload.get('verified_attributions'):
        body['attributions']=payload['verified_attributions']
    if source in {'codex-desktop','codex-cli','codex-subagent'} and payload.get('capability_observations'):
        body.setdefault('capability_observations',[]).extend(payload['capability_observations'])
    diagnostic=payload.get('diagnostic_fact')
    authorized=any(cwd==Path(s).resolve() or Path(s).resolve() in cwd.parents for s in store.settings().get('diagnostic_scopes',[]))
    if authorized and source in {'codex-desktop','codex-cli','codex-subagent'} and isinstance(diagnostic,dict):
        if set(diagnostic)=={'status','exit_code','reason_code'} and diagnostic['status']=='failed' and type(diagnostic['exit_code']) is int and diagnostic['exit_code']!=0 and diagnostic['reason_code'] in {'CLI_ARGUMENT_MISMATCH','TOOL_TIMEOUT','TOOL_EXIT_NONZERO'}:
            body['diagnostic_fact']=diagnostic
    for s in store.list('skills'):
        if str(Path(s['path'])/'SKILL.md') in raw:
            body.setdefault('attributions',[]).append({"skill_id":s['id'],"package_sha256":s['package_sha256'],"attribution":"inferred"})
    identity={k:body.get(k) for k in ('source','session_id','turn_id','agent_id','tool_use_id','event','input_sha256')}
    body['id']='ev_'+digest(canonical(identity));body['created_at']=now()
    path=store.root/'spool'/f"{body['id']}.json"
    if not path.exists(): atomic_write(path,canonical(body))
    return {"status":"spooled","id":body['id']}


def ingest(store,limit=512):
    count=0
    for p in sorted((store.root/'spool').glob('*.json'))[:limit]:
        try:
            b=p.read_bytes();e=json.loads(b)
            normalized={k:v for k,v in e.items() if k!='created_at'}; h=digest(canonical(normalized))
            with store.connect() as db:
                old=db.execute('SELECT hash,data FROM events WHERE id=?',(e['id'],)).fetchone()
                if old and old[0]!=h:
                    prior={k:v for k,v in store.event_data(old[1],db).items() if k!='created_at'}
                    # Older collectors omitted this derived field. Accept only an
                    # exact redelivery with the same fallback execution identity;
                    # keep the original durable bytes and reject every other drift.
                    legacy_equivalent=('execution_session_id' not in prior
                        and old[0]==digest(canonical(prior))
                        and canonical({**prior,'execution_session_id':prior.get('agent_id') or prior.get('session_id')})==canonical(normalized))
                    if not legacy_equivalent:raise ValueError('EVENT_ID_COLLISION')
                if old:
                    # Delivery timestamps are excluded from event identity. Use the
                    # first durable bytes for downstream evidence on redelivery.
                    e=store.event_data(old[1],db)
                if not old:
                    db.execute('INSERT INTO events VALUES(?,?,?,?)',(e['id'],h,b.decode(),e['created_at']))
                    if e['event'] in {'SubagentStart','SubagentStop'} and not e.get('agent_id'):
                        store.put('adapter_errors',{'id':e['id'],'reason_code':'UPSTREAM_CHILD_IDENTITY_MISSING','created_at':now()},db)
                        count+=1
                        p.unlink()
                        continue
                    execution=e.get('execution_session_id',e.get('agent_id') or e.get('session_id'))
                    run_id='run_'+digest(canonical([execution,e.get('turn_id') or 'turn_unknown',e.get('agent_id')]))[:32]
                    # Persist the terminal session envelope; insertion order is not chronology.
                    if e['event']=='SessionEnd' and not e.get('turn_id'):
                        store.put('session_envelopes',{'id':e['id'],'execution_session_id':execution,'agent_id':e.get('agent_id'),
                            'event_id':e['id'],'occurred_at':e.get('occurred_at'),'source':e['source'],'status':'terminal_turn_unknown',
                            'reason_code':'TRUSTED_TURN_ORDER_REQUIRED','created_at':e['created_at']},db)
                    if not (e['event']=='SessionEnd' and not e.get('turn_id')):
                        r=store.get('runs',run_id,db) or {"id":run_id,"session_id":execution,"execution_session_id":execution,"parent_session_id":e.get('parent_session_id'),"turn_id":e.get('turn_id'),"agent_id":e.get('agent_id'),"origin":e['origin'],"created_at":e['created_at'],"event_ids":[],"status":"evidence_pending","outcome":"unverified","attributions":[],"missing":[],"cwd":e.get("cwd")}
                        r.setdefault('sources',[])
                        if e['source'] not in r['sources']:r['sources'].append(e['source'])
                        if e['source']=='codex-subagent' and e.get('parent_session_id'):
                            r['parent_session_id']=e['parent_session_id'];r['root_session_id']=e.get('root_session_id')
                        r['event_ids'].append(e['id'])
                        event_time=e.get('occurred_at')
                        if event_time and (not r.get('last_source_at') or event_time>=r['last_source_at']):
                            r['last_event']=e['event'];r['last_source_at']=event_time
                        elif not r.get('last_event') or e['event'] in TERMINAL:r['last_event']=e['event']
                        if event_time:r['first_source_at']=min(event_time,r.get('first_source_at',event_time))
                        r['updated_at']=max(e['created_at'],r.get('updated_at',e['created_at']))
                        for a in e.get('attributions',[]):
                            if a not in r['attributions']: r['attributions'].append(a)
                        if not e.get('turn_id'): r['missing']=list(set(r['missing']+['UPSTREAM_TURN_ID_MISSING']))
                        if e['event']=='Interrupt': r['outcome']='partial'
                        if e['event'] in TERMINAL:
                            r['status']='ready';r['terminal']=True;jid='job_'+run_id
                            db.execute("INSERT OR IGNORE INTO jobs(id,run_id,status,created_at) VALUES(?,?,'queued',?)",(jid,run_id,now()))
                            # A later SessionEnd must not create a second review or overwrite reviewed.
                            prior=store.get('reviews','rv_'+run_id,db)
                            if prior:r['status']=prior['status']
                        store.put('runs',r,db)
                        if e.get('diagnostic_fact'):
                            facts=store.get('run_diagnostics',run_id,db) or {'id':run_id,'run_id':run_id,'steps':[],'coverage':'typed_tool_failures_only','goal':None,'success_criteria':None,'created_at':now()}
                            step={'event_id':e['id'],**e['diagnostic_fact']}
                            if step not in facts['steps']:facts['steps']=(facts['steps']+[step])[-24:]
                            store.put('run_diagnostics',facts,db)
                    count+=1
            if e.get('source')=='codex-hook' and e.get('transcript_path'):
                from .transcripts import track_hook_session
                cause_id='adapter_'+digest(canonical([e.get('execution_session_id'),e.get('transcript_path')]))[:32]
                error=store.get('adapter_errors',cause_id) or {}
                if error.get('eligible_at',0)<=time.time():
                    try:track_hook_session(store,e)
                    except (ValueError,OSError,KeyError) as ex:
                        reason=str(ex) if re.fullmatch(r'[A-Z0-9_:-]{1,160}',str(ex)) else type(ex).__name__
                        store.put('adapter_errors',{'id':cause_id,'reason_code':reason,'count':error.get('count',0)+1,
                            'first_seen_at':error.get('first_seen_at',now()),'created_at':now(),'eligible_at':time.time()+300,
                            'execution_session_id':e.get('execution_session_id')})
            # Idempotent usage ingress after an interrupted event commit.
            from .capabilities import record_usage
            for observation in e.get('capability_observations',[]):
                if e.get('session_id') and e.get('turn_id') and e.get('tool_use_id'):
                    try:
                        record_usage(store,{**observation,'session_id':e.get('execution_session_id',e.get('agent_id') or e['session_id']),'turn_id':e['turn_id'],
                            'cwd':e['cwd'],'invocation_id':e['tool_use_id'],'tool_use_id':e['tool_use_id'],
                            'source':e['source'],'event_id':e['id']+'_'+observation['capability_id']+'_'+observation['version_id']+'_'+observation['stage'],
                            'origin':e['origin'],'agent_id':e.get('agent_id'),'evidence_sha256':store.artifact(canonical(e))})
                    except ValueError as ex:
                        store.put('adapter_errors',{'id':e['id']+'_'+observation['capability_id'],'reason_code':str(ex),'created_at':now()})
            p.unlink()
            if count and count%100==0:progress(store,'daemon','ingest',last_committed_event=e['id'])
        except sqlite3.DatabaseError:
            # A ledger failure says nothing about an individual delivery's
            # validity. Preserve the spool and let the lane back off.
            raise
        except OSError as ex:
            if ex.errno in {5,13,28,30}:raise
            atomic_write(store.root/'quarantine'/p.name,canonical({"reason_code":type(ex).__name__,"sha256":digest(p.read_bytes())}))
            p.rename(store.root/'quarantine'/('raw-'+p.name))
        except Exception as ex:
            atomic_write(store.root/'quarantine'/p.name,canonical({"reason_code":str(ex),"sha256":digest(p.read_bytes())}))
            p.rename(store.root/'quarantine'/('raw-'+p.name))
    if count:
        reconcile_session_ends(store)
        from .evidence import evidence_plan
        evidence_plan(store,limit=4)
    return count


def reconcile_session_ends(store):
    """Rebuild late terminal binding from trustworthy time, never hash/rowid order."""
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        runs=[json.loads(x[0]) for x in db.execute("SELECT data FROM entities WHERE kind='runs'")]
        ends=[json.loads(x[0]) for x in db.execute("SELECT data FROM entities WHERE kind='session_envelopes'")]
        for end in ends:
            if not end.get('occurred_at'):continue
            eligible=[r for r in runs if r.get('execution_session_id',r.get('session_id'))==end['execution_session_id']
                      and r.get('agent_id')==end.get('agent_id') and r.get('first_source_at')
                      and r['first_source_at']<=end['occurred_at']]
            eligible.sort(key=lambda r:r['first_source_at'],reverse=True)
            if not eligible or (len(eligible)>1 and eligible[0]['first_source_at']==eligible[1]['first_source_at']):continue
            r=eligible[0]
            # A newer turn may arrive after the terminal envelope. Move the binding.
            prior=end.get('run_id')
            if prior and prior!=r['id']:
                old=next((x for x in runs if x['id']==prior),None)
                if old and end['event_id'] in old['event_ids']:
                    old['event_ids'].remove(end['event_id'])
                    other=[]
                    for eid in old['event_ids']:
                        row=db.execute('SELECT data FROM events WHERE id=?',(eid,)).fetchone()
                        if row:other.append(store.event_data(row[0],db))
                    if not any(e['event'] in TERMINAL for e in other):
                        old['terminal']=False
                        if old.get('status')=='ready':old['status']='evidence_pending'
                        last=max(other,key=lambda e:e.get('occurred_at',''),default={})
                        old['last_event']=last.get('event');old['last_source_at']=last.get('occurred_at')
                    store.put('runs',old,db)
            if end['event_id'] not in r['event_ids']:r['event_ids'].append(end['event_id'])
            r['terminal']=True
            if r.get('status')=='evidence_pending':r['status']='ready'
            if end['occurred_at']>=r.get('last_source_at',''):
                r['last_event']='SessionEnd';r['last_source_at']=end['occurred_at']
            store.put('runs',r,db)
            end.update(run_id=r['id'],status='bound',reason_code=None);store.put('session_envelopes',end,db)
            # SessionEnd is a coverage envelope, not a second semantic dispatch.
            # Turn terminal hooks/transcript events own review enqueueing.


def process_one(store, reviewer=None):
    if store.settings().get('paused') or not store.settings().get('automatic_review'): return None
    job=store.lease(seconds=getattr(reviewer,'max_seconds',120)+60)
    if not job:return None
    r=store.get('runs',job['run_id'])
    if reviewer:
        try:return reviewer.review(store,r)
        except Exception as ex:
            from .reviewer import ReviewDeferred
            attempts=[a for a in store.list('review_attempts') if a.get('run_id')==r['id'] and a.get('admission_sha256')]
            deferred=isinstance(ex,ReviewDeferred) and not attempts
            reason=str(ex) if re.fullmatch(r'[A-Z0-9_:-]{1,160}',str(ex)) else type(ex).__name__
            with store.connect() as db:db.execute("UPDATE jobs SET status=?,reason_code=?,lease_until=0,eligible_at=? WHERE id=?",('deferred' if deferred else 'hold',reason,ex.eligible_at if deferred else 0,job['id']))
            # Pre-dispatch rejection is a job state, not a consumed model attempt.
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


# Identity is captured when this runtime module loads, not from later disk bytes.
BUILD_IDENTITY=digest(Path(__file__).read_bytes())


def progress(store,lane,phase,successful=False,**fields):
    stamp=time.time();cached=store._progress.get(lane,{})
    old=cached.get('row') or store.get('runtime',lane) or {}
    row={**old,'id':lane,'status':'running','pid':os.getpid(),'build_sha256':BUILD_IDENTITY,
        'phase':phase,'phase_started_at':old.get('phase_started_at',stamp) if old.get('phase')==phase else stamp,
        'last_attempt_at':stamp,'last_success_at':old.get('last_success_at'),
        'last_progress_at':old.get('last_progress_at'),'heartbeat':stamp,'created_at':old.get('created_at',now()),**fields}
    if successful:row.update(last_success_at=stamp,last_progress_at=stamp)
    store._progress[lane]={'row':row,'persisted_at':cached.get('persisted_at',0)}
    # Coalesce phase churn; a live socket/attempt does not advance successful work.
    if stamp-cached.get('persisted_at',0)>=5:
        from .health import write_lane
        write_lane(store,lane,**row,consecutive_failures=0 if successful else cached.get('failures',0),reason_code=None)
        store.put('runtime',row);store._progress[lane]['persisted_at']=stamp
    elif successful:
        from .health import read_lane,write_lane
        if read_lane(store.root,lane).get('status')=='failed':
            write_lane(store,lane,**row,consecutive_failures=0,reason_code=None)
    return row


def collect(store):
    from .transcripts import observe_session, resolve_selected
    # Drain durable deliveries before following transcripts; one large appended
    # session must not delay the entire existing spool behind a full catalog pass.
    n=ingest(store)
    pending=list((store.root/'spool').glob('*.json'))
    if len(pending)>=512:
        progress(store,'daemon','idle',ingested=n,spool_count=len(pending),backpressure='drain_before_transcript_expansion',
            spool_oldest_age=max((time.time()-p.stat().st_mtime for p in pending if p.exists()),default=0))
        return n
    progress(store,'daemon','transcripts')
    sessions=store.list('selected_sessions')
    start=getattr(store,'_collect_cursor',0)%max(1,len(sessions))
    selected_batch=(sessions[start:]+sessions[:start])[:8]
    store._collect_cursor=start+len(selected_batch)
    for selected in selected_batch:
        if selected.get('relocated_to'):continue
        if selected.get('eligible_at',0)>time.time():continue
        if selected.get('closed'):
            cursor=store.get('cursors','cursor_'+digest(str(Path(selected['path']).resolve()).encode())[:24]) or {}
            try:
                if Path(selected['path']).stat().st_size==cursor.get('offset'):continue
            except OSError:
                pass  # The normal adapter error/backoff below owns missing paths.
        progress(store,'daemon','transcripts',selected_session_id=selected['id'])
        try:
            selected=resolve_selected(store,selected)
            if selected.get('relocation_pending'):continue
            observe_session(store,selected['path'],selected['session_id'],selected['source'])
        except Exception as ex:
            # One cause/session/version record, bounded retry; not one error per tick.
            old=store.get('adapter_errors',selected['id']) or {}
            store.put('adapter_errors',{'id':selected['id'],'reason_code':str(ex)[:160],
                'count':old.get('count',0)+1,'first_seen_at':old.get('first_seen_at',now()),'created_at':now()})
            selected['eligible_at']=time.time()+300
            store.put('selected_sessions',selected)
        n+=ingest(store,limit=64)
    progress(store,'daemon','ingest')
    n+=ingest(store)
    spool_files=list((store.root/'spool').glob('*.json'))
    progress(store,'daemon','idle',ingested=n,spool_count=len(spool_files),
             spool_oldest_age=max((time.time()-p.stat().st_mtime for p in spool_files if p.exists()),default=0))
    return n


def tick(store,reviewer=None,pipeline=None):
    n=collect(store)
    progress(store,'review_worker','review',deadline_at=time.time()+getattr(reviewer,'max_seconds',120)+50)
    review=process_one(store,reviewer)
    progress(store,'review_worker','idle')
    if pipeline is None:
        from .pipeline import EvolutionPipeline
        pipeline=EvolutionPipeline(store)
    progress(store,'evolution_worker','evolution')
    evolution=pipeline.tick()
    progress(store,'evolution_worker','idle')
    return {'ingested':n,'processed':bool(review),'evolution_processed':bool(evolution)}


def state(store):
    d={k:store.list(k) for k in ('skills','runs','reviews','experiments','installations','environments')}
    with store.connect() as db:
        for run in d['runs']:
            if not run.get('cwd') and run.get('event_ids'):
                row=db.execute('SELECT data FROM events WHERE id=?',(run['event_ids'][0],)).fetchone()
                if row:run['cwd']=store.event_data(row[0],db).get('cwd')
    for experiment in d['experiments']:
        if experiment.get('state'):experiment['status']=experiment['state']
    from .capabilities import project_lifecycle
    d.update(project_lifecycle(store));d['captures']=store.list('captures')
    d['lifecycle_metrics']={'catalog':len(d['capability_catalog']),'captures':len(d['captures']),
        'active':sum(x.get('status')=='active' for x in d['capability_catalog']),
        'invocations':len(d['capability_invocations']),'unknown_births':sum(not x.get('born_at') for x in d['capability_catalog']),
        'capture_holds':sum(x.get('status') in {'hold','failed'} for x in d['captures'])}
    d['jobs']=store.jobs();d['settings']=store.settings()
    reviewed=sum(x['status']=='reviewed' for x in d['reviews'])
    daemon=store.get('runtime','daemon') or {}
    d['metrics']={"observed_runs":len(d['runs']),"reviewed_runs":reviewed,"triaged_runs":sum(x['status']=='triaged' for x in d['reviews']),"global_coverage":None,"coverage_reason":"GLOBAL_DENOMINATOR_UNKNOWN","queued_jobs":sum(x['status']=='queued' for x in d['jobs']),"daemon_running":time.time()-daemon.get('heartbeat',0)<30,"window_start":min((x['created_at'] for x in d['runs']),default=None),"window_end":now()}
    from .semantic_progress import project
    d['semantic_progress']=project(store)
    d['runtime']=store.list('runtime');d['revision']=store.revision()
    d['capabilities']={"semantic_review":(store.get('runtime','reviewer') or {}).get('status','unconfigured'),"strong_sandbox":"requires_current_environment_receipt","promotion":"requires_frozen_independent_final","hook_trust":"native_review_required","recursive_gain":"UNVERIFIED"}
    return d
