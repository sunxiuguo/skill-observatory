"""Compile measured evaluation + independently signed domain/cost receipts.

This fixed kernel is never editable by a proposer. Missing human/domain truth
is HOLD. Signing helpers are trusted-owner ingress, not model/UI capabilities.
"""
import hmac
import math
import json
from decimal import Decimal
from pathlib import Path
from .store import canonical, digest, now
from .installations import key, seal_verdict, authority_expired,validate_verdict


def seal_owner_receipt(store,kind,receipt):
    if kind not in {'domain','cost'}:raise ValueError('FINAL_RECEIPT_KIND_INVALID')
    r=dict(receipt);r.pop('signature',None)
    return {**r,'signature':hmac.new(key(store),('final-'+kind+'-v1\0').encode()+canonical(r),'sha256').hexdigest()}


def _read(store,kind,receipt,evaluation_sha256,protocol_sha256):
    if not receipt:raise ValueError(kind.upper()+'_RECEIPT_REQUIRED')
    r=dict(receipt);sig=r.pop('signature','')
    expected=hmac.new(key(store),('final-'+kind+'-v1\0').encode()+canonical(r),'sha256').hexdigest()
    if not hmac.compare_digest(sig,expected):raise ValueError('FINAL_RECEIPT_UNTRUSTED')
    if r.get('evaluation_sha256')!=evaluation_sha256 or r.get('protocol_sha256')!=protocol_sha256:raise ValueError('FINAL_RECEIPT_BINDING_MISMATCH')
    store.read_artifact(r['evidence_sha256'])
    return r


