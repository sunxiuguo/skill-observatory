"""Bounded factual review contract; evidence never confers execution authority."""
from __future__ import annotations
import json
import re
from .store import canonical, digest, now

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
    versioned=value.get('schema_version')==2
    extra={'schema_version','run_binding','package_digest','environment_binding','artifact_refs','actual_terminal','source_class','coverage','attempt_refs','policy_digest','source_fingerprint','builder_version','local_refs'} if versioned else set()
    if set(value)!=required|extra or len(canonical(value))>24000 or redact(value)!=value:
        raise ValueError('EVIDENCE_CAPSULE_CONTRACT_INVALID')
    run=store.get('runs',value['run_id'])
    if not run:raise ValueError('RUN_NOT_FOUND')
    if versioned:
        outbound={k:v for k,v in value.items() if k!='local_refs'}
        if re.search(r'/Users/|/home/|/private/|[A-Z]:\\',canonical(outbound).decode()):raise ValueError('EVIDENCE_PRIVATE_PATH_REJECTED')
        _validate_v2(store,run,value)
    for k in ('goal','success_criteria'):
        if not isinstance(value[k],str) or not 0<len(value[k])<=1600:raise ValueError('EVIDENCE_TEXT_INVALID')
    if not isinstance(value['version_id'],str) or not CODE.fullmatch(value['version_id']):
        raise ValueError('EVIDENCE_OWNER_VERSION_REQUIRED')
    # Owners are registered text labels; only version IDs use the code grammar.
    # Reuse registration's contract, then require the exact catalog binding.
    from .capabilities import _text
    try:_text(value['owner'],'owner',True)
    except ValueError as ex:raise ValueError('EVIDENCE_OWNER_VERSION_REQUIRED') from ex
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
        from .capabilities import bind_run_attributions
        current=bind_run_attributions(store,current,db,version_id=value['version_id'])
        manifest=digest(canonical(current))
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
    if facts and facts.get('schema_version')==2:
        # Paths/local source material remain private; external owner admission is
        # checked against the actual capsule version, never a v1 fallback.
        facts={k:v for k,v in facts.items() if k not in {'local_refs'}}
    value={'schema_version':2 if facts and facts.get('schema_version')==2 else 1,'run_id':run['id'],'facts':facts,'events':events,
           'coverage':'selected_redacted_facts_only','missing':missing,'outcome_truth':'runtime_only_unverified'}
    if len(canonical(value))>16000:raise ValueError('EVIDENCE_CAPSULE_TOO_LARGE')
    return value


BUILDER_VERSION = 'evidence-builder-v2'


def project_run_evidence(store, run):
    """Deterministic, local-only facts. No inferred goals or success labels."""
    from pathlib import Path
    cwd=Path(run.get('cwd') or '.').resolve()
    from .transcripts import _inside_scope
    if not _inside_scope(store,cwd):raise ValueError('OUTSIDE_SCOPE')
    events=[]
    with store.connect() as db:
        for eid in run.get('event_ids',[]):
            row=db.execute('SELECT data FROM events WHERE id=?',(eid,)).fetchone()
            if not row:raise ValueError('EVIDENCE_EVENT_MISSING')
            event=store.event_data(row[0],db)
            if Path(event['cwd']).resolve()!=cwd:raise ValueError('EVIDENCE_SOURCE_CWD_DRIFT')
            h=store.artifact(canonical(event))
            events.append({**{k:event[k] for k in ('id','event','tool_name','tool_use_id','source','source_sequence','transcript_record_sha256','occurred_at','diagnostic_fact') if k in event},'event_sha256':h})
    execution=run.get('execution_session_id',run.get('session_id'))
    gaps=[g for g in store.list('transcript_gaps') if g.get('execution_session_id')==execution and
          (g.get('turn_id') is None or g.get('turn_id')==run.get('turn_id'))]
    coverage=[{'kind':'observed_receipts_only','global_denominator':None}]
    if gaps:coverage.append({'kind':'semantic_gap','gap_ids':[g['id'] for g in gaps],'status':'incomplete'})
    origin=run.get('origin')
    source_class='child' if run.get('agent_id') else {'review':'maintenance','maintenance':'maintenance','candidate_dev':'evaluation','final_eval':'evaluation','activation_canary':'canary'}.get(origin,'unknown')
    terminal=[e for e in events if e['event'] in {'Stop','SessionEnd','SubagentStop','Interrupt'}]
    actual={'event':terminal[-1]['event'] if terminal else None,'event_id':terminal[-1]['id'] if terminal else None,
            'truth':'runtime_only_unverified','result_status':'interrupted' if terminal and terminal[-1]['event']=='Interrupt' else 'unknown'}
    policy=digest(canonical({'builder':BUILDER_VERSION,'scopes':store.settings().get('scopes'),
                              'diagnostic_scopes':store.settings().get('diagnostic_scopes',[]),'privacy':'selected_redacted_only-v2'}))
    binding={k:run.get(k) for k in ('id','session_id','execution_session_id','turn_id','agent_id','origin')}
    source_manifest=store.artifact(canonical({'binding':binding,'events':events,'gaps':gaps}))
    fingerprint=digest(canonical({'source_manifest':source_manifest,'policy':policy}))
    return {'run_binding':binding,'source_event_manifest_sha256':source_manifest,'events':events[-24:],'actual_terminal':actual,'source_class':source_class,'coverage':coverage,
            'source_fingerprint':fingerprint,'policy_digest':policy,'builder_version':BUILDER_VERSION}


