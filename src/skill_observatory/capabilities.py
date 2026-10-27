"""Canonical capabilities, immutable versions and evidence-stage invocation ledger."""
from __future__ import annotations
import json
from pathlib import Path
import re
from .store import canonical,digest,now

STAGES=('mentioned','selected','verified_read','declared_applied','executed','accepted')


def capability_projection(store,cap,db):
    """Full-ledger counters and explicit authority facts; registration grants nothing."""
    cap=dict(cap)
    uses=[json.loads(r[0]) for r in db.execute("SELECT data FROM entities WHERE kind='capability_invocations' AND json_extract(data,'$.capability_id')=?",(cap['id'],))]
    cap.update(usage_counts={k:sum(k in u['stages'] for u in uses) for k in STAGES},invocation_count=len(uses),
        canary_invocation_count=sum(u.get('origin')=='activation_canary' for u in uses),
        projects=sorted({u['cwd'] for u in uses}),session_count=len({u['session_id'] for u in uses}),usage_scope='observed_receipts_only')
    from .installations import authority_expired
    authorized=False
    for row in db.execute("SELECT data FROM entities WHERE kind='authority_grants'"):
        grant=json.loads(row[0])
        if grant.get('status')=='authorized' and grant.get('target')==str(Path(cap['path'])/'SKILL.md') and grant.get('owner')=='skill-evolution-loop' and grant.get('package_sha256')==cap['package_sha256'] and not authority_expired(grant.get('expires_at')):
            authorized=True
    cap['evaluation_projection']={'version_id':cap['version_id'],'owner_authorized':authorized,
        'status':'owner_authorized_missing_independent_truth' if authorized else 'registration_only',
        'eligible':False,'missing':['INDEPENDENT_DOMAIN_TRUTH_REQUIRED','ALL_ATTEMPT_COST_REQUIRED']+([] if authorized else ['OWNER_AUTHORITY_REQUIRED'])}
    return cap


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


def _project_skill(store, cap, version, db):
    """Legacy evaluator view of the canonical frozen version; grants nothing."""
    manifest = version['manifest']
    if version['capability_id'] != cap['id'] or manifest['package_sha256'] != version['package_sha256'] \
            or digest(canonical(manifest['files'])) != version['package_sha256']:
        raise ValueError('FROZEN_SKILL_VERSION_INVALID')
    snapshot = json.loads(store.read_artifact(version['snapshot_sha256']))
    if snapshot.get('files') != manifest['files'] or snapshot.get('package_sha256') != version['package_sha256']:
        raise ValueError('FROZEN_SKILL_VERSION_INVALID')
    sid = 'sk_' + digest(str(Path(cap['path']).resolve()).encode())[:24]
    old = store.get('skills', sid, db) or {}
    binding=store.get('legacy_projection_migrations',old.get('projection_owner_binding_id',''),db) or {}
    delegated=(binding.get('skill_id')==sid and binding.get('capability_id')==cap['id']
               and binding.get('canonical_owner')==cap['owner']
               and binding.get('installation_owner')==old.get('owner'))
    if old and old['owner'] != cap['owner']:
        if not delegated:raise ValueError('CANONICAL_OWNER_CONFLICT')
    if old.get('capability_id') not in {None,cap['id']}:
        raise ValueError('CANONICAL_OWNER_CONFLICT')
    value = {**old, 'id': sid, 'name': cap['name'], 'path': cap['path'],
        'owner':old['owner'] if delegated else cap['owner'],'capability_owner':cap['owner'],
        'source': cap['source'], 'license': old.get('license'), 'status': old.get('status', 'observing'),
        'capability_id': cap['id'], 'version_id': version['id'], 'package_sha256': version['package_sha256'],
        'manifest': manifest, 'created_at': old.get('created_at', cap['created_at']),
        'updated_at': version['created_at'], 'auto_promote': False, 'score': old.get('score'),
        'missing': old.get('missing', ['independent_final_evidence'])}
    return store.put('skills', value, db)


def verified_run_invocations(store, run, db):
    """One identity predicate for factual selection and Skill attribution."""
    execution = run.get('execution_session_id', run.get('session_id'))
    if not run.get('cwd') or not run.get('turn_id'):
        return []  # Unknown legacy context cannot establish an observed version.
    rows = db.execute("SELECT data FROM entities WHERE kind='capability_invocations' "
        "AND json_extract(data,'$.session_id')=? AND json_extract(data,'$.turn_id')=?",
        (execution, run.get('turn_id'))).fetchall()
    result = []
    for raw in rows:
        invocation = json.loads(raw[0])
        if invocation.get('agent_id') != run.get('agent_id') or 'verified_read' not in invocation['stages'] \
                or not invocation.get('evidence_ids'):
            continue
        if str(Path(invocation['cwd']).resolve()) != str(Path(run['cwd']).resolve()):
            continue
        result.append(invocation)
    return result