def finalize(store,candidate_id,evaluation_id,domain_receipt=None,cost_receipt=None):
    c=store.get('candidates',candidate_id);e=store.get('evaluations',evaluation_id)
    if not c or not e:raise ValueError('FINAL_INPUT_MISSING')
    p=store.get('protocols',e['protocol_id']);missing=[]
    if not p or digest(canonical(p))!=e['protocol_sha256']:raise ValueError('PROTOCOL_DRIFT')
    evaluation_sha=store.artifact(canonical(e));protocol_sha=digest(canonical(p))
    prior=store.get('verdicts','verdict_'+candidate_id)
    if prior and prior.get('status')=='accepted':
        try:
            if prior.get('schema_version')!=2:raise ValueError('LEGACY_FINAL_VERDICT_REVALIDATION_REQUIRED')
            domain=_read(store,'domain',domain_receipt,evaluation_sha,protocol_sha)
            cost=_read(store,'cost',cost_receipt,evaluation_sha,protocol_sha)
            _reconcile_trials(store,p,e,domain)
            _reconcile_cost(store,c,e,p,cost)
            _cost_policy(c,e,p,cost)
            _candidate_gates(store,c,p,require=True)
            validate_verdict(store,prior)
            if prior.get('evaluation_sha256')!=evaluation_sha or prior.get('protocol_sha256')!=protocol_sha or prior.get('final_inputs_sha256')!=_final_inputs(store,c,domain,cost):
                raise ValueError('FINAL_VERDICT_INPUT_DRIFT')
            return prior
        except (ValueError,KeyError) as ex:
            # Preserve the signed historical verdict, but current consumers must
            # not keep using its old green gates after cost/effect/input drift.
            historical=store.artifact(canonical(prior));revoked={k:v for k,v in prior.items() if k!='signature'}
            revoked.update(status='hold',gates={k:False for k in prior['gates']},missing=[str(ex)],previous_verdict_sha256=historical,created_at=now())
            store.put('verdicts',revoked)
            raise
    attempt=store.get('evaluation_attempts',e['attempt_id'])
    if not attempt or attempt.get('result_sha256')!=evaluation_sha:missing.append('DURABLE_ATTEMPT_LEDGER_REQUIRED')
    arms=p.get('arm_files',{});parent=arms.get('parent',{});candidate=arms.get('candidate',{})
    package_gates,current_missing=_candidate_gates(store,c,p)
    missing.extend(current_missing)
    if parent.get('SKILL.md')!=c['parent_sha256'] or candidate.get('SKILL.md')!=c['candidate_sha256']:
        missing.append('FINAL_CANDIDATE_HASH_MISMATCH')
    store.read_artifact(c['candidate_sha256'])
    missing.extend(x for x in e.get('missing',[]) if x not in {'DOMAIN_GUARDRAIL_RECEIPT_REQUIRED','COST_COVERAGE_REQUIRED'})
    if p.get('synthetic') or p.get('final_exposed'):missing.append('INDEPENDENT_TRUTH_REQUIRED')
    domain={};cost={}
    try:
        domain=_read(store,'domain',domain_receipt,evaluation_sha,protocol_sha)
        final_ids={x['id'] for x in p['cases'] if x['split']=='final'}
        if set(domain.get('case_ids',[]))!=final_ids or domain.get('oracle_sha256')!=p['oracle_sha256']:
            raise ValueError('DOMAIN_COVERAGE_OR_ORACLE_DRIFT')
        _reconcile_trials(store,p,e,domain)
        for gate in ('independent_final','comparable','guardrails_pass','regressions_pass'):
            if domain.get(gate) is not True:missing.append(gate.upper()+'_REQUIRED')
        if not domain.get('regression_case_ids') or not set(domain['regression_case_ids'])<=final_ids:
            missing.append('REGRESSION_COVERAGE_REQUIRED')
        if not domain.get('guardrail_case_ids') or not set(domain['guardrail_case_ids'])<=final_ids:
            missing.append('GUARDRAIL_COVERAGE_REQUIRED')
    except (ValueError,KeyError) as ex:missing.append(str(ex))
    try:
        cost=_read(store,'cost',cost_receipt,evaluation_sha,protocol_sha)
        _reconcile_cost(store,c,e,p,cost)
        _cost_policy(c,e,p,cost)
    except (ValueError,KeyError) as ex:missing.append(str(ex))
    gain=e.get('paired_gain_lower_bound')
    if type(gain) not in {int,float} or not math.isfinite(gain) or gain<=p['min_gain']:missing.append('NO_CONFIRMED_GAIN')
    missing=sorted(set(missing));accepted=not missing
    gates={g:accepted for g in ('authorization_matches','hashes_current','comparable','independent_final',
        'coverage_sufficient','gain_pass','guardrails_pass','regressions_pass','budget_pass')}
    verdict={'schema_version':2,'id':'verdict_'+candidate_id,'status':'accepted' if accepted else 'hold','candidate_id':candidate_id,
        'parent_sha256':c['parent_sha256'],'candidate_sha256':c['candidate_sha256'],'protocol_id':p['id'],
        'protocol_sha256':protocol_sha,'evaluation_sha256':evaluation_sha,'final_inputs_sha256':_final_inputs(store,c,domain,cost),**package_gates,'gates':gates,'missing':missing,'created_at':now()}
    verdict['domain_receipt_sha256']=store.artifact(canonical(domain_receipt)) if domain_receipt else None
    verdict['cost_receipt_sha256']=store.artifact(canonical(cost_receipt)) if cost_receipt else None
    if accepted:verdict=seal_verdict(store,verdict)
    store.put('verdicts',verdict)
    if domain_receipt:store.artifact(canonical(domain_receipt))
    if cost_receipt:store.artifact(canonical(cost_receipt))
    return verdict



def _final_inputs(store,candidate,domain,cost):
    frozen={k:candidate.get(k) for k in ('id','authority_id','target','parent_sha256','candidate_sha256','parent_package','candidate_package','cost_attempt_ids','review_id','review_binding_sha256','experiment_id','generation_id','proposer_method_version_id','owner_incident_id','skill_id')}
    frozen['authority']=store.get('authority_grants',candidate.get('authority_id'))
    return digest(canonical({'candidate':frozen,'domain':domain,'cost':cost}))


