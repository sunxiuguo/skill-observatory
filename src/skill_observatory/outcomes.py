"""Independent task-result ingress; semantic model reviews cannot use this path.

The trusted domain verifier signs receipts. Candidate/model processes never get
the verifier key or Store. There is deliberately no HTTP/CLI claim-success API.
"""
from datetime import datetime, timezone
from pathlib import Path
import hmac
import json
from .store import canonical, digest, now
from .installations import key, validate_verdict


def run_binding(run):
    return digest(canonical({k:run.get(k) for k in (
        'id','session_id','turn_id','agent_id','origin','created_at','event_ids','attributions')}))


def seal_task_receipt(store,receipt):
    r=dict(receipt);r.pop('signature',None)
    return {**r,'signature':hmac.new(key(store),b'task-result-v1\0'+canonical(r),'sha256').hexdigest()}


def validate_task_receipt(store,receipt):
    r=dict(receipt);sig=r.pop('signature','')
    expected=hmac.new(key(store),b'task-result-v1\0'+canonical(r),'sha256').hexdigest()
    if not hmac.compare_digest(sig,expected):raise ValueError('TASK_RECEIPT_UNTRUSTED')
    run=store.get('runs',r['run_id']);installation=store.get('installations',r['installation_id'])
    if not run or not installation or run_binding(run)!=r['run_binding_sha256']:raise ValueError('TASK_EVIDENCE_DRIFT')
    candidate=store.get('candidates',installation['candidate_id'])
    if not candidate:raise ValueError('CANDIDATE_NOT_FOUND')
    verdict=validate_verdict(store,store.get('verdicts',candidate['verdict_id']) or {})
    protocol=store.get('protocols',verdict['protocol_id'])
    if r['protocol_sha256']!=verdict['protocol_sha256'] or r['skill_sha256']!=installation['after_sha256']:raise ValueError('TASK_PROTOCOL_BINDING_HOLD')
    if r['status'] not in {'accepted','partial','failed'}:raise ValueError('TASK_OUTCOME_INVALID')
    if r['oracle_sha256']!=protocol.get('activation_oracle_sha256',protocol['oracle_sha256']):raise ValueError('TASK_ORACLE_DRIFT')
    store.read_artifact(r['oracle_sha256']);store.read_artifact(r['result_artifact_sha256'])
    context=json.loads(store.read_artifact(r['context_receipt_sha256']))
    if context.get('context_id')!=run['session_id'] or context.get('origin')!='trusted_broker' or context.get('fresh') is not True:
        raise ValueError('FRESH_CONTEXT_RECEIPT_REQUIRED')
    if context.get('model')!=protocol['model'] or context.get('effort')!=protocol['max_verified_effort']:
        raise ValueError('TASK_MODEL_DRIFT')
    if installation.get('after_package'):
        from .packages import snapshot_package
        expected_package=installation['after_package']['package_digest']
        if r.get('package_digest')!=expected_package or context.get('loaded_package_digest')!=expected_package:raise ValueError('FRESH_PACKAGE_LOAD_REQUIRED')
        if snapshot_package(store,installation['target_root'])!=installation['after_package']:raise ValueError('TASK_PACKAGE_DRIFT')
    if not installation.get('applied_at'):raise ValueError('INSTALLATION_APPLY_TIME_REQUIRED')
    try:
        born=datetime.fromisoformat(context['created_at'].replace('Z','+00:00'))
        installed=datetime.fromisoformat(installation['applied_at'].replace('Z','+00:00'))
        if born.tzinfo is None or installed.tzinfo is None or born<=installed:raise ValueError()
    except (KeyError,TypeError,ValueError):raise ValueError('PREINSTALL_CONTEXT_REJECTED')
    if not any(a.get('file_sha256')==r['skill_sha256'] and a.get('attribution') in
               {'explicit_loaded','verified_read','executed_script'} for a in run['attributions']):
        raise ValueError('FRESH_LOAD_EVIDENCE_REQUIRED')
    return r


def accept_task_result(store,receipt):
    r=validate_task_receipt(store,receipt)
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        run=store.get('runs',r['run_id'],db)
        if run_binding(run)!=r['run_binding_sha256']:raise ValueError('TASK_EVIDENCE_DRIFT')
        prior=store.get('task_receipts',r['id'],db)
        if prior and prior!=receipt:raise ValueError('TASK_RECEIPT_ID_COLLISION')
        store.put('task_receipts',receipt,db)
        run.update(outcome=r['status'],fresh_context=True,outcome_receipt_id=r['id'])
        store.put('runs',run,db)
    return receipt


