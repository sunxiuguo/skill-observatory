"""Bounded factual review contract; evidence never confers execution authority."""
from __future__ import annotations
import re
from .store import canonical, digest

CODE = re.compile(r'^[A-Za-z0-9_.:-]{1,120}$')


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
    return store.put('run_evidence',{'id':value['run_id'],'capsule_sha256':h,'run_manifest_sha256':digest(canonical(run))})


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
                event=json.loads(row[0]);events.append({k:event[k] for k in ('id','event','tool_name','tool_use_id','source','occurred_at') if k in event})
    value={'schema_version':1,'run_id':run['id'],'facts':facts,'events':events,
           'coverage':'selected_redacted_facts_only','missing':missing,'outcome_truth':'runtime_only_unverified'}
    if len(canonical(value))>16000:raise ValueError('EVIDENCE_CAPSULE_TOO_LARGE')
    return value