def _candidate_gates(store,c,p,require=False):
    """Current usability, shared by first final, cache and dependent reports.

    A signed acceptance remains historical evidence. Current disk must match
    the evaluated parent, or the exact candidate in a matching original-owner
    installation/intent. Such lifecycle readback never consumes final again.
    """
    grant=store.get('authority_grants',c.get('authority_id'));packaged=bool(c.get('parent_package') or c.get('candidate_package'))
    missing=[];extra={};current=False
    try:
        installations=[i for i in store.list('installations') if i.get('candidate_id')==c['id'] and
            i.get('owner')=='skill-evolution-loop' and i.get('status') in {'owner_prepared','activation_pending','activated'} and
            i.get('before_sha256')==c['parent_sha256'] and i.get('after_sha256')==c['candidate_sha256']]
        if packaged:
            from .packages import read_package,changed_files,snapshot_package,trial_manifest
            a=read_package(store,c['parent_package']);b=read_package(store,c['candidate_package']);harness=p.get('harness_files',{})
            changed=changed_files(store,c['parent_package'],c['candidate_package'],grant.get('changed_files') if grant else [])
            if set(harness)&(set(a)|set(b)):raise ValueError('PACKAGE_HARNESS_COLLISION')
            for arm,files,manifest in [('parent',a,c['parent_package']),('candidate',b,c['candidate_package'])]:
                if p['arm_files'][arm]!={**{n:digest(v) for n,v in files.items()},**harness}:raise ValueError('FULL_PACKAGE_EVALUATION_BINDING_REQUIRED')
                if p.get(arm+'_package_digest')!=manifest['package_digest']:raise ValueError('FINAL_PACKAGE_PROTOCOL_BINDING_DRIFT')
                if not grant or grant.get(arm+'_package_digest')!=manifest['package_digest']:raise ValueError('PACKAGE_AUTHORITY_BINDING_DRIFT')
                loaded={n:store.read_artifact(v) for n,v in p['arm_files'][arm].items()}
                actual=trial_manifest(p,arm,loaded,{})
                modes={v['path']:v['mode'] for v in actual['entries'] if v['path'] in files}
                from .packages import execution_manifest
                if execution_manifest(files,modes)!=manifest:raise ValueError('FULL_PACKAGE_EVALUATION_BINDING_REQUIRED')
            extra={'parent_package_digest':c['parent_package']['package_digest'],'candidate_package_digest':c['candidate_package']['package_digest'],'changed_files':changed}
            disk=snapshot_package(store,c['target'])
            current=disk==c['parent_package'] or (disk==c['candidate_package'] and any(i.get('target_root')==c['target'] and i.get('before_package')==c['parent_package'] and i.get('after_package')==c['candidate_package'] for i in installations))
        else:
            parent=p['arm_files']['parent'];candidate=p['arm_files']['candidate']
            if set(parent)!=set(candidate) or {k for k in parent if parent[k]!=candidate[k]}!={'SKILL.md'}:missing.append('AUTHORIZED_TEXT_SURFACE_REQUIRED')
            target=Path(c['target'])
            if not target.is_symlink() and not any(x.is_symlink() for x in target.parents) and target.is_file():
                disk=digest(target.read_bytes())
                current=disk==c['parent_sha256'] or (disk==c['candidate_sha256'] and any(i.get('target')==c['target'] for i in installations))
        if not current:missing.append('DRIFT_HOLD')
        authorized=bool(grant and grant.get('status')=='authorized' and grant.get('owner')=='skill-evolution-loop' and
            grant.get('surface')==('package' if packaged else 'single_text_file') and grant.get('target')==c['target'] and not authority_expired(grant.get('expires_at')))
        if not authorized:missing.append('OWNER_AUTHORITY_HOLD')
        else:store.read_artifact(grant['evidence_sha256'])
    except (ValueError,KeyError,OSError) as ex:missing.append(str(ex))
    if require and missing:raise ValueError(missing[0])
    return extra,missing