def verify_live(store,installation_id,run_id):
    """A later user run and current disk readback, valid as of this receipt."""
    from .installations import lock
    # Initialize outside the installation transaction; key reads inside are pure.
    key(store)
    with lock(store):
        i=store.get('installations',installation_id);run=store.get('runs',run_id)
        if not i or not run or i['status']!='activated' or run['origin']!='user_run':raise ValueError('LIVE_STATE_HOLD')
        if run_id==i.get('activation_run_id') or run.get('outcome')!='accepted':raise ValueError('LATER_ACCEPTED_RUN_REQUIRED')
        r=validate_task_receipt(store,store.get('task_receipts',run.get('outcome_receipt_id')) or {})
        if r['installation_id']!=installation_id:raise ValueError('LIVE_INSTALLATION_MISMATCH')
        target=Path(i['target'])
        if target.is_symlink() or not target.is_file() or digest(target.read_bytes())!=i['after_sha256']:
            raise ValueError('DRIFT_HOLD')
        if i.get('after_package'):
            from .packages import snapshot_package
            if snapshot_package(store,i['target_root'])!=i['after_package']:raise ValueError('DRIFT_HOLD')
            i['verified_package_digest']=i['after_package']['package_digest']
        verified_at=now()
        i.update(live_verified=True,live_run_id=run_id,updated_at=verified_at,
                 live_verified_at=verified_at,verified_skill_sha256=i['after_sha256'])
        return store.put('installations',i)


def _immutable(store,kind,value):
    old=store.get(kind,value['id'])
    if old and old!=value:raise ValueError('IMMUTABLE_OUTCOME_BINDING_DRIFT')
    return old or store.put(kind,value)


def freeze_cohort(store,value):
    """Trusted local owner defines comparability; no automatic natural labels."""
    required={'id','installation_id','arm_bindings','task_family','task_family_sha256','start','end','comparison','source_definition_sha256','denominator'}
    if set(value)!=required:raise ValueError('COHORT_CONTRACT_INVALID')
    installation=store.get('installations',value['installation_id'])
    if not installation or not installation.get('applied_at'):raise ValueError('INSTALLATION_APPLY_TIME_REQUIRED')
    bindings=value['arm_bindings']
    if not isinstance(bindings,dict) or set(bindings)!={'parent','candidate'}:raise ValueError('COHORT_ARM_BINDINGS_REQUIRED')
    versions={}
    for arm,binding in bindings.items():
        if not isinstance(binding,dict) or set(binding)!={'installation_id','version_sha256'}:raise ValueError('COHORT_ARM_BINDINGS_REQUIRED')
        item=store.get('installations',binding['installation_id'])
        if not item or not item.get('applied_at'):raise ValueError('COHORT_ARM_INSTALLATION_UNKNOWN')
        version=(item.get('after_package') or {}).get('package_digest',item.get('after_sha256'))
        if not version or binding['version_sha256']!=version:raise ValueError('COHORT_VERSION_BINDING_DRIFT')
        versions[arm]=item
    parent,candidate=versions['parent'],versions['candidate']
    if bindings['candidate']['installation_id']!=value['installation_id']:raise ValueError('COHORT_INSTALLATION_MISMATCH')
    if bindings['parent']['installation_id']==value['installation_id'] or bindings['parent']['version_sha256']==bindings['candidate']['version_sha256']:
        raise ValueError('COHORT_DISTINCT_PARENT_REQUIRED')
    if not candidate.get('before_sha256') or candidate['before_sha256']!=parent['after_sha256']:raise ValueError('COHORT_PARENT_VERSION_UNKNOWN')
    if candidate.get('after_package') or parent.get('after_package'):
        before=candidate.get('before_package') or {};prior=parent.get('after_package') or {}
        if not before.get('package_digest') or before['package_digest']!=prior.get('package_digest'):raise ValueError('COHORT_PARENT_PACKAGE_UNKNOWN')
    family=json.loads(store.read_artifact(value['task_family_sha256']))
    if not isinstance(family,dict) or family.get('id')!=value['task_family'] or not family.get('definition'):raise ValueError('COHORT_TASK_FAMILY_REQUIRED')
    try:
        start=datetime.fromisoformat(value['start']);end=datetime.fromisoformat(value['end'])
        if start.tzinfo is None or end.tzinfo is None or start>=end:raise ValueError()
    except (ValueError,TypeError):raise ValueError('COHORT_WINDOW_INVALID')
    comparison=value['comparison']
    if set(comparison)!={'model','effort','harness','environment_sha256'} or not all(isinstance(v,str) and v for v in comparison.values()):raise ValueError('COHORT_COMPARABILITY_REQUIRED')
    store.read_artifact(comparison['environment_sha256']);store.read_artifact(value['source_definition_sha256'])
    denominator=value['denominator']
    if set(denominator)!={'parent','candidate'} or any(v is not None and (type(v) is not int or v<0) for v in denominator.values()):raise ValueError('COHORT_DENOMINATOR_INVALID')
    row=_immutable(store,'outcome_cohorts',{**value,'schema_version':3})
    existing=store.get('outcome_followups','cohort_'+value['id'])
    if not existing:
        store.put('outcome_followups',{'id':'cohort_'+value['id'],'cohort_id':value['id'],'installation_id':value['installation_id'],
                 'owner':'proactive-review','status':'pending','due_at':value['end'],'missing':['NATURAL_COMPARABLE_SAMPLES_REQUIRED'],
                 'next_action':'collect independent natural task receipts under frozen cohort','created_at':now()})
    return row


def seal_natural_source(store,value):
    """Independent provenance owner only; not available to candidate/UI."""
    data=dict(value);data.pop('signature',None)
    return {**data,'signature':hmac.new(key(store),b'natural-source-v1\0'+canonical(data),'sha256').hexdigest()}


