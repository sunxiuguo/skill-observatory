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


def load_reviewer(store):
    result=_owner(store,'reviewer')
    if result is None:return None
    module,config=result
    reviewer=module.make_reviewer()
    store.put('runtime',{'id':'reviewer','status':'configured_not_certified','owner_sha256':config['owner_sha256'],'created_at':now()})
    return reviewer


def load_pipeline(store):
    from .pipeline import EvolutionPipeline
    result=_owner(store,'evolution')
    if result is None:return EvolutionPipeline(store)
    module,config=result
    pipeline=module.make_pipeline(store)
    if not isinstance(pipeline,EvolutionPipeline) or pipeline.store is not store:
        raise ValueError('EVOLUTION_OWNER_INTERFACE_INVALID')
    store.put('runtime',{'id':'evolution','status':'configured_not_certified',
                        'owner_sha256':config['owner_sha256'],'created_at':now()})
    return pipeline