def assert_current_final(store,verdict):
    """Before installation, recheck the frozen cost/effect universe too."""
    validate_verdict(store,verdict)
    if verdict.get('schema_version')!=2:return # explicitly legacy owner ingress
    if not verdict.get('cost_receipt_sha256') or not verdict.get('domain_receipt_sha256'):raise ValueError('FINAL_VERDICT_BINDING_REQUIRED')
    c=store.get('candidates',verdict['candidate_id']);e=json.loads(store.read_artifact(verdict['evaluation_sha256']))
    p=store.get('protocols',verdict['protocol_id'])
    if not c or not p or digest(canonical(p))!=verdict['protocol_sha256'] or store.get('evaluations',e['id'])!=e:raise ValueError('FINAL_VERDICT_INPUT_DRIFT')
    _candidate_gates(store,c,p,require=True)
    domain=_read(store,'domain',json.loads(store.read_artifact(verdict['domain_receipt_sha256'])),verdict['evaluation_sha256'],verdict['protocol_sha256'])
    cost=_read(store,'cost',json.loads(store.read_artifact(verdict['cost_receipt_sha256'])),verdict['evaluation_sha256'],verdict['protocol_sha256'])
    _reconcile_trials(store,p,e,domain);_reconcile_cost(store,c,e,p,cost);_cost_policy(c,e,p,cost)
    if verdict.get('final_inputs_sha256')!=_final_inputs(store,c,domain,cost):raise ValueError('FINAL_VERDICT_INPUT_DRIFT')


def _cost_policy(candidate,evaluation,protocol,cost):
    if cost.get('all_attempts_covered') is not True or cost.get('budget_pass') is not True:raise ValueError('COST_COVERAGE_REQUIRED')
    if evaluation['attempt_id'] not in cost.get('attempt_ids',[]):raise ValueError('FINAL_ATTEMPT_COST_MISSING')
    if not candidate.get('cost_attempt_ids') or not set(candidate['cost_attempt_ids'])<=set(cost.get('attempt_ids',[])):raise ValueError('EXPLORATION_COST_COVERAGE_REQUIRED')
    for field in ('money','tokens','wall_seconds'):
        value=cost.get(field);limit=(protocol.get('cost_limits') or {}).get(field)
        if not _finite(value):raise ValueError('COST_TRUTH_REQUIRED')
        if not _finite(limit):raise ValueError('FROZEN_COST_POLICY_REQUIRED')
        if value>limit:raise ValueError('COST_BUDGET_EXCEEDED')


# Known invoice != known side effects. These are explicit read-back terminal
# states; interrupted/failed_after_dispatch/unknown_after_dispatch stay HOLD.
COST_TERMINAL_STATES={
    'review_attempts':{'completed','reviewed','failed','rejected'},
    'evaluation_attempts':{'completed','completed_hold','failed','refused'},
    'broker_attempts':{'completed','failed','rejected'},
    'generation_attempts':{'completed','failed','rejected'},
    'task_family_attempts':{'completed','failed','rejected'},
}


