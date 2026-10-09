"""Canonical capabilities, immutable versions and evidence-stage invocation ledger."""
from __future__ import annotations
import json
from pathlib import Path
import re
from .store import canonical,digest,now

STAGES=('mentioned','selected','verified_read','declared_applied','executed','accepted')


def _scope(store,scope):
    p=Path(scope).resolve()
    if not any(p==Path(s).resolve() or Path(s).resolve() in p.parents for s in store.settings()['scopes']):raise ValueError('OUTSIDE_SCOPE')
    return str(p)


def _text(value,name,required=False):
    if value is None and not required:return None
    if not isinstance(value,str) or not value.strip() or len(value)>4000:raise ValueError('INVALID_'+name.upper())
    from .runtime import redact
    if redact(value)!=value:raise ValueError('SENSITIVE_METADATA_REJECTED')
    return value


def _manifest(path,kind):
    if kind=='skill':
        from .runtime import package_manifest
        return package_manifest(path)
    from .capture import _manifest as script_manifest
    return script_manifest(path,kind)


def register_capability(store,path,owner,kind='skill',purpose=None,background=None,origin=None,capability_id=None,scope=None):
    if kind not in {'skill','script'}:raise ValueError('CAPABILITY_KIND_INVALID')
    owner=_text(owner,'owner',True);p=Path(path).resolve()
    if not p.is_dir():raise ValueError('PACKAGE_NOT_FOUND')
    if scope is None:raise ValueError('CLASSIFIED_SCOPE_REQUIRED')
    scope=_scope(store,scope);m=_manifest(p,kind)
    capid=capability_id or 'cap_'+digest(str(p).encode())[:24]
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',capid):raise ValueError('CAPABILITY_ID_INVALID')
    if origin:
        for field in ('session_id','turn_id','project','scenario','evidence_sha256'):
            _text(origin.get(field),field,True)
        _scope(store,origin['project']);store.read_artifact(origin['evidence_sha256'])
    description=None
    if kind=='skill':
        match=re.search(r'^description:\s*(.+)$',(p/'SKILL.md').read_text(),re.M)
        if match:description=match.group(1).strip('"\'')[:4000]
    else:
        cmd=json.loads((p/'command.json').read_text());description=cmd.get('description') or cmd.get('result')
    purpose=_text(purpose,'purpose');background=_text(background,'background')
    files={name:store.artifact((p/name).read_bytes()) for name in m['files']}
    snapshot=store.artifact(canonical({'files':files,'package_sha256':m['package_sha256']}))
    vid='ver_'+digest(canonical([capid,m['package_sha256']]))[:32];t=now()
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE');old=store.get('capability_catalog',capid,db)
        if old and (old['owner']!=owner or old['kind']!=kind):raise ValueError('CANONICAL_OWNER_CONFLICT')
        existing=store.get('capability_versions',vid,db)
        if existing and (existing['manifest']!=m or existing['snapshot_sha256']!=snapshot):raise ValueError('IMMUTABLE_VERSION_CONFLICT')
        if not existing:store.put('capability_versions',{'id':vid,'capability_id':capid,'package_sha256':m['package_sha256'],'manifest':m,'snapshot_sha256':snapshot,'origin':origin,'created_at':t},db)
        if old:
            value={**old,'path':str(p),'version_id':vid,'package_sha256':m['package_sha256'],'scope':scope,'description':description}
            if str(p) not in value['locations']:value['locations']=[*value['locations'],str(p)]
            # A new version is observable, never silently inherits activation admission.
            if old['version_id']!=vid:value.update(status='registered',updated_at=t)
            if purpose and not value.get('purpose'):value['purpose']=purpose
            if background and not value.get('background'):value['background']=background
            # Historical origin is immutable. Later use/source never becomes a new birth.
        else:
            value={'id':capid,'name':p.name,'kind':kind,'path':str(p),'locations':[str(p)],'owner':owner,'source':'user-owned',
                   'description':description,'purpose':purpose,'background':background,'origin':origin,'scope':scope,'status':'registered',
                   'created_at':t,'registered_at':t,'first_seen_at':t,'born_at':None,'version_id':vid,'package_sha256':m['package_sha256'],
                   'missing':[] if origin else ['CREATION_ORIGIN_UNKNOWN'],'usage_counts':{k:0 for k in STAGES}}
        store.put('capability_catalog',value,db)
    return value