def record_cohort_sample(store,value):
    required={'id','cohort_id','arm','task_receipt_id','source_receipt','rework','takeovers','elapsed_seconds','attempt_refs'}
    if set(value)!=required or value['arm'] not in {'parent','candidate'}:raise ValueError('COHORT_SAMPLE_INVALID')
    cohort=store.get('outcome_cohorts',value['cohort_id'])
    if not cohort:raise ValueError('COHORT_NOT_FOUND')
    if cohort.get('schema_version')!=3:raise ValueError('COHORT_ARM_BINDINGS_REQUIRED')
    receipt=store.get('task_receipts',value['task_receipt_id']) or {}
    task=validate_task_receipt(store,receipt);run=store.get('runs',task['run_id'])
    if run.get('origin')!='user_run' or run.get('agent_id') or task.get('canary') is True:raise ValueError('CANARY_OR_CHILD_NOT_NATURAL')
    binding=cohort['arm_bindings'][value['arm']]
    installation=store.get('installations',task['installation_id'])
    version=(installation.get('after_package') or {}).get('package_digest',installation.get('after_sha256'))
    if task['installation_id']!=binding['installation_id'] or version!=binding['version_sha256']:raise ValueError('COHORT_INSTALLATION_MISMATCH')
    if task.get('task_family_sha256')!=cohort['task_family_sha256']:raise ValueError('COHORT_TASK_FAMILY_MISMATCH')
    context=json.loads(store.read_artifact(task['context_receipt_sha256']))
    for k in ('model','effort','harness','environment_sha256'):
        if context.get(k)!=cohort['comparison'][k]:raise ValueError('COHORT_COMPARABILITY_DRIFT')
    try:
        stamp=datetime.fromisoformat(context['created_at'].replace('Z','+00:00'))
        if stamp.tzinfo is None or not datetime.fromisoformat(cohort['start'])<=stamp<datetime.fromisoformat(cohort['end']):raise ValueError()
    except (ValueError,TypeError,KeyError):raise ValueError('COHORT_OUTSIDE_WINDOW')
    provenance=dict(value['source_receipt']);sig=provenance.pop('signature','')
    expected=hmac.new(key(store),b'natural-source-v1\0'+canonical(provenance),'sha256').hexdigest()
    if not hmac.compare_digest(sig,expected):raise ValueError('NATURAL_SOURCE_UNTRUSTED')
    if provenance.get('run_id')!=run['id'] or provenance.get('source_class')!='natural' or provenance.get('definition_sha256')!=cohort['source_definition_sha256']:
        raise ValueError('NATURAL_SOURCE_BINDING_REQUIRED')
    logical=provenance.get('logical_task_id')
    if not isinstance(logical,str) or not logical or len(logical)>160:raise ValueError('LOGICAL_TASK_IDENTITY_REQUIRED')
    if task.get('logical_task_id')!=logical or task.get('natural_source_definition_sha256')!=cohort['source_definition_sha256']:
        raise ValueError('LOGICAL_TASK_RECEIPT_BINDING_REQUIRED')
    logical_identity=digest(canonical([cohort['source_definition_sha256'],logical]))
    execution_identity=_natural_execution_identity(run)
    binding=digest(canonical({'logical_task_sha256':logical_identity,'execution_source_sha256':execution_identity,
        'run_binding_sha256':task['run_binding_sha256'],'installation_id':task['installation_id'],
        'context_receipt_sha256':task['context_receipt_sha256'],'result_artifact_sha256':task['result_artifact_sha256'],
        'cost_manifest_sha256':task.get('cost_manifest_sha256')}))
    store.read_artifact(provenance['evidence_sha256'])
    if any(type(value[k]) is not int or value[k]<0 for k in ('rework','takeovers')):raise ValueError('COHORT_COUNTS_INVALID')
    from .final_gate import _finite,COST_KINDS
    if not _finite(value['elapsed_seconds']):raise ValueError('COHORT_ELAPSED_INVALID')
    seen=set()
    for ref in value['attempt_refs']:
        if set(ref)!={'kind','id','sha256'} or ref['kind'] not in COST_KINDS or (ref['kind'],ref['id']) in seen:raise ValueError('COHORT_COST_REFERENCE_INVALID')
        row=store.get(ref['kind'],ref['id'])
        if not row or digest(canonical(row))!=ref['sha256']:raise ValueError('COHORT_COST_REFERENCE_DRIFT')
        if row.get('run_id') not in _natural_task_runs(store,task):raise ValueError('COHORT_COST_RUN_MISMATCH')
        seen.add((ref['kind'],ref['id']))
    accounting=_sample_costs(store,{**value,'run_id':run['id']},task)
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if store.get('task_receipts',value['task_receipt_id'],db)!=receipt or run_binding(store.get('runs',run['id'],db))!=task['run_binding_sha256']:raise ValueError('TASK_EVIDENCE_DRIFT')
        # Check actual source even for legacy rows without the new fields. A
        # re-signed receipt, alias run or retry cannot buy a second denominator.
        for stored in db.execute("SELECT data FROM entities WHERE kind='cohort_samples'"):
            sample=json.loads(stored[0]);old_task=store.get('task_receipts',sample.get('task_receipt_id'),db) or {}
            old_run=store.get('runs',old_task.get('run_id'),db)
            same_source=old_run and _natural_execution_identity(old_run)==execution_identity
            same_task=sample.get('logical_task_sha256')==logical_identity
            if (same_source or same_task or sample.get('task_receipt_id')==value['task_receipt_id']) and sample['id']!=value['id']:
                raise ValueError('COHORT_SAMPLE_DUPLICATE_LOGICAL_TASK')
        old=store.get('cohort_samples',value['id'],db)
        data={**value,'run_id':run['id'],'created_at':old.get('created_at') if old else now(),
              'logical_task_sha256':logical_identity,'execution_source_sha256':execution_identity,'task_binding_sha256':binding,
              'cost_coverage':'complete_owner_manifest' if accounting['complete'] else 'unknown',
              'costs':accounting['costs'],'cost_missing':accounting['missing']}
        if old and old!=data:raise ValueError('IMMUTABLE_OUTCOME_BINDING_DRIFT')
        row=store.put('cohort_samples',data,db)
    return row