def _validate_v2(store,run,value):
    projection=project_run_evidence(store,run)
    for field in ('run_binding','source_fingerprint','policy_digest','source_class','actual_terminal','coverage','builder_version'):
        if value[field]!=projection[field]:raise ValueError('EVIDENCE_SOURCE_BINDING_DRIFT')
    version=store.get('capability_versions',value['version_id'])
    if not version or value['package_digest']!=version['package_sha256']:raise ValueError('EVIDENCE_PACKAGE_DRIFT')
    if value['local_refs']!=[{'sha256':projection['source_event_manifest_sha256'],'kind':'event_manifest'}]:
        raise ValueError('EVIDENCE_LOCAL_REFERENCE_DRIFT')
    for ref in value['local_refs']+value['artifact_refs']:
        if not isinstance(ref,dict) or set(ref)!={'sha256','kind'} or not CODE.fullmatch(ref['kind']):raise ValueError('EVIDENCE_REFERENCE_INVALID')
        store.read_artifact(ref['sha256'])
    # Unknown environment is explicit. Operator-selected values need provenance;
    # this builder cannot derive a model/effort from a guessed default.
    env=value['environment_binding']
    if not isinstance(env,dict) or set(env)!={'model','effort','harness','runtime','evidence_sha256','missing'}:raise ValueError('EVIDENCE_ENVIRONMENT_INVALID')
    if env['evidence_sha256'] is None:
        if any(env[k] is not None for k in ('model','effort','harness','runtime')) or not env['missing']:raise ValueError('EVIDENCE_ENVIRONMENT_UNVERIFIED')
    else:
        proof=json.loads(store.read_artifact(env['evidence_sha256']))
        if proof.get('run_binding')!=projection['run_binding'] or any(proof.get(k)!=env[k] for k in ('model','effort','harness','runtime')):
            raise ValueError('EVIDENCE_ENVIRONMENT_UNVERIFIED')
    from .final_gate import COST_KINDS
    for ref in value['attempt_refs']:
        if not isinstance(ref,dict) or set(ref)!={'kind','id','sha256'} or ref['kind'] not in COST_KINDS:raise ValueError('EVIDENCE_ATTEMPT_REFERENCE_INVALID')
        item=store.get(ref['kind'],ref['id'])
        if not item or digest(canonical(item))!=ref['sha256']:raise ValueError('EVIDENCE_ATTEMPT_DRIFT')
    if any(x.get('kind')=='semantic_gap' for x in value['coverage']) and value['result']['status']=='completed':
        raise ValueError('EVIDENCE_GAP_PREVENTS_SUCCESS_CLAIM')


def evidence_plan(store, run_id=None, limit=8):
    """Bounded durable sweep; an epoch's fixed ceiling cannot chase arrivals.

    Explicit selection remains idempotent. Automatic discovery advances even
    over built/blocked rows, including at limit=1 and after a process restart.
    The cursor and discovered work commit together in the original ledger.
    """
    if not 1<=limit<=50:raise ValueError('EVIDENCE_PLAN_LIMIT_INVALID')
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        scan=None
        if run_id:
            run=store.get('runs',run_id,db)
            if not run:raise ValueError('RUN_NOT_FOUND')
            runs=[run]
        else:
            scan=store.get('source_configuration','evidence_sweep',db) or {'id':'evidence_sweep','cursor':0,'ceiling':0}
            if scan['cursor']>=scan['ceiling']:
                ceiling=db.execute("SELECT COALESCE(MAX(rowid),0) FROM entities WHERE kind='runs'").fetchone()[0]
                scan={**scan,'cursor':0,'ceiling':ceiling}
            rows=db.execute("SELECT rowid,data FROM entities WHERE kind='runs' AND rowid>? AND rowid<=? AND json_extract(data,'$.terminal')=1 ORDER BY rowid LIMIT ?",
                            (scan['cursor'],scan['ceiling'],limit)).fetchall()
            runs=[json.loads(row['data']) for row in rows]
            scan['cursor']=rows[-1]['rowid'] if len(rows)==limit else scan['ceiling']
        result=_plan_runs(store,runs,db,explicit=bool(run_id))
        if scan is not None:store.put('source_configuration',scan,db)
        return result


