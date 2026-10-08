"""Runtime-owned single-file transactions. Other owners must supply adapters."""
from __future__ import annotations
import fcntl
import hmac
import json
import secrets
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timezone
from .store import atomic_write, canonical, digest, now


@contextmanager
def lock(store):
    with (store.root/'installation.lock').open('a') as f:
        fcntl.flock(f,fcntl.LOCK_EX)
        try:yield
        finally:fcntl.flock(f,fcntl.LOCK_UN)


def key(store):
    p=store.root/'verifier.key'
    with lock(store):
        if not p.exists():atomic_write(p,secrets.token_bytes(32))
        return p.read_bytes()


def seal_verdict(store, verdict):
    """Only the frozen trusted verifier calls this; not exposed in HTTP or CLI."""
    v={**verdict}; v.pop('signature',None)
    return {**v,'signature':hmac.new(key(store),canonical(v),'sha256').hexdigest()}


def validate_verdict(store, verdict):
    v={**verdict};sig=v.pop('signature','')
    if not hmac.compare_digest(sig,hmac.new(key(store),canonical(v),'sha256').hexdigest()):raise ValueError('VERDICT_UNTRUSTED')
    gates=('authorization_matches','hashes_current','comparable','independent_final','coverage_sufficient','gain_pass','guardrails_pass','regressions_pass','budget_pass')
    if verdict.get('status')!='accepted' or any(verdict.get('gates',{}).get(g) is not True for g in gates):raise ValueError('FINAL_GATE_HOLD')
    protocol=store.get('protocols',verdict['protocol_id'])
    if not protocol or digest(canonical(protocol))!=verdict['protocol_sha256']:raise ValueError('PROTOCOL_DRIFT')
    if protocol.get('synthetic') or protocol.get('final_exposed'):raise ValueError('INDEPENDENT_TRUTH_REQUIRED')
    return verdict


def authority_expired(expires_at):
    if expires_at is None:return False
    try:
        value=datetime.fromisoformat(expires_at.replace('Z','+00:00'))
        if value.tzinfo is None:raise ValueError('AUTHORITY_TIMEZONE_REQUIRED')
    except (TypeError,AttributeError,ValueError) as e:
        raise ValueError('AUTHORITY_EXPIRY_INVALID') from e
    return value<=datetime.now(timezone.utc)


def grant_owner(store,target,authority_id,evidence_sha256,expires_at=None):
    """Trusted local ingress for an explicit human single-Skill text grant.

    Not exposed over HTTP; the evidence artifact must contain the actual human
    authorization selected by the calling owner, never a review recommendation.
    """
    p=Path(target)
    if p.is_symlink() or not p.is_file() or p.name!='SKILL.md':raise ValueError('TARGET_NOT_REGULAR_SKILL')
    p=p.resolve()
    if '.codex/plugins/cache' in str(p) or '.agents/skills' in str(p):raise ValueError('OWNING_INSTALLER_REQUIRED')
    skill=next((s for s in store.list('skills') if Path(s['path']).resolve()==p.parent),None)
    if not skill or skill['owner']!='skill-evolution-loop' or skill['source']!='user-owned':raise ValueError('OWNER_REGISTRY_REQUIRED')
    if authority_expired(expires_at):raise ValueError('AUTHORITY_EXPIRED')
    store.read_artifact(evidence_sha256);p.read_bytes().decode('utf-8')
    g={'id':authority_id,'target':str(p),'owner':'skill-evolution-loop','surface':'single_text_file',
       'status':'authorized','evidence_sha256':evidence_sha256,'expires_at':expires_at}
    old=store.get('authority_grants',authority_id)
    if old:
        if any(old.get(k)!=v for k,v in g.items()):raise ValueError('AUTHORITY_DRIFT')
        return old
    return store.put('authority_grants',{**g,'created_at':now()})


def grant(store, target, authority_id, expires_at, evidence_sha256):
    p=Path(target)
    if p.is_symlink() or not p.is_file():raise ValueError('TARGET_NOT_REGULAR')
    p=p.resolve()
    if '.codex/plugins/cache' in str(p) or '.agents/skills' in str(p):raise ValueError('OWNING_INSTALLER_REQUIRED')
    store.read_artifact(evidence_sha256)
    g={"id":authority_id,"target":str(p),"owner":"skill-observatory","surface":"single_text_file","expires_at":expires_at,"authority_evidence_sha256":evidence_sha256,"created_at":now()}
    store.put('grants',g);return g


