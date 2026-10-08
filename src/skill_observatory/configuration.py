"""Explicit local owner plugin. Never configurable over HTTP."""
import importlib.util
import json
from pathlib import Path
from .store import now

def load_reviewer(store):
    path=store.root/'reviewer.json'
    if not path.exists():return None
    if path.is_symlink() or path.stat().st_mode & 0o077:raise ValueError('REVIEWER_CONFIG_NOT_PRIVATE')
    config=json.loads(path.read_text());owner=Path(config['owner_module']).resolve()
    from .store import digest
    if digest(owner.read_bytes())!=config['owner_sha256']:raise ValueError('REVIEWER_OWNER_DRIFT')
    spec=importlib.util.spec_from_file_location('skillobs_local_owner',owner)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    reviewer=module.make_reviewer()
    store.put('runtime',{'id':'reviewer','status':'configured_not_certified','owner_sha256':config['owner_sha256'],'created_at':now()})
    return reviewer
