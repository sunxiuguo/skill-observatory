"""Compile measured evaluation + independently signed domain/cost receipts.

This fixed kernel is never editable by a proposer. Missing human/domain truth
is HOLD. Signing helpers are trusted-owner ingress, not model/UI capabilities.
"""
import hmac
import math
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
        validate_verdict(store,prior)
        if prior.get('evaluation_sha256')!=evaluation_sha or prior.get('protocol_sha256')!=protocol_sha:
            raise ValueError('FINAL_VERDICT_ALREADY_SEALED')
        return prior
    attempt=store.get('evaluation_attempts',e['attempt_id'])
    if not attempt or attempt.get('result_sha256')!=evaluation_sha:missing.append('DURABLE_ATTEMPT_LEDGER_REQUIRED')
    arms=p.get('arm_files',{});parent=arms.get('parent',{});candidate=arms.get('candidate',{})
    if set(parent)!=set(candidate) or {k for k in parent if parent[k]!=candidate[k]}!={'SKILL.md'}:
        missing.append('AUTHORIZED_TEXT_SURFACE_REQUIRED')
    if parent.get('SKILL.md')!=c['parent_sha256'] or candidate.get('SKILL.md')!=c['candidate_sha256']:
        missing.append('FINAL_CANDIDATE_HASH_MISMATCH')
    store.read_artifact(c['candidate_sha256'])
    grant=store.get('authority_grants',c['authority_id'])
    authorized=bool(grant and grant.get('status')=='authorized' and grant.get('owner')=='skill-evolution-loop'
        and grant.get('surface')=='single_text_file' and grant.get('target')==c['target'] and not authority_expired(grant.get('expires_at')))
    if authorized:store.read_artifact(grant['evidence_sha256'])
    if not authorized:missing.append('OWNER_AUTHORITY_HOLD')
    target=Path(c['target'])
    current=not target.is_symlink() and target.is_file() and digest(target.read_bytes())==c['parent_sha256']
    if not current:missing.append('DRIFT_HOLD')
    missing.extend(x for x in e.get('missing',[]) if x not in {'DOMAIN_GUARDRAIL_RECEIPT_REQUIRED','COST_COVERAGE_REQUIRED'})
    if p.get('synthetic') or p.get('final_exposed'):missing.append('INDEPENDENT_TRUTH_REQUIRED')
    domain={};cost={}
    try:
        domain=_read(store,'domain',domain_receipt,evaluation_sha,protocol_sha)
        final_ids={x['id'] for x in p['cases'] if x['split']=='final'}
        if set(domain.get('case_ids',[]))!=final_ids or domain.get('oracle_sha256')!=p['oracle_sha256']:
            raise ValueError('DOMAIN_COVERAGE_OR_ORACLE_DRIFT')
        for gate in ('independent_final','comparable','guardrails_pass','regressions_pass'):
            if domain.get(gate) is not True:missing.append(gate.upper()+'_REQUIRED')
        if not domain.get('regression_case_ids') or not set(domain['regression_case_ids'])<=final_ids:
            missing.append('REGRESSION_COVERAGE_REQUIRED')
        if not domain.get('guardrail_case_ids') or not set(domain['guardrail_case_ids'])<=final_ids:
            missing.append('GUARDRAIL_COVERAGE_REQUIRED')
    except (ValueError,KeyError) as ex:missing.append(str(ex))
    try:
        cost=_read(store,'cost',cost_receipt,evaluation_sha,protocol_sha)
        if cost.get('all_attempts_covered') is not True or cost.get('budget_pass') is not True:
            missing.append('COST_COVERAGE_REQUIRED')
        if e['attempt_id'] not in cost.get('attempt_ids',[]):missing.append('FINAL_ATTEMPT_COST_MISSING')
        if not c.get('cost_attempt_ids') or not set(c['cost_attempt_ids'])<=set(cost.get('attempt_ids',[])):
            missing.append('EXPLORATION_COST_COVERAGE_REQUIRED')
        for field in ('money','tokens','wall_seconds'):
            if type(cost.get(field)) not in {int,float} or not math.isfinite(cost[field]) or cost[field]<0:missing.append('COST_TRUTH_REQUIRED')
            limit=(p.get('cost_limits') or {}).get(field)
            if type(limit) not in {int,float} or not math.isfinite(limit) or limit<0:missing.append('FROZEN_COST_POLICY_REQUIRED')
            elif type(cost.get(field)) in {int,float} and cost[field]>limit:missing.append('COST_BUDGET_EXCEEDED')
    except (ValueError,KeyError) as ex:missing.append(str(ex))
    gain=e.get('paired_gain_lower_bound')
    if type(gain) not in {int,float} or not math.isfinite(gain) or gain<=p['min_gain']:missing.append('NO_CONFIRMED_GAIN')
    missing=sorted(set(missing));accepted=not missing
    gates={g:accepted for g in ('authorization_matches','hashes_current','comparable','independent_final',
        'coverage_sufficient','gain_pass','guardrails_pass','regressions_pass','budget_pass')}
    verdict={'id':'verdict_'+candidate_id,'status':'accepted' if accepted else 'hold','candidate_id':candidate_id,
        'parent_sha256':c['parent_sha256'],'candidate_sha256':c['candidate_sha256'],'protocol_id':p['id'],
        'protocol_sha256':protocol_sha,'evaluation_sha256':evaluation_sha,'gates':gates,'missing':missing,'created_at':now()}
    if accepted:verdict=seal_verdict(store,verdict)
    store.put('verdicts',verdict)
    if domain_receipt:store.artifact(canonical(domain_receipt))
    if cost_receipt:store.artifact(canonical(cost_receipt))
    return verdict