def _related_attempts(store,candidate,evaluation,protocol):
    """Resolve actual runtime edges as well as declared exploration roots."""
    found={};seeds=set(candidate.get('cost_attempt_ids') or [])|{evaluation['attempt_id']}
    review=store.get('reviews',candidate.get('review_id')) or {}
    with store.connect() as db:
        if candidate.get('generation_id'):
            generation=store.get('method_generations',candidate['generation_id'],db)
            ref=(generation or {}).get('attempt_ref') or {}
            item=store.get(ref.get('kind'),ref.get('id'),db) if ref.get('kind') in COST_KINDS else None
            if not item or digest(canonical(item))!=ref.get('sha256'):raise ValueError('COST_SOURCE_ATTEMPT_DRIFT')
            found[(ref['kind'],ref['id'])]=item
        for kind in sorted(COST_KINDS):
            rows=db.execute("SELECT data FROM entities WHERE kind=? AND (json_extract(data,'$.candidate_id')=? OR json_extract(data,'$.protocol_id')=? OR json_extract(data,'$.evaluation_id')=? OR json_extract(data,'$.attempt_id')=? OR json_extract(data,'$.evaluation_attempt_id')=? OR json_extract(data,'$.run_id')=?) LIMIT 4097",
                (kind,candidate['id'],protocol['id'],evaluation['id'],evaluation['attempt_id'],evaluation['attempt_id'],review.get('run_id'))).fetchall()
            if len(rows)>4096:raise ValueError('COST_CLOSURE_TOO_LARGE')
            for row in rows:
                item=json.loads(row[0]);found[(kind,item['id'])]=item
        main=store.get('evaluation_attempts',evaluation['attempt_id'],db)
        if main:found[('evaluation_attempts',main['id'])]=main
        for id_ in seeds:
            if any(key_[1]==id_ for key_ in found):continue
            matches=[(kind,store.get(kind,id_,db)) for kind in sorted(COST_KINDS)]
            matches=[(kind,item) for kind,item in matches if item]
            if len(matches)!=1:raise ValueError('COST_ATTEMPT_ID_AMBIGUOUS_OR_MISSING')
            kind,item=matches[0];found[(kind,id_)]=item
        return _attempt_relation_closure(store,found,db)


def _attempt_relation_closure(store,found,db):
    """Typed forward/reverse runtime edges, shared with method exploration."""
    for _ in range(32):
        expanded=False
        for item in list(found.values()):
            for field in ('source_attempt_ref','retry_of_ref','parent_attempt_ref'):
                ref=item.get(field)
                if not ref:continue
                if not isinstance(ref,dict) or set(ref)!={'kind','id','sha256'}:raise ValueError('COST_ATTEMPT_RELATION_REQUIRED')
                if ref.get('kind') not in COST_KINDS:raise ValueError('COST_ATTEMPT_RELATION_REQUIRED')
                ident=(ref['kind'],ref['id']);source=store.get(*ident,db)
                if not source or digest(canonical(source))!=ref.get('sha256'):raise ValueError('COST_SOURCE_ATTEMPT_DRIFT')
                if ident not in found:found[ident]=source;expanded=True
        for ident in list(found):
            for field in ('source_attempt_ref','retry_of_ref','parent_attempt_ref'):
                incoming=db.execute("SELECT kind,data FROM entities WHERE kind IN ("+','.join('?' for _ in COST_KINDS)+") AND json_extract(data,?)=? AND json_extract(data,?)=? LIMIT 4097",
                    (*sorted(COST_KINDS),'$.'+field+'.kind',ident[0],'$.'+field+'.id',ident[1])).fetchall()
                if len(incoming)>4096:raise ValueError('COST_CLOSURE_TOO_LARGE')
                for row in incoming:
                    item=json.loads(row['data']);key_=(row['kind'],item['id'])
                    if key_ not in found:found[key_]=item;expanded=True
        if not expanded:break
        if len(found)>4096:raise ValueError('COST_CLOSURE_TOO_LARGE')
    else:raise ValueError('COST_CLOSURE_TOO_LARGE')
    return found


def _finite(value):
    return type(value) in {int, float} and math.isfinite(value) and value >= 0


