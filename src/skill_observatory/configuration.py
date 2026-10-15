"""Explicit local owner plugin. Never configurable over HTTP."""
import json
import types
import sys
from pathlib import Path
from .store import now

def _owner(store,name):
    path=store.root/(name+'.json')
    if not path.exists():return None
    if path.is_symlink() or path.stat().st_mode & 0o077:raise ValueError('REVIEWER_CONFIG_NOT_PRIVATE')
    config=json.loads(path.read_text());owner=Path(config['owner_module']).resolve()
    from .store import digest
    source=owner.read_bytes()
    if digest(source)!=config['owner_sha256']:raise ValueError('REVIEWER_OWNER_DRIFT')
    # Execute exactly the checked bytes, not a second filesystem read which
    # could load changed source between validation and import.
    module_name='skillobs_local_'+name+'_'+config['owner_sha256']
    module=types.ModuleType(module_name);module.__file__=str(owner)
    sys.modules[module_name]=module
    exec(compile(source,str(owner),'exec'),module.__dict__)
    return module,config


def load_reviewer(store,isolated=True):
    result=_owner(store,'reviewer')
    if result is None:return None
    module,config=result
    reviewer=module.make_reviewer()
    certification=getattr(reviewer,'transport_certification',{})
    status='owner_verified_tool_free_transport' if certification.get('verified') is True and isinstance(certification.get('proof_sha256'),str) and len(certification['proof_sha256'])==64 else 'configured_not_certified'
    semantic=getattr(reviewer,'semantic_certification',{})
    if status=='owner_verified_tool_free_transport' and semantic.get('verified') is True and isinstance(semantic.get('proof_sha256'),str) and len(semantic['proof_sha256'])==64:
        status='owner_verified_schema_review'
    # A transport proof cannot override a trusted owner's explicit execution HOLD.
    hold=getattr(reviewer,'execution_hold',None)
    if hold:
        import re
        if not isinstance(hold,str) or not re.fullmatch(r'[A-Z0-9_]{1,160}',hold):raise ValueError('REVIEWER_EXECUTION_HOLD_INVALID')
        status='semantic_integration_hold'
    store.put('runtime',{'id':'reviewer','status':status,'transport_certification':certification,'semantic_certification':semantic,'owner_sha256':config['owner_sha256'],'created_at':now(),
        'execution_hold':hold,
        'execution_mode':'background_tool_free','required_admission_contract':'background_tool_free',
        'capsule_schema_version':1,'isolation':'process_group_deadline'})
    if hold:
        from .reviewer import ReviewDeferred
        import time
        class HeldReviewer:
            def review(self,store,run):raise ReviewDeferred(hold,time.time()+3600)
        return HeldReviewer()
    if isolated:
        from .review_worker import IsolatedReviewer
        seconds=getattr(reviewer,'max_seconds',120)
        if not isinstance(seconds,(int,float)) or not 0<seconds<=300:raise ValueError('REVIEWER_DEADLINE_INVALID')
        return IsolatedReviewer(seconds)
    return reviewer


def load_pipeline(store):
    from .pipeline import EvolutionPipeline
    result=_owner(store,'evolution')
    if result is None:
        store.put('runtime',{'id':'evolution','status':'awaiting_owner_adapters',
            'missing':['PROPOSER_ADAPTER_REQUIRED','INDEPENDENT_DOMAIN_EVALUATOR_REQUIRED','ACTIVATION_OWNER_REQUIRED'],
            'created_at':now(),'automatic_promotion':False})
        return EvolutionPipeline(store)
    module,config=result
    pipeline=module.make_pipeline(store)
    if not isinstance(pipeline,EvolutionPipeline) or pipeline.store is not store:
        raise ValueError('EVOLUTION_OWNER_INTERFACE_INVALID')
    store.put('runtime',{'id':'evolution','status':'configured_not_certified',
                        'adapter_mode':getattr(pipeline,'adapter_mode','custom_owner'),
                        'required_inputs':getattr(pipeline,'required_inputs',[]),
                        'owner_sha256':config['owner_sha256'],'created_at':now()})
    return pipeline