def record_usage(store,receipt):
    r=dict(receipt)
    for field in ('capability_id','version_id','cwd','session_id','turn_id','invocation_id','stage','source','event_id'):_text(r.get(field),field,True)
    if r['stage'] not in STAGES:raise ValueError('INVALID_USAGE_STAGE')
    _scope(store,r['cwd'])
    cap=store.get('capability_catalog',r['capability_id']);v=store.get('capability_versions',r['version_id'])
    if not cap or not v or v['capability_id']!=cap['id']:raise ValueError('VERSION_CAPABILITY_MISMATCH')
    cwd=Path(r['cwd']).resolve();scope=Path(cap['scope']).resolve()
    if cwd!=scope and scope not in cwd.parents:raise ValueError('OUTSIDE_CAPABILITY_SCOPE')
    if r.get('evidence_sha256'):store.read_artifact(r['evidence_sha256'])
    if r['stage'] in {'verified_read','executed','accepted'} and not r.get('evidence_sha256'):raise ValueError('STAGE_EVIDENCE_REQUIRED')
    from .runtime import redact
    if redact(r)!=r:raise ValueError('SENSITIVE_USAGE_REJECTED')
    identity=[r['capability_id'],r['version_id'],r['session_id'],r['turn_id'],r.get('agent_id'),r['invocation_id']]
    iid='use_'+digest(canonical(identity))[:32]
    # Channel observations are unique receipts, while identity is channel independent.
    eid='observation_'+digest(canonical([r['source'],r['event_id']]))[:32]
    observed={**r,'id':eid,'invocation_record_id':iid}
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE');prior=store.get('capability_observations',eid,db)
        if prior:
            if prior!=observed:raise ValueError('USAGE_EVENT_ID_CONFLICT')
            return store.get('capability_invocations',iid,db)
        u=store.get('capability_invocations',iid,db) or {'id':iid,'capability_id':cap['id'],'version_id':v['id'],'session_id':r['session_id'],'turn_id':r['turn_id'],
            'agent_id':r.get('agent_id'),'cwd':str(cwd),'scenario':r.get('scenario'),'origin':r.get('origin','user_run'),'created_at':now(),
            'stages':[],'sources':[],'attempts':[],'evidence_ids':[],'observation_ids':[],'status':'observed','missing':[]}
        if u['cwd']!=str(cwd):raise ValueError('INVOCATION_CONTEXT_CONFLICT')
        for key,value in (('stages',r['stage']),('sources',r['source']),('attempts',r.get('attempt_id')),('evidence_ids',r.get('evidence_sha256')),('observation_ids',eid)):
            if value and value not in u[key]:u[key].append(value)
        if r.get('scenario'):
            if u.get('scenario') and u['scenario']!=r['scenario']:raise ValueError('INVOCATION_SCENARIO_CONFLICT')
            u['scenario']=r['scenario']
        if r.get('status'):u['status']=r['status']
        u['updated_at']=now()
        store.put('capability_observations',observed,db);store.put('capability_invocations',u,db)
    return u


def project_lifecycle(store):
    catalog=store.list('capability_catalog');invocations=store.list('capability_invocations')
    for cap in catalog:
        uses=[u for u in invocations if u['capability_id']==cap['id']]
        cap['usage_counts']={k:sum(k in u['stages'] for u in uses) for k in STAGES}
        cap['invocation_count']=len(uses)
        cap['canary_invocation_count']=sum(u.get('origin')=='activation_canary' for u in uses)
        cap['projects']=sorted({u['cwd'] for u in uses})
        cap['session_count']=len({u['session_id'] for u in uses})
        cap['usage_scope']='observed_receipts_only'
    return {'capability_catalog':catalog,'capability_versions':store.list('capability_versions'),'capability_invocations':invocations}


def discover(store,query,cwd):
    try:_scope(store,cwd)
    except ValueError:return []
    p=Path(cwd).resolve();words=[x for x in re.split(r'[\s,;/]+',query.casefold()) if x]
    candidates=[]
    for cap in project_lifecycle(store)['capability_catalog']:
        scope=Path(cap['scope']).resolve()
        if (p!=scope and scope not in p.parents) or cap['status'] in {'retired','quarantined','hold'}:continue
        content=' '.join(str(cap.get(k) or '') for k in ('name','description','purpose')).casefold()
        score=sum(w in content for w in words)
        if not words or score:candidates.append((score,cap['name'],cap))
    candidates.sort(key=lambda x:(-x[0],x[1]))
    return [cap for _,_,cap in candidates[:10]]