def _reconcile_trials(store, protocol, evaluation, domain=None):
    """Derive coverage and scores from immutable arm outputs and frozen labels."""
    if protocol.get('schema_version') != 2 or evaluation.get('schema_version') != 2:
        raise ValueError('FINAL_SCHEMA_RECONCILIATION_REQUIRED')
    cases = [c for c in protocol['cases'] if c['split'] == 'final']
    expected = {(c['id'], arm) for c in cases for arm in ('parent','candidate')}
    trials = evaluation.get('trials', [])
    actual = [(t.get('case_id'),t.get('arm')) for t in trials]
    if len(actual) != len(set(actual)) or set(actual) != expected:raise ValueError('FINAL_CASE_ARM_COVERAGE_MISMATCH')
    labels = json.loads(store.read_artifact(protocol['oracle_sha256']))
    oracle=None
    if labels.get('kind')=='argparse-cli-v1':
        from .task_families import ArgparseTaskOracle
        oracle=ArgparseTaskOracle.from_descriptor(store,labels)
        label_ids=set(labels['cases'])
    else:label_ids=set(labels)
    if label_ids != {c['id'] for c in protocol['cases']}:raise ValueError('ORACLE_CASE_DRIFT')
    contexts = set(); outcomes = {}
    by_case={c['id']:c for c in cases}
    for case in cases:
        if digest(canonical(case.get('input_files',{})))!=case.get('inputs_sha256'):raise ValueError('FINAL_INPUT_MANIFEST_REQUIRED')
        for kind, value in (('input',case['inputs_sha256']),('evidence',case['evidence_sha256'])):
            claim=store.get('final_sets','final_case_'+digest(canonical([kind,value])))
            if not claim or claim.get('attempt_id')!=evaluation['attempt_id'] or claim.get('status')!='consumed':raise ValueError('FINAL_CONSUMPTION_BINDING_REQUIRED')
    for case in cases:
        if case.get('source') not in {'real_incident','real_success','regression','prospective_real','adversarial'}:
            raise ValueError('REAL_CASE_EVIDENCE_REQUIRED')
        store.read_artifact(case['evidence_sha256'])
    for trial in trials:
        frozen = dict(trial); h = frozen.pop('receipt_artifact', None)
        if h is None or store.read_artifact(h) != canonical(frozen):raise ValueError('TRIAL_RECEIPT_DRIFT')
        receipt = trial.get('receipt', {})
        if receipt.get('status') != 'completed' or type(receipt.get('exit_code')) is not int:
            raise ValueError('INCOMPLETE_FINAL_TRIAL')
        expected_inputs={**protocol['arm_files'][trial['arm']],**by_case[trial['case_id']]['input_files']}
        measured=receipt if receipt.get('input_manifest_sha256') else receipt.get('container') or {}
        if protocol.get('arm_packages'):
            from .packages import trial_manifest
            arm={n:store.read_artifact(v) for n,v in protocol['arm_files'][trial['arm']].items()}
            inputs={n:store.read_artifact(v) for n,v in by_case[trial['case_id']]['input_files'].items()}
            expected_manifest=trial_manifest(protocol,trial['arm'],arm,inputs)
            if measured.get('input_manifest')!=expected_manifest or measured.get('input_manifest_sha256')!=expected_manifest['package_digest']:raise ValueError('TRIAL_INPUT_BINDING_DRIFT')
        elif protocol.get('parent_package_digest') or protocol.get('candidate_package_digest'):
            raise ValueError('EXECUTION_MANIFEST_REQUIRED')
        elif measured.get('input_manifest_sha256')!=digest(canonical(expected_inputs)):raise ValueError('TRIAL_INPUT_BINDING_DRIFT')
        artifacts = trial.get('artifacts', {})
        for h in artifacts.values():store.read_artifact(h)
        passed = oracle.grade(trial['case_id'],{n:store.read_artifact(h) for n,h in artifacts.items()},receipt) if oracle else receipt['exit_code'] == 0 and artifacts == labels[trial['case_id']]
        if type(trial.get('passed')) is not bool or trial['passed'] != passed:raise ValueError('TRIAL_SCORE_MISMATCH')
        outcomes[(trial['case_id'],trial['arm'])] = int(passed)
        identity = protocol.get('execution_identity', {})
        if identity.get('kind') != 'deterministic-python':
            if receipt.get('execution_identity') != identity:raise ValueError('TRIAL_EXECUTION_IDENTITY_DRIFT')
        context = receipt.get('container_id') or (receipt.get('container') or {}).get('container_id') or receipt.get('context_id')
        if not context or context in contexts:raise ValueError('INDEPENDENT_ARM_CONTEXT_REQUIRED')
        contexts.add(context)
    n = len(cases)
    if not n:raise ValueError('FINAL_CASES_REQUIRED')
    gain = sum(outcomes[(c['id'],'candidate')]-outcomes[(c['id'],'parent')] for c in cases)/n
    lower = gain-math.sqrt(2*math.log(1/protocol['alpha'])/n)
    if not all(type(evaluation.get(k)) in {int,float} and math.isfinite(evaluation[k]) and math.isclose(evaluation[k], v, abs_tol=1e-12)
               for k,v in (('paired_gain',gain),('paired_gain_lower_bound',lower),('paired_cases',n))):
        raise ValueError('PAIRED_SCORE_RECONCILIATION_MISMATCH')
    if domain is not None:
        if domain.get('schema_version') != 2:raise ValueError('DOMAIN_SCHEMA_RECONCILIATION_REQUIRED')
        for category, field in (('regression','regression_case_ids'),('guardrail','guardrail_case_ids')):
            required = {c['id'] for c in cases if category in c.get('categories', []) or c.get('source') == category}
            ids = domain.get(field, [])
            if not required or len(ids) != len(set(ids)) or set(ids) != required:raise ValueError('DOMAIN_CATEGORY_EXECUTION_MISMATCH')
            if any(not outcomes[(cid,'candidate')] for cid in required):raise ValueError('DOMAIN_CATEGORY_FAILED')
        if len(domain.get('case_ids', [])) != n:raise ValueError('DOMAIN_CASE_DUPLICATE')
        if set(domain.get('trial_receipt_sha256', [])) != {t['receipt_artifact'] for t in trials}:
            raise ValueError('DOMAIN_TRIAL_BINDING_REQUIRED')


