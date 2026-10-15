"""Bounded factual review contract; evidence never confers execution authority."""
from __future__ import annotations
import json
import re
from .store import canonical, digest

CODE = re.compile(r'^[A-Za-z0-9_.:-]{1,120}$')


def diagnostic_from_output(output):
    """Extract allowlisted failure types, never raw commands/output or prompts."""
    texts=[];codes=[]
    def visit(value,depth=0):
        if depth>5:return
        if isinstance(value,dict):
            for k,v in value.items():
                if k in {'exit_code','exitCode'} and type(v) is int:codes.append(v)
                elif k in {'output','text','content','metadata','result','value'}:visit(v,depth+1)
        elif isinstance(value,list):
            for v in value[:64]:visit(v,depth+1)
        elif isinstance(value,str):
            text=value[:1000000];texts.append(text)
            try:visit(json.loads(text),depth+1)
            except ValueError:pass
    visit(output)
    text='\n'.join(texts)
    codes.extend(int(m) for m in re.findall(r'(?:exit_code[\"\s:]+|exit code[:\s]+|exited with code\s+)(-?\d+)',text,re.I))
    failed=next((c for c in codes if c!=0),None)
    if failed is None:return None
    reason='CLI_ARGUMENT_MISMATCH' if re.search(r'unrecognized arguments|argument .*invalid choice',text,re.I) else 'TOOL_TIMEOUT' if 'TimeoutExpired' in text else 'TOOL_EXIT_NONZERO'
    return {'status':'failed','exit_code':failed,'reason_code':reason}


def attach_evidence(store, value):
    """Trusted local ingress, absent from HTTP; only redacted selected facts."""
    from .runtime import redact
    required={'run_id','goal','success_criteria','owner','version_id','result','steps','receipt_sha256'}
    if set(value)!=required or len(canonical(value))>12000 or redact(value)!=value:
        raise ValueError('EVIDENCE_CAPSULE_CONTRACT_INVALID')
    run=store.get('runs',value['run_id'])
    if not run:raise ValueError('RUN_NOT_FOUND')
    for k in ('goal','success_criteria'):
        if not isinstance(value[k],str) or not 0<len(value[k])<=1600:raise ValueError('EVIDENCE_TEXT_INVALID')
    if not all(isinstance(value[k],str) and CODE.fullmatch(value[k]) for k in ('owner','version_id')):
        raise ValueError('EVIDENCE_OWNER_VERSION_REQUIRED')
    version=store.get('capability_versions',value['version_id'])
    cap=store.get('capability_catalog',version['capability_id']) if version else None
    if not cap or cap['owner']!=value['owner']:raise ValueError('EVIDENCE_OWNER_VERSION_MISMATCH')
    if not any(u.get('version_id')==version['id'] and u.get('session_id')==run.get('execution_session_id',run.get('session_id'))
               and u.get('turn_id')==run.get('turn_id') and 'verified_read' in u.get('stages',[])
               for u in store.list('capability_invocations')):raise ValueError('EVIDENCE_VERSION_NOT_OBSERVED')
    if not isinstance(value['result'],dict) or set(value['result'])-{'status','reason_code','exit_code'}:
        raise ValueError('EVIDENCE_RESULT_INVALID')
    if value['result'].get('status') not in {'completed','failed','interrupted','unknown'}:raise ValueError('EVIDENCE_RESULT_INVALID')
    if value['result'].get('reason_code') is not None and not CODE.fullmatch(value['result']['reason_code']):raise ValueError('EVIDENCE_RESULT_INVALID')
    if not isinstance(value['steps'],list) or not 1<=len(value['steps'])<=24:raise ValueError('EVIDENCE_STEPS_INVALID')
    for step in value['steps']:
        if not isinstance(step,dict) or set(step)!={'event_id','fact'} or step['event_id'] not in run['event_ids']:
            raise ValueError('EVIDENCE_STEP_NOT_BOUND')
        if not isinstance(step['fact'],str) or not 0<len(step['fact'])<=320:raise ValueError('EVIDENCE_STEPS_INVALID')
    # This receipt is source evidence, not an independent oracle signature.
    store.read_artifact(value['receipt_sha256'])
    h=store.artifact(canonical(value))
    manifest=digest(canonical(run))
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        current=store.get('runs',run['id'],db)
        if digest(canonical(current))!=manifest:raise ValueError('EVIDENCE_CAPSULE_RUN_DRIFT')
        old=store.get('run_evidence',run['id'],db)
        if old and old.get('capsule_sha256')==h and old.get('run_manifest_sha256')==manifest:return old
        # Only a known pre-dispatch evidence wait can reopen. Missing admission
        # metadata on an otherwise ambiguous legacy attempt is not proof of safety.
        attempts=[__import__('json').loads(r[0]) for r in db.execute("SELECT data FROM entities WHERE kind='review_attempts' AND json_extract(data,'$.run_id')=?",(run['id'],))]
        safe=not any(a.get('admission_sha256') or a.get('status') not in {'hold','deferred'}
            or a.get('reason_code') not in {'DIAGNOSTIC_FACTS_REQUIRED','EVIDENCE_CAPSULE_RUN_DRIFT','DAILY_REVIEW_ATTEMPT_BUDGET_HOLD'} for a in attempts)
        resumed=0
        if safe:
            resumed=db.execute("UPDATE jobs SET status='queued',reason_code=NULL,eligible_at=0,lease_until=0 WHERE run_id=? AND status='hold' AND reason_code IN ('DIAGNOSTIC_FACTS_REQUIRED','EVIDENCE_CAPSULE_RUN_DRIFT')",(run['id'],)).rowcount
        return store.put('run_evidence',{'id':value['run_id'],'capsule_sha256':h,'run_manifest_sha256':manifest,'resumed_pre_dispatch_jobs':resumed},db)


def build_capsule(store,run):
    attached=store.get('run_evidence',run['id'])
    facts=None;missing=[]
    if attached:
        if attached['run_manifest_sha256']!=digest(canonical(run)):
            missing.append('EVIDENCE_CAPSULE_RUN_DRIFT')
        else:
            import json
            facts=json.loads(store.read_artifact(attached['capsule_sha256']))
    if facts is None:missing.append('DIAGNOSTIC_FACTS_REQUIRED')
    # Metadata allows deterministic triage; it does not replace diagnostic facts.
    events=[]
    with store.connect() as db:
        for eid in run.get('event_ids',[])[-24:]:
            row=db.execute('SELECT data FROM events WHERE id=?',(eid,)).fetchone()
            if row:
                import json
                event=store.event_data(row[0],db);events.append({k:event[k] for k in ('id','event','tool_name','tool_use_id','source','occurred_at') if k in event})
    value={'schema_version':1,'run_id':run['id'],'facts':facts,'events':events,
           'coverage':'selected_redacted_facts_only','missing':missing,'outcome_truth':'runtime_only_unverified'}
    if len(canonical(value))>16000:raise ValueError('EVIDENCE_CAPSULE_TOO_LARGE')
    return value