def _natural_execution_identity(run):
    execution=run.get('execution_session_id') or run.get('session_id')
    source=run.get('turn_id') or sorted(set(run.get('event_ids') or []))
    if not execution or not source:raise ValueError('NATURAL_EXECUTION_SOURCE_REQUIRED')
    return digest(canonical({'execution':execution,'task_source':source}))


def _natural_task_runs(store,task):
    runs={task['run_id']}
    if task.get('logical_task_id') and task.get('natural_source_definition_sha256'):
        for receipt in store.list('task_receipts'):
            if all(receipt.get(k)==task.get(k) for k in ('logical_task_id','natural_source_definition_sha256','task_family_sha256')):runs.add(receipt['run_id'])
    return runs


def _sample_costs(store,sample,task):
    """A signed per-task inventory, plus every currently known attempt.

    The independent result owner attests inventory completeness; the report
    re-resolves it so a later failed/retried attempt cannot disappear behind a
    cached aggregate. Missing proof is UNKNOWN, including an empty refs list.
    """
    from .final_gate import COST_KINDS,COST_TERMINAL_STATES,_finite
    refs=sample.get('attempt_refs',[]);costs=[];missing=[];seen=set();related_runs=_natural_task_runs(store,task)
    for ref in refs:
        ident=(ref['kind'],ref['id']);row=store.get(*ident)
        if ident in seen or not row or digest(canonical(row))!=ref['sha256'] or row.get('run_id') not in related_runs:
            missing.append('ATTEMPT_REFERENCE_DRIFT');continue
        seen.add(ident);costs.append(row.get('cost',row))
        if row.get('status') not in COST_TERMINAL_STATES[ref['kind']]:missing.append('ATTEMPT_READBACK_REQUIRED')
    with store.connect() as db:
        known={(r['kind'],r['id']) for r in db.execute("SELECT kind,id FROM entities WHERE kind IN ("+','.join('?' for _ in COST_KINDS)+") AND json_extract(data,'$.run_id') IN ("+','.join('?' for _ in related_runs)+")",(*sorted(COST_KINDS),*sorted(related_runs)))}
    if known-seen:missing.append('KNOWN_ATTEMPT_COST_MISSING')
    manifest=None
    if task.get('cost_manifest_sha256'):
        try:manifest=json.loads(store.read_artifact(task['cost_manifest_sha256']))
        except (ValueError,OSError):missing.append('COST_MANIFEST_INVALID')
    if not isinstance(manifest,dict) or manifest.get('complete') is not True or manifest.get('run_id')!=task['run_id'] or manifest.get('attempt_refs')!=refs:
        missing.append('ALL_ATTEMPT_COST_REQUIRED')
    elif not refs:
        zero=manifest.get('zero_cost')
        if not isinstance(zero,dict) or zero.get('money')!=0 or type(zero.get('tokens')) is not int or zero['tokens']!=0 or known:
            missing.append('EXPLICIT_ZERO_COST_REQUIRED')
        else:costs=[zero]
    if any(not isinstance(c,dict) or not _finite(c.get('money')) or type(c.get('tokens')) is not int or c['tokens']<0 or
           not isinstance(c.get('currency'),str) or len(c['currency'])!=3 or not c['currency'].isascii() or not c['currency'].isupper() for c in costs):
        missing.append('ATTEMPT_COST_UNKNOWN')
    if len({c.get('currency') for c in costs if isinstance(c,dict)})>1:missing.append('COST_CURRENCY_MISMATCH')
    if missing and 'ALL_ATTEMPT_COST_REQUIRED' not in missing:missing.append('ALL_ATTEMPT_COST_REQUIRED')
    return {'complete':not missing,'costs':costs,'missing':sorted(set(missing)),
            'known_attempts':len(known),'referenced_attempts':len(seen)}