def bind_run_attributions(store, run, db, version_id=None):
    """Bind exact verified reads; caller owns the transaction and no-replay gate."""
    attributions = list(run.get('attributions', []))
    for invocation in verified_run_invocations(store, run, db):
        if version_id and invocation['version_id'] != version_id:
            continue
        _scope(store, invocation['cwd'])
        version = store.get('capability_versions', invocation['version_id'], db)
        cap = store.get('capability_catalog', invocation['capability_id'], db)
        if not version or not cap or cap['kind'] != 'skill' or version['capability_id'] != cap['id']:
            continue
        current = store.get('capability_versions', cap['version_id'], db)
        skill = _project_skill(store, cap, current, db)
        attribution = {'skill_id': skill['id'], 'package_sha256': version['package_sha256'],
            'file_sha256': version['manifest']['files']['SKILL.md'], 'attribution': 'verified_read',
            'capability_id': cap['id'], 'version_id': version['id'],
            'loaded_version_source': 'capability_invocation_verified_read'}
        if not any(all(a.get(k) == attribution[k] for k in ('skill_id', 'package_sha256', 'attribution')) for a in attributions):
            attributions.append(attribution)
    if attributions != run.get('attributions', []):
        run = {**run, 'attributions': attributions}
        store.put('runs', run, db)
    return run


def register_capability(store,path,owner,kind='skill',purpose=None,background=None,origin=None,capability_id=None,scope=None,*,_reconcile=None):
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
    files={}
    for name,expected in m['files'].items():
        data=(p/name).read_bytes()
        if digest(data)!=expected:raise ValueError('CAPABILITY_CHANGED_DURING_READ')
        files[name]=store.artifact(data)
    if _reconcile and m['package_sha256']!=_reconcile['package_sha256']:
        raise ValueError('CAPABILITY_READBACK_DRIFT')
    snapshot=store.artifact(canonical({'files':files,'package_sha256':m['package_sha256']}))
    vid='ver_'+digest(canonical([capid,m['package_sha256']]))[:32];t=now()
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE');old=store.get('capability_catalog',capid,db)
        if old and (old['owner']!=owner or old['kind']!=kind):raise ValueError('CANONICAL_OWNER_CONFLICT')
        if _reconcile:
            if not old or old['path']!=str(p) or old['scope']!=scope or old['status'] in {'retired','quarantined','hold'}:
                raise ValueError('CAPABILITY_RECONCILIATION_SCOPE_HOLD')
            prior=store.get('capability_reconciliations',_reconcile['id'],db)
            if prior:
                if prior['spec_sha256']!=_reconcile['spec_sha256'] or old['version_id']!=prior['after_version_id']:
                    raise ValueError('CAPABILITY_RECONCILIATION_CAS_MISMATCH')
                return old
            if old['version_id']!=_reconcile['expected_version_id']:
                raise ValueError('CAPABILITY_RECONCILIATION_CAS_MISMATCH')
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
        # Legacy evaluator identity is a projection of the immutable version,
        # never a second mutable package fact or a new authority grant.
        if kind=='skill':
            if _reconcile and _reconcile.get('legacy_projection_sha256'):
                sid='sk_'+digest(str(p).encode())[:24]
                legacy=store.get('skills',sid,db)
                if (not legacy or digest(canonical(legacy))!=_reconcile['legacy_projection_sha256']
                        or legacy.get('capability_id') or legacy.get('version_id')
                        or legacy.get('path')!=str(p)):
                    raise ValueError('LEGACY_PROJECTION_CAS_MISMATCH')
                protected=db.execute("SELECT data FROM entities WHERE kind IN ('authority_grants','installations','candidates') "
                    "AND (json_extract(data,'$.target') IN (?,?) OR json_extract(data,'$.target_root')=?)",
                    (str(p),str(p/'SKILL.md'),str(p))).fetchall()
                if any(json.loads(row[0]).get('owner')!=legacy['owner'] for row in protected):
                    raise ValueError('LEGACY_PROJECTION_AUTHORITY_HOLD')
                store.put('legacy_projection_migrations',{
                    'id':_reconcile['id'],'skill_id':sid,'capability_id':capid,
                    'before_sha256':store.artifact(canonical(legacy)),
                    'previous_owner':legacy['owner'],'canonical_owner':owner,'installation_owner':legacy['owner'],
                    'evidence_sha256':_reconcile['evidence_sha256'],'created_at':t,
                    'claim':'unbound_projection_binding_only_no_authority_change'},db)
                store.put('skills',{**legacy,'projection_owner_binding_id':_reconcile['id']},db)
            _project_skill(store, value, store.get('capability_versions', vid, db), db)
        if _reconcile:
            store.put('capability_reconciliations',{
                'id':_reconcile['id'],'capability_id':capid,'owner':owner,
                'before_version_id':old['version_id'],'after_version_id':vid,
                'package_sha256':m['package_sha256'],'evidence_sha256':_reconcile['evidence_sha256'],
                'spec_sha256':_reconcile['spec_sha256'],'created_at':t,
                'claim':'catalog_readback_only_not_activation_or_gain'},db)
    return value


