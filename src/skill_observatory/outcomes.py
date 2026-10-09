"""Independent task-result ingress; semantic model reviews cannot use this path.

The trusted domain verifier signs receipts. Candidate/model processes never get
the verifier key or Store. There is deliberately no HTTP/CLI claim-success API.
"""
from datetime import datetime
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
        verified_at=now()
        i.update(live_verified=True,live_run_id=run_id,updated_at=verified_at,
                 live_verified_at=verified_at,verified_skill_sha256=i['after_sha256'])
        return store.put('installations',i)