def _activate_build(store,row,db):
    """One pending source/policy revision per run; retain historical receipts."""
    if row['status']=='superseded':
        row={**row,'status':row['superseded_from_status']}
        for field in ('superseded_from_status','superseded_by','superseded_at'):
            row.pop(field)
    store.put('evidence_builds',row,db)
    prior=db.execute("SELECT data FROM entities WHERE kind='evidence_builds' AND id!=? "
        "AND json_extract(data,'$.run_id')=? AND json_extract(data,'$.status') IN "
        "('awaiting_native_selection','blocked')",(row['id'],row['run_id'])).fetchall()
    for raw in prior:
        old=json.loads(raw[0])
        store.put('evidence_builds',{**old,'status':'superseded','superseded_from_status':old['status'],
            'superseded_by':row['id'],'superseded_at':now()},db)
    return row


def _plan_runs(store,runs,db,*,explicit):
    result=[]
    for run in runs:
        try:projection=project_run_evidence(store,run)
        except (ValueError,KeyError,OSError) as ex:
            if explicit:raise
            code=str(ex) if isinstance(ex,ValueError) and CODE.fullmatch(str(ex)) else 'EVIDENCE_SOURCE_READBACK_REQUIRED'
            fingerprint=digest(canonical([run,store.settings().get('scopes'),code]))
            id_='facts_blocked_'+fingerprint[:32]
            row=store.get('evidence_builds',id_,db) or {'id':id_,'run_id':run['id'],'source_fingerprint':fingerprint,
                 'status':'blocked','missing':[code],'observed_version_ids':[],'source_class':'unknown','created_at':now(),'model_attempts':0}
            result.append(_activate_build(store,row,db));continue
        id_='facts_'+digest(canonical([run['id'],projection['source_fingerprint'],BUILDER_VERSION,projection['policy_digest']]))[:32]
        old=store.get('evidence_builds',id_,db)
        if old:
            old=_activate_build(store,old,db)
            if explicit or old['status']!='built':result.append(old)
            continue
        version_ids=sorted({u['version_id'] for u in store.list('capability_invocations') if
                            u.get('session_id')==run.get('execution_session_id',run.get('session_id')) and u.get('turn_id')==run.get('turn_id') and 'verified_read' in u.get('stages',[])})
        row={'id':id_,'run_id':run['id'],**projection,'observed_version_ids':version_ids,
             'status':'awaiting_native_selection','missing':['TASK_GOAL_REQUIRED','SUCCESS_CRITERIA_REQUIRED']+([] if version_ids else ['OBSERVED_CAPABILITY_VERSION_REQUIRED']),
             'created_at':now(),'model_attempts':0}
        result.append(_activate_build(store,row,db))
    return result


def build_selected_evidence(store, selection):
    """Thin trusted Native selection ingress, sharing attach_evidence safety/CAS."""
    allowed={'run_id','goal','success_criteria','owner','version_id','result','steps','receipt_sha256','artifact_refs','attempt_refs','environment_binding'}
    if not isinstance(selection,dict) or set(selection)-allowed or not allowed-{'artifact_refs','attempt_refs','environment_binding'}<=set(selection):raise ValueError('EVIDENCE_SELECTION_INVALID')
    plan=evidence_plan(store,selection['run_id'])[0]
    version=store.get('capability_versions',selection['version_id'])
    if not version:raise ValueError('EVIDENCE_OWNER_VERSION_MISMATCH')
    value={**selection,'schema_version':2,**{k:plan[k] for k in ('run_binding','actual_terminal','source_class','coverage','source_fingerprint','policy_digest','builder_version')},
           'package_digest':version['package_sha256'],'artifact_refs':selection.get('artifact_refs',[]),'attempt_refs':selection.get('attempt_refs',[]),
           'environment_binding':selection.get('environment_binding',{'model':None,'effort':None,'runtime':None,'harness':None,'evidence_sha256':None,'missing':['ENVIRONMENT_NOT_OBSERVED']}),
           'local_refs':[{'sha256':plan['source_event_manifest_sha256'],'kind':'event_manifest'}]}
    h=store.artifact(canonical(value))
    if plan.get('selection_sha256'):
        if plan['selection_sha256']!=h:raise ValueError('EVIDENCE_BUILD_ALREADY_SELECTED')
        with store.connect() as db:
            db.execute('BEGIN')
            receipt=store.get('run_evidence',selection['run_id'],db)
            current=store.get('runs',selection['run_id'],db)
            if not receipt or receipt.get('capsule_sha256')!=h or receipt.get('run_manifest_sha256')!=digest(canonical(current)):
                raise ValueError('EVIDENCE_BUILD_READBACK_REQUIRED')
            return receipt
    receipt=attach_evidence(store,value)
    plan.update(status='built',missing=[],selection_sha256=h,completed_at=now())
    store.put('evidence_builds',plan)
    return receipt