def reconcile_capability(store,value):
    """Explicit trusted-root readback; discovery never accepts changed bytes."""
    fields={'schema_version','capability_id','owner','expected_version_id','package_sha256','evidence_sha256'}
    if not isinstance(value,dict) or set(value)-{'legacy_projection_sha256'}!=fields or type(value['schema_version']) is not int or value['schema_version']!=1:
        raise ValueError('CAPABILITY_RECONCILIATION_INVALID')
    for key in ('capability_id','expected_version_id'):
        if not isinstance(value[key],str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',value[key]):
            raise ValueError('CAPABILITY_RECONCILIATION_INVALID')
    for key in ('package_sha256','evidence_sha256',*(['legacy_projection_sha256'] if 'legacy_projection_sha256' in value else [])):
        if not isinstance(value[key],str) or not re.fullmatch(r'[0-9a-f]{64}',value[key]):
            raise ValueError('CAPABILITY_RECONCILIATION_INVALID')
    cap=store.get('capability_catalog',value['capability_id'])
    if not cap or cap['owner']!=value['owner']:raise ValueError('CANONICAL_OWNER_CONFLICT')
    if not store.read_artifact(value['evidence_sha256']).strip():raise ValueError('CAPABILITY_RECONCILIATION_EVIDENCE_REQUIRED')
    h=digest(canonical(value));spec={**value,'id':'cr_'+h[:32],'spec_sha256':h}
    register_capability(store,cap['path'],cap['owner'],kind=cap['kind'],scope=cap['scope'],capability_id=cap['id'],_reconcile=spec)
    return store.get('capability_reconciliations',spec['id'])


def drift_actions(store,limit=8):
    """Bounded diagnostic pointers; no catalog update, model or installation."""
    if type(limit) is not int or not 1<=limit<=50:raise ValueError('CAPABILITY_DRIFT_LIMIT_INVALID')
    actions=[]
    for cap in store.list('capability_catalog'):
        if cap['status'] in {'retired','quarantined','hold'}:continue
        try:_scope(store,cap['scope'])
        except ValueError:continue
        try:
            current=_manifest(Path(cap['path']),cap['kind'])
            if current['package_sha256']==cap['package_sha256']:continue
            action={'capability_id':cap['id'],'owner':cap['owner'],'expected_version_id':cap['version_id'],
                    'package_sha256':current['package_sha256'],'reason_code':'CAPABILITY_VERSION_DRIFT'}
        except (OSError,ValueError):
            action={'capability_id':cap['id'],'owner':cap['owner'],'expected_version_id':cap['version_id'],
                    'reason_code':'CAPABILITY_READBACK_REQUIRED'}
        actions.append(action)
        if len(actions)>=limit:break
    return actions


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
        if 'verified_read' in u['stages']:
            runs = db.execute("SELECT data FROM entities WHERE kind='runs' AND "
                "COALESCE(json_extract(data,'$.execution_session_id'),json_extract(data,'$.session_id'))=? "
                "AND json_extract(data,'$.turn_id')=? LIMIT 2", (u['session_id'], u['turn_id'])).fetchall()
            if len(runs) == 1:
                bind_run_attributions(store, json.loads(runs[0][0]), db)
    return u


def project_lifecycle(store):
    catalog=store.list('capability_catalog');invocations=store.list('capability_invocations')
    from collections import defaultdict
    grouped=defaultdict(list)
    for u in invocations:grouped[u['capability_id']].append(u)
    for cap in catalog:
        uses=grouped[cap['id']]
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
    p=Path(cwd).resolve();words=_tokens(query)
    candidates=[]
    for cap in store.list('capability_catalog'):
        scope=Path(cap['scope']).resolve()
        if (p!=scope and scope not in p.parents) or cap['status'] in {'retired','quarantined','hold'}:continue
        content=' '.join(str(cap.get(k) or '') for k in ('name','description','purpose','aliases')).casefold()
        score=sum(len(w) for w in words if w in content)
        if not words or score:
            with store.connect() as db:cap=capability_projection(store,cap,db)
            try:
                current=_manifest(Path(cap['path']),cap['kind'])
                if current['package_sha256']!=cap['package_sha256']:
                    cap={**cap,'freshness':'drift','eligible_for_reuse':False,'reason_code':'CAPABILITY_VERSION_DRIFT'}
                else:cap={**cap,'freshness':'verified_current','eligible_for_reuse':True}
            except (OSError,ValueError):cap={**cap,'freshness':'unavailable','eligible_for_reuse':False,'reason_code':'CAPABILITY_READBACK_REQUIRED'}
            candidates.append((score,len(scope.parts),cap['name'],cap))
    candidates.sort(key=lambda x:(-x[0],-x[1],x[2]))
    return [cap for *_,cap in candidates[:10]]


def _tokens(text):
    """Deterministic Latin tokens and Chinese bigrams; no semantic gain claim."""
    words=re.findall(r'[a-z0-9_-]+|[\u4e00-\u9fff]+',text.casefold())
    return set(part for w in words for part in ([w[i:i+2] for i in range(len(w)-1)] if re.fullmatch(r'[\u4e00-\u9fff]{3,}',w) else [w]))