def cohort_report(store,cohort_id):
    c=store.get('outcome_cohorts',cohort_id)
    if not c:raise ValueError('COHORT_NOT_FOUND')
    rows=[x for x in store.list('cohort_samples') if x['cohort_id']==cohort_id];arms={}
    for arm in ('parent','candidate'):
        samples=[x for x in rows if x['arm']==arm];n=len(samples)
        statuses=[store.get('task_receipts',x['task_receipt_id'])['status'] for x in samples]
        missing=[]
        identities={};sources={};identity_missing=False
        for sample in rows:
            task=store.get('task_receipts',sample['task_receipt_id']) or {};run=store.get('runs',task.get('run_id'))
            try:
                validate_task_receipt(store,task)
                provenance=dict(sample['source_receipt']);signature=provenance.pop('signature','')
                expected=hmac.new(key(store),b'natural-source-v1\0'+canonical(provenance),'sha256').hexdigest()
                if not hmac.compare_digest(signature,expected):raise ValueError('NATURAL_SOURCE_UNTRUSTED')
                if provenance.get('run_id')!=task['run_id'] or provenance.get('source_class')!='natural' or provenance.get('definition_sha256')!=c['source_definition_sha256'] or task.get('natural_source_definition_sha256')!=c['source_definition_sha256'] or task.get('task_family_sha256')!=c['task_family_sha256'] or task['installation_id']!=c['arm_bindings'][sample['arm']]['installation_id'] or run.get('origin')!='user_run' or run.get('agent_id'):
                    raise ValueError('COHORT_SAMPLE_BINDING_DRIFT')
                logical=digest(canonical([c['source_definition_sha256'],task['logical_task_id']]))
                physical=_natural_execution_identity(run or {})
                binding=digest(canonical({'logical_task_sha256':logical,'execution_source_sha256':physical,
                    'run_binding_sha256':task['run_binding_sha256'],'installation_id':task['installation_id'],
                    'context_receipt_sha256':task['context_receipt_sha256'],'result_artifact_sha256':task['result_artifact_sha256'],
                    'cost_manifest_sha256':task.get('cost_manifest_sha256')}))
                if sample.get('logical_task_sha256')!=logical or sample.get('execution_source_sha256')!=physical or sample.get('task_binding_sha256')!=binding or provenance.get('logical_task_id')!=task['logical_task_id']:
                    raise ValueError('COHORT_SAMPLE_BINDING_DRIFT')
            except (ValueError,KeyError,TypeError,OSError) as ex:
                identity_missing=True;missing.append(str(ex))
            logical=sample.get('logical_task_sha256')
            if not logical:identity_missing=True
            else:identities.setdefault(logical,[]).append(sample['id'])
            try:physical=_natural_execution_identity(run or {})
            except ValueError:identity_missing=True;continue
            sources.setdefault(physical,[]).append(sample['id'])
        duplicates=[ids for ids in [*identities.values(),*sources.values()] if len(ids)>1]
        independent=len({x.get('logical_task_sha256') for x in samples}) if not identity_missing else None
        if duplicates:missing.append('DUPLICATE_LOGICAL_NATURAL_TASK')
        if identity_missing:missing.append('LOGICAL_TASK_IDENTITY_REQUIRED')
        if not n:missing.append('NATURAL_SAMPLES_REQUIRED')
        if c['denominator'][arm] is None:missing.append('DENOMINATOR_UNKNOWN')
        elif independent!=c['denominator'][arm]:missing.append('INCOMPLETE_COHORT_COVERAGE')
        accounts=[_sample_costs(store,x,store.get('task_receipts',x['task_receipt_id'])) for x in samples]
        costs=[v for x in accounts for v in x['costs']]
        currencies={v.get('currency') for v in costs if isinstance(v,dict)}
        cost_known=bool(n) and not duplicates and not identity_missing and all(x['complete'] for x in accounts) and len(currencies)==1
        if not cost_known:missing.append('ALL_ATTEMPT_COST_REQUIRED')
        if len(currencies)>1:missing.append('COST_CURRENCY_MISMATCH')
        arms[arm]={'observed':n,'independent_observed':independent,'duplicate_sample_groups':duplicates,'denominator':c['denominator'][arm],'accepted':statuses.count('accepted') if not duplicates and not identity_missing else None,'partial':statuses.count('partial') if not duplicates and not identity_missing else None,
                   'failed':statuses.count('failed') if not duplicates and not identity_missing else None,'rework':sum(x['rework'] for x in samples) if n and not duplicates and not identity_missing else None,'takeovers':sum(x['takeovers'] for x in samples) if n and not duplicates and not identity_missing else None,
                   'elapsed_seconds':sum(x['elapsed_seconds'] for x in samples) if n and not duplicates and not identity_missing else None,'missing':sorted(set(missing)),'money':sum(v['money'] for v in costs) if cost_known else None,'tokens':sum(v['tokens'] for v in costs) if cost_known else None,'currency':costs[0]['currency'] if cost_known else None,
                   'sample_cost_coverage':[{'sample_id':x['id'],**{k:a[k] for k in ('complete','missing','known_attempts','referenced_attempts')}} for x,a in zip(samples,accounts)]}
    return {'cohort_id':cohort_id,'window':[c['start'],c['end']],'task_family':c['task_family'],'comparison':c['comparison'],'arms':arms,'natural_gain':'UNKNOWN','coverage':'observed_receipts_only'}