COST_KINDS = {'review_attempts','evaluation_attempts','broker_attempts','generation_attempts','task_family_attempts'}


def _attempt_cost_entries(kind,row,evaluation=None,protocol=None):
    if evaluation and kind=='evaluation_attempts' and row['id']==evaluation['attempt_id']:
        if row.get('result_sha256')!=digest(canonical(evaluation)):raise ValueError('COST_EVALUATION_BINDING_MISMATCH')
        return [dict(t.get('cost') or {},wall_seconds=(t.get('receipt') or {}).get('wall_seconds')) for t in evaluation['trials']]
    if evaluation and kind=='task_family_attempts' and row.get('attempt_id')==evaluation['attempt_id'] and any(t.get('trial_id')==row['id'] for t in evaluation['trials']):
        trial=next(t for t in evaluation['trials'] if t.get('trial_id')==row['id'])
        if row.get('protocol_id')!=protocol['id'] or any(row.get(k)!=trial.get(k) for k in ('case_id','arm','passed','receipt','artifacts','cost')):raise ValueError('COST_CHILD_EVALUATION_DRIFT')
        return []
    if kind=='generation_attempts' and row.get('source_attempt_ref') and 'cost' not in row:return []
    value=row.get('cost',row)
    if not isinstance(value,dict):raise ValueError('COST_TRUTH_REQUIRED')
    cost=dict(value)
    if 'wall_seconds' not in cost:cost['wall_seconds']=(row.get('receipt') or {}).get('wall_seconds')
    return [cost]


def _accumulate_costs(totals,entries,currency):
    for entry in entries:
        if entry.get('currency')!=currency:raise ValueError('COST_CURRENCY_REQUIRED')
        for field in totals:
            v=entry.get(field)
            if not _finite(v) or (field=='tokens' and type(v) is not int):raise ValueError('COST_TRUTH_REQUIRED')
            totals[field]+=Decimal(str(v)) if field!='tokens' else v
        if any(type(entry.get(k)) is not int or entry[k]<0 for k in ('input_tokens','output_tokens','cached_input_tokens')):raise ValueError('COST_TOKEN_COMPONENTS_REQUIRED')
        if entry['cached_input_tokens']>entry['input_tokens'] or entry['input_tokens']+entry['output_tokens']!=entry['tokens']:raise ValueError('COST_TOKEN_COMPONENT_MISMATCH')