def promote(store, candidate_id):
    c=store.get('candidates',candidate_id)
    if not c:raise ValueError('CANDIDATE_NOT_FOUND')
    v=store.get('verdicts',c['verdict_id'])
    validate_verdict(store,v or {})
    g=store.get('grants',c['authority_id'])
    if not g or authority_expired(g['expires_at']) or g['target']!=c['target'] or g['owner']!='skill-observatory':raise ValueError('AUTHORITY_HOLD')
    after=store.read_artifact(c['candidate_sha256'])
    if v['parent_sha256']!=c['parent_sha256'] or v['candidate_sha256']!=digest(after):raise ValueError('VERDICT_BINDING_MISMATCH')
    id='inst_'+candidate_id
    with lock(store):
        i=store.get('installations',id)
        if i:return _recover(store,i)
        p=Path(g['target'])
        if p.is_symlink() or digest(p.read_bytes())!=c['parent_sha256']:raise ValueError('DRIFT_HOLD')
        before=store.artifact(p.read_bytes())
        i={"id":id,"candidate_id":candidate_id,"target":str(p),"before_sha256":before,"after_sha256":digest(after),"authority_id":g['id'],"status":"prepared","created_at":now(),"activated":False,"live_verified":False}
        store.put('installations',i)
        return _recover(store,i)


def _recover(store,i):
    p=Path(i['target'])
    if p.is_symlink():raise ValueError('DRIFT_HOLD')
    h=digest(p.read_bytes())
    rollback=i['status']=='rollback_prepared'
    if i['status'] not in {'prepared','rollback_prepared'}:return i
    expected=i['after_sha256'] if rollback else i['before_sha256']
    desired=i['before_sha256'] if rollback else i['after_sha256']
    if h==expected:atomic_write(p,store.read_artifact(desired))
    elif h!=desired:
        i.update(status='drift_hold',reason_code='DRIFT_HOLD');store.put('installations',i);return i
    if digest(p.read_bytes())!=desired:raise ValueError('READBACK_FAILED')
    i.update(status='rolled_back' if rollback else 'activation_pending',readback_sha256=desired,updated_at=now())
    store.put('installations',i);return i


def rollback(store,id):
    with lock(store):
        i=store.get('installations',id)
        if not i:raise ValueError('INSTALLATION_NOT_FOUND')
        if i['status']=='rolled_back':return i
        if i.get('owner')=='skill-evolution-loop':
            from .owner_installers import SkillEvolutionInstaller
            return SkillEvolutionInstaller().rollback(store,i)
        if digest(Path(i['target']).read_bytes())!=i['after_sha256']:raise ValueError('DRIFT_HOLD')
        i.update(status='rollback_prepared');store.put('installations',i)
        return _recover(store,i)


def recover(store):
    with lock(store):
        recovered=[]
        for i in store.list('installations'):
            if i.get('owner')=='skill-evolution-loop' and i['status']=='owner_prepared':
                from .owner_installers import SkillEvolutionInstaller
                recovered.append(SkillEvolutionInstaller().apply(store,i['candidate_id']))
            elif i.get('owner')=='skill-evolution-loop' and i['status']=='owner_rollback_prepared':
                from .owner_installers import SkillEvolutionInstaller
                recovered.append(SkillEvolutionInstaller().rollback(store,i))
            elif i['status'] in {'prepared','rollback_prepared'}:recovered.append(_recover(store,i))
        return recovered


def activate(store,id,run_id):
    i=store.get('installations',id);r=store.get('runs',run_id)
    if not i or not r:raise ValueError('EVIDENCE_MISSING')
    if i['status']!='activation_pending' or r['origin']!='activation_canary':raise ValueError('ACTIVATION_STATE_HOLD')
    if not any(a['attribution'] in {'explicit_loaded','verified_read','executed_script'} and a.get('file_sha256')==i['after_sha256'] for a in r['attributions']):raise ValueError('FRESH_LOAD_EVIDENCE_REQUIRED')
    if r.get('outcome')!='accepted' or not r.get('fresh_context') or not r.get('outcome_receipt_id'):raise ValueError('TASK_VERIFICATION_REQUIRED')
    from .outcomes import validate_task_receipt
    receipt=validate_task_receipt(store,store.get('task_receipts',r['outcome_receipt_id']) or {})
    if receipt['installation_id']!=id:raise ValueError('TASK_INSTALLATION_MISMATCH')
    if digest(Path(i['target']).read_bytes())!=i['after_sha256']:raise ValueError('DRIFT_HOLD')
    i.update(status='activated',activated=True,activation_run_id=run_id,updated_at=now());store.put('installations',i);return i