def register_method_version(store,value):
    required={'id','content_sha256','parent_version_id','mutable_surface','authority_evidence_sha256','acceptance_verdict_id'}
    if set(value)!=required or not set(value['mutable_surface'])<={'proposer','selector'} or not value['mutable_surface']:raise ValueError('METHOD_MUTABLE_SURFACE_REJECTED')
    store.read_artifact(value['content_sha256']);store.read_artifact(value['authority_evidence_sha256'])
    if value['parent_version_id'] and not store.get('method_versions',value['parent_version_id']):raise ValueError('METHOD_PARENT_MISSING')
    if value['acceptance_verdict_id']:
        verdict=validate_verdict(store,store.get('verdicts',value['acceptance_verdict_id']) or {})
        if verdict['candidate_sha256']!=value['content_sha256']:raise ValueError('METHOD_ACCEPTANCE_BINDING_DRIFT')
    return _immutable(store,'method_versions',{**value,'schema_version':2})


def bind_generation(store,value):
    required={'id','method_version_id','attempt_ref','input_capsule_sha256','protocol_sha256','candidate_sha256','trace_sha256'}
    if set(value)!=required:raise ValueError('METHOD_GENERATION_INVALID')
    method=store.get('method_versions',value['method_version_id'])
    if not method or not method.get('acceptance_verdict_id'):raise ValueError('METHOD_NOT_ACCEPTED')
    ref=value['attempt_ref'];attempt=store.get('generation_attempts',ref['id']) if ref.get('kind')=='generation_attempts' else None
    if not attempt or digest(canonical(attempt))!=ref.get('sha256') or attempt.get('status')!='completed' or attempt.get('method_version_id')!=method['id']:
        raise ValueError('METHOD_REAL_GENERATION_REQUIRED')
    for k in ('input_capsule_sha256','protocol_sha256','candidate_sha256','trace_sha256'):
        if attempt.get(k)!=value[k]:raise ValueError('METHOD_GENERATION_BINDING_DRIFT')
        store.read_artifact(value[k])
    source_ref=attempt.get('source_attempt_ref') or {}
    source=store.get(source_ref.get('kind'),source_ref.get('id')) if source_ref.get('kind') in {'task_family_attempts','broker_attempts'} else None
    if not source or source.get('status')!='completed' or digest(canonical(source))!=source_ref.get('sha256') or value['candidate_sha256'] not in source.get('artifacts',{}).values():raise ValueError('METHOD_REAL_GENERATION_REQUIRED')
    trace=json.loads(store.read_artifact(value['trace_sha256']))
    if not isinstance(trace,list) or (source.get('receipt') or {}).get('trace_sha256')!=value['trace_sha256'] or not (source.get('receipt') or {}).get('tool_results'):raise ValueError('METHOD_REAL_GENERATION_REQUIRED')
    method_text=store.read_artifact(method['content_sha256']).decode()
    if not any(o.get('type')=='response_item' and o.get('payload',{}).get('type') in {'function_call_output','custom_tool_call_output'} and method_text in str(o['payload'].get('output','')) for o in trace):raise ValueError('METHOD_ACTUAL_READ_REQUIRED')
    prior=store.get('method_generations',value['id'])
    return _immutable(store,'method_generations',{**value,'schema_version':2,'created_at':prior['created_at'] if prior else now()})


def method_comparison_design(protocol):
    """Freeze knowable design before generation; bind outputs afterwards."""
    return {k:v for k,v in protocol.items() if k not in {
        'id','created_at','parent_sha256','candidate_sha256','arm_files','arm_packages'}}


def preregister_method_comparison(store,value):
    required={'id','method_version_id','previous_method_version_id','input_capsule_sha256','generation_identity','generation_budget','downstream_design'}
    if set(value)!=required:raise ValueError('METHOD_COMPARISON_PLAN_INVALID')
    method=store.get('method_versions',value['method_version_id']);previous=store.get('method_versions',value['previous_method_version_id'])
    if not method or not previous or method.get('parent_version_id')!=previous['id'] or not all(x.get('acceptance_verdict_id') for x in (method,previous)):
        raise ValueError('METHOD_COMPARISON_LINEAGE_REQUIRED')
    from .final_gate import _finite
    identity=value['generation_identity'];budget=value['generation_budget']
    if not isinstance(identity,dict) or not all(identity.get(k) for k in ('kind','model','effort','harness','runtime_sha256')):raise ValueError('METHOD_GENERATION_COMPARABILITY_REQUIRED')
    if not isinstance(budget,dict) or set(budget)!={'currency','money','tokens','wall_seconds'} or not isinstance(budget['currency'],str) or any(not _finite(budget[k]) for k in ('money','tokens','wall_seconds')):raise ValueError('METHOD_GENERATION_BUDGET_REQUIRED')
    design=value['downstream_design']
    needed={'schema_version','cost_accounting','entrypoint','execution_identity','oracle_sha256','environment','model','max_verified_effort','cases','budget_seconds','cost_limits','min_gain','alpha','minimum_cases','final_exposed','max_attempts'}
    if not isinstance(design,dict) or not needed<=set(design) or any(k in design for k in ('arm_files','parent_sha256','candidate_sha256','created_at','arm_packages')):
        raise ValueError('METHOD_COMPARISON_PLAN_INVALID')
    store.read_artifact(value['input_capsule_sha256']);store.read_artifact(design['oracle_sha256'])
    for case in design['cases']:
        for h in case.get('input_files',{}).values():store.read_artifact(h)
    prior=store.get('method_comparison_plans',value['id'])
    return _immutable(store,'method_comparison_plans',{**value,'schema_version':1,
        'method_version_bindings':{x['id']:digest(canonical(x)) for x in (method,previous)},'created_at':prior['created_at'] if prior else now()})