def _reconcile_cost(store, candidate, evaluation, protocol, cost):
    """All totals derive from typed immutable ledger references, never flags."""
    refs = cost.get('attempt_refs')
    if cost.get('schema_version') != 2 or not isinstance(refs,list) or not refs:
        raise ValueError('COST_TYPED_ATTEMPTS_REQUIRED')
    policy = protocol.get('cost_accounting') or {}
    if policy.get('wall_basis') not in {'sum_duration','elapsed'} or not isinstance(policy.get('currency'),str):
        raise ValueError('FROZEN_COST_ACCOUNTING_REQUIRED')
    resolved = {}; totals = {'money':Decimal(0),'tokens':0,'wall_seconds':Decimal(0)}; intervals=[]
    for ref in refs:
        if not isinstance(ref,dict) or set(ref) != {'kind','id','sha256'} or ref['kind'] not in COST_KINDS:
            raise ValueError('COST_TYPED_ATTEMPT_INVALID')
        key_ = (ref['kind'],ref['id'])
        if key_ in resolved:raise ValueError('COST_ATTEMPT_DUPLICATE')
        row = store.get(ref['kind'],ref['id'])
        if not row or digest(canonical(row)) != ref['sha256']:raise ValueError('COST_ATTEMPT_MISSING_OR_DRIFT')
        store.read_artifact(ref['sha256'])
        if row.get('status') not in COST_TERMINAL_STATES[ref['kind']]:raise ValueError('COST_ATTEMPT_READBACK_REQUIRED')
        entries=_attempt_cost_entries(ref['kind'],row,evaluation,protocol)
        _accumulate_costs(totals,entries,policy['currency'])
        if policy['wall_basis']=='elapsed' and entries:
            from datetime import datetime
            try:
                a=datetime.fromisoformat(row['started_at']);b=datetime.fromisoformat(row['finished_at'])
                if a.tzinfo is None or b.tzinfo is None or b<a:raise ValueError()
                intervals.append((a.timestamp(),b.timestamp()))
            except (KeyError,ValueError,TypeError):raise ValueError('COST_CLOCK_REQUIRED')
        resolved[key_] = row
    related=_related_attempts(store,candidate,evaluation,protocol)
    if set(related)-set(resolved):raise ValueError('EXPLORATION_COST_COVERAGE_REQUIRED')
    if set(resolved)-set(related):raise ValueError('COST_UNRELATED_ATTEMPT_REJECTED')
    expected_ids={id_ for kind,id_ in related}
    actual_ids=[ref['id'] for ref in refs]
    if set(actual_ids)!=expected_ids or len(cost.get('attempt_ids',[]))!=len(set(cost.get('attempt_ids',[]))) or set(cost.get('attempt_ids',[]))!=expected_ids:
        raise ValueError('ALL_ATTEMPT_COST_COVERAGE_MISMATCH')
    if policy['wall_basis']=='elapsed':totals['wall_seconds']=Decimal(str(max(b for a,b in intervals)-min(a for a,b in intervals)))
    if cost.get('currency') != policy['currency']:raise ValueError('COST_CURRENCY_REQUIRED')
    for field,total in totals.items():
        value = cost.get(field)
        if not _finite(value) or (field=='tokens' and type(value) is not int):raise ValueError('COST_TRUTH_REQUIRED')
        if field=='wall_seconds':
            matches=math.isclose(value,float(total),rel_tol=1e-9,abs_tol=1e-9)
        else:matches=Decimal(str(value)) == Decimal(total)
        if not matches:raise ValueError('COST_TOTAL_RECONCILIATION_MISMATCH')