def validate_method_generation(store,method_id,generation_id,candidate_sha256):
    generation=store.get('method_generations',generation_id)
    if not generation or generation['method_version_id']!=method_id or generation['candidate_sha256']!=candidate_sha256:
        raise ValueError('METHOD_REAL_GENERATION_REQUIRED')
    return generation


def method_report(store,method_id):
    method=store.get('method_versions',method_id)
    if not method:raise ValueError('METHOD_NOT_FOUND')
    generations=[x for x in store.list('method_generations') if x['method_version_id']==method_id]
    comparisons=[x for x in store.list('method_comparisons') if x['method_version_id']==method_id]
    current=[];history=[];missing=[];accepted=False
    try:_current_method(store,method);accepted=True
    except (ValueError,KeyError,OSError) as ex:missing.append(str(ex))
    for comparison in comparisons:
        problems=[]
        try:
            if comparison.get('schema_version')!=3 or comparison.get('status')!='independent_downstream_verified':raise ValueError('METHOD_COMPARISON_REVALIDATION_REQUIRED')
            evidence=_method_comparison_evidence(store,comparison)
            if any(comparison.get(k)!=v for k,v in evidence.items()):raise ValueError('METHOD_COMPARISON_DEPENDENCY_DRIFT')
            current.append(comparison['id'])
        except (ValueError,KeyError,OSError) as ex:problems.append(str(ex));missing.extend(problems)
        history.append({'id':comparison['id'],'historical_status':comparison.get('status'),'verified_at':comparison.get('verified_at'),
                        'current':not problems,'missing':problems})
    if not current:missing.append('INDEPENDENT_NEXT_GENERATION_DOWNSTREAM_COMPARISON_REQUIRED')
    if not generations:missing.append('REAL_NEXT_GENERATION_REQUIRED')
    return {'method_version_id':method_id,'content_sha256':method['content_sha256'],'accepted':accepted,
            'generation_ids':[x['id'] for x in generations],'comparison_ids':current,'comparison_history':history,
            'method_rsi':'VERIFIED_BOUNDED_DOWNSTREAM' if current and accepted and not missing else 'UNVERIFIED','missing':sorted(set(missing))}


def bind_method_comparison(store,value):
    """Independent downstream gate, separate from accepting the method itself."""
    required={'id','plan_id','method_version_id','previous_method_version_id','baseline_generation_id','next_generation_id','verdict_id'}
    if set(value)!=required:raise ValueError('METHOD_COMPARISON_INVALID')
    evidence=_method_comparison_evidence(store,value)
    for ref in evidence['generation_attempt_refs']:store.artifact(canonical(store.get(ref['kind'],ref['id'])))
    prior=store.get('method_comparisons',value['id'])
    return _immutable(store,'method_comparisons',{**value,**evidence,'schema_version':3,'status':'independent_downstream_verified',
        'verified_at':prior['verified_at'] if prior else now()})


def _current_method(store,method):
    verdict=validate_verdict(store,store.get('verdicts',method.get('acceptance_verdict_id')) or {})
    if verdict.get('candidate_sha256')!=method['content_sha256']:raise ValueError('METHOD_ACCEPTANCE_BINDING_DRIFT')
    store.read_artifact(method['content_sha256'])
    if verdict.get('schema_version')==2:
        from .final_gate import assert_current_final
        assert_current_final(store,verdict)
    return verdict


def _method_comparison_evidence(store,value):
    """Read-only current dependency check; historical rows never certify today."""
    method=store.get('method_versions',value['method_version_id']);previous=store.get('method_versions',value['previous_method_version_id'])
    baseline=store.get('method_generations',value['baseline_generation_id']);next_=store.get('method_generations',value['next_generation_id'])
    if not method or not previous or method.get('parent_version_id')!=previous['id'] or not baseline or not next_:
        raise ValueError('METHOD_COMPARISON_LINEAGE_REQUIRED')
    if baseline['method_version_id']!=previous['id'] or next_['method_version_id']!=method['id']:raise ValueError('METHOD_COMPARISON_LINEAGE_REQUIRED')
    for item in (method,previous):_current_method(store,item)
    verdict=validate_verdict(store,store.get('verdicts',value['verdict_id']) or {})
    if verdict.get('schema_version')!=2 or verdict['id'] in {method.get('acceptance_verdict_id'),previous.get('acceptance_verdict_id')}:
        raise ValueError('METHOD_DOWNSTREAM_EVIDENCE_REUSE_REJECTED')
    if verdict.get('parent_package_digest',verdict.get('parent_sha256'))!=baseline['candidate_sha256'] or verdict.get('candidate_package_digest',verdict.get('candidate_sha256'))!=next_['candidate_sha256']:
        raise ValueError('METHOD_DOWNSTREAM_BINDING_DRIFT')
    protocol=store.get('protocols',verdict['protocol_id'])
    plan=store.get('method_comparison_plans',value['plan_id'])
    if not plan or any(plan[k]!=value[k] for k in ('method_version_id','previous_method_version_id')) or method_comparison_design(protocol)!=plan['downstream_design']:
        raise ValueError('METHOD_COMPARISON_DESIGN_DRIFT')
    if plan.get('method_version_bindings')!={x['id']:digest(canonical(x)) for x in (method,previous)}:raise ValueError('METHOD_VERSION_BINDING_DRIFT')
    for generation in (baseline,next_):
        bind_generation(store,{k:generation[k] for k in ('id','method_version_id','attempt_ref','input_capsule_sha256','protocol_sha256','candidate_sha256','trace_sha256')})
        attempt=store.get('generation_attempts',generation['attempt_ref']['id'])
        if attempt.get('comparison_plan_id')!=plan['id'] or generation['input_capsule_sha256']!=plan['input_capsule_sha256']:
            raise ValueError('METHOD_COMPARISON_PLAN_BINDING_REQUIRED')
        source_ref=attempt['source_attempt_ref'];source=store.get(source_ref['kind'],source_ref['id'])
        if attempt.get('execution_identity')!=plan['generation_identity'] or source.get('receipt',{}).get('execution_identity')!=plan['generation_identity']:
            raise ValueError('METHOD_GENERATION_COMPARABILITY_DRIFT')
        from .final_gate import _finite
        try:
            frozen=datetime.fromisoformat(plan['created_at']);started=datetime.fromisoformat(attempt['started_at'])
            produced=datetime.fromisoformat(generation['created_at']);bound=datetime.fromisoformat(protocol['created_at'])
            if any(x.tzinfo is None for x in (frozen,started,produced,bound)) or not frozen<started<=produced<=bound:raise ValueError()
        except (KeyError,ValueError,TypeError):raise ValueError('METHOD_COMPARISON_NOT_PREREGISTERED')
    costs=_method_plan_costs(store,plan)
    from .final_gate import assert_current_final
    assert_current_final(store,verdict)
    return {'protocol_sha256':verdict['protocol_sha256'],'downstream_verdict_sha256':digest(canonical(verdict)),
        'generation_attempt_refs':costs['attempt_refs'],'generation_costs':costs['totals'],
        'dependency_sha256':digest(canonical({'plan':plan,'method':method,'previous':previous,'baseline':baseline,'next':next_,'verdict':verdict,'costs':costs}))}


def _method_plan_costs(store,plan):
    from decimal import Decimal
    from .final_gate import COST_KINDS,COST_TERMINAL_STATES,_attempt_relation_closure,_attempt_cost_entries,_accumulate_costs
    with store.connect() as db:
        unbound=db.execute("SELECT 1 FROM entities WHERE kind='generation_attempts' AND json_extract(data,'$.comparison_plan_id') IS NULL AND json_extract(data,'$.method_version_id') IN (?,?) AND json_extract(data,'$.input_capsule_sha256')=? LIMIT 1",(plan['method_version_id'],plan['previous_method_version_id'],plan['input_capsule_sha256'])).fetchone()
        if unbound:raise ValueError('METHOD_PLAN_COST_BINDING_REQUIRED')
        rows=db.execute("SELECT kind,data FROM entities WHERE kind IN ("+','.join('?' for _ in COST_KINDS)+") AND json_extract(data,'$.comparison_plan_id')=? LIMIT 4097",(*sorted(COST_KINDS),plan['id'])).fetchall()
        if len(rows)>4096:raise ValueError('COST_CLOSURE_TOO_LARGE')
        found={(r['kind'],json.loads(r['data'])['id']):json.loads(r['data']) for r in rows}
        found=_attempt_relation_closure(store,found,db)
    if not found:raise ValueError('METHOD_GENERATION_COST_REQUIRED')
    totals={'money':Decimal(0),'tokens':0,'wall_seconds':Decimal(0)};refs=[]
    for (kind,id_),row in sorted(found.items()):
        if row.get('comparison_plan_id') not in {None,plan['id']}:raise ValueError('METHOD_PLAN_COST_CONFLICT')
        if row.get('status') not in COST_TERMINAL_STATES[kind]:raise ValueError('COST_ATTEMPT_READBACK_REQUIRED')
        _accumulate_costs(totals,_attempt_cost_entries(kind,row),plan['generation_budget']['currency'])
        refs.append({'kind':kind,'id':id_,'sha256':digest(canonical(row))})
    if any(totals[k]>Decimal(str(plan['generation_budget'][k])) for k in totals):raise ValueError('METHOD_GENERATION_BUDGET_EXCEEDED')
    return {'attempt_refs':refs,'totals':{k:float(v) if k!='tokens' else v for k,v in totals.items()}}
