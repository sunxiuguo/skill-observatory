"""Content addressed package identity shared by task execution and owner mapping.

No installer lives here. Legacy files-only identities remain readable unchanged.
"""
from pathlib import Path, PurePosixPath
import stat
from .store import canonical,digest


def validate_names(names):
    folded=set()
    for name in names:
        if not isinstance(name,str):raise ValueError('PACKAGE_PATH_REJECTED')
        p=PurePosixPath(name)
        if not isinstance(name,str) or not name or '\\' in name or p.is_absolute() or '..' in p.parts or str(p)!=name or ':' in name:
            raise ValueError('PACKAGE_PATH_REJECTED')
        if name.casefold() in folded:raise ValueError('PACKAGE_PATH_COLLISION')
        folded.add(name.casefold())


def execution_manifest(files, modes=None):
    """Pure complete input identity; shared by loaders and the final verifier."""
    validate_names(files)
    if not files or len(files)>512:raise ValueError('PACKAGE_FILE_COUNT_INVALID')
    modes=modes or {}
    if set(modes)-set(files):raise ValueError('PACKAGE_MODE_OUTSIDE_MANIFEST')
    entries=[];total=0
    for name,data in sorted(files.items()):
        mode=modes.get(name,0o644)
        if type(mode) is not int or mode not in {0o600,0o644,0o700,0o755} or (mode in {0o700,0o755} and not name.endswith(('.py','.sh'))):raise ValueError('PACKAGE_MODE_REJECTED')
        if not isinstance(data,bytes) or len(data)>8_000_000:raise ValueError('PACKAGE_FILE_TOO_LARGE')
        total+=len(data)
        if total>32*1024*1024:raise ValueError('PACKAGE_TOTAL_TOO_LARGE')
        entries.append({'path':name,'type':'file','sha256':digest(data),'size':len(data),'mode':mode})
    value={'schema_version':2,'entries':entries}
    return {**value,'package_digest':digest(canonical(value))}


def validate_execution_manifest(files,manifest):
    try:
        modes={e['path']:e['mode'] for e in manifest['entries']}
        if execution_manifest(files,modes)!=manifest:raise ValueError('EXECUTION_MANIFEST_DRIFT')
    except (KeyError,TypeError):raise ValueError('EXECUTION_MANIFEST_REQUIRED')
    return manifest


def freeze_package(store,files,modes=None):
    manifest=execution_manifest(files,modes)
    for data in files.values():store.artifact(data)
    store.artifact(canonical({k:v for k,v in manifest.items() if k!='package_digest'}))
    return manifest


def trial_manifest(protocol,arm,files,inputs):
    """An explicit package contract can never fall back to bytes-only loading."""
    manifest=(protocol.get('arm_packages') or {}).get(arm)
    if not manifest:raise ValueError('EXECUTION_MANIFEST_REQUIRED')
    validate_execution_manifest(files,manifest)
    package_digest=protocol.get(arm+'_package_digest')
    if package_digest and package_digest!=manifest['package_digest']:
        # Package protocols may add a separately frozen harness, but its
        # entries must not be confused with the installable package identity.
        harness=protocol.get('harness_files') or {}
        package_files={n:v for n,v in files.items() if n not in harness}
        modes={e['path']:e['mode'] for e in manifest['entries'] if e['path'] in package_files}
        if execution_manifest(package_files,modes)['package_digest']!=package_digest:
            raise ValueError('EXECUTION_PACKAGE_BINDING_DRIFT')
    if set(files)&set(inputs):raise ValueError('CASE_OVERWRITES_SKILL')
    return execution_manifest({**files,**inputs},{e['path']:e['mode'] for e in manifest['entries']})


def read_package(store, manifest):
    descriptor={k:v for k,v in manifest.items() if k!='package_digest'}
    if manifest.get('schema_version')!=2 or store.read_artifact(manifest['package_digest'])!=canonical(descriptor):raise ValueError('PACKAGE_MANIFEST_DRIFT')
    entries=manifest['entries']
    if len(entries)>512 or any(type(e.get('size')) is not int or e['size']<0 for e in entries) or sum(e['size'] for e in entries)>32*1024*1024:raise ValueError('PACKAGE_TOTAL_TOO_LARGE')
    names=[x['path'] for x in entries];validate_names(names)
    if names!=sorted(names) or len(entries)!=len(set(names)):raise ValueError('PACKAGE_MANIFEST_ORDER_OR_DUPLICATE')
    files={}
    for item in entries:
        if set(item)!={'path','type','sha256','size','mode'} or item['type']!='file':raise ValueError('PACKAGE_TYPE_REJECTED')
        data=store.read_artifact(item['sha256'])
        if len(data)!=item['size']:raise ValueError('PACKAGE_SIZE_DRIFT')
        files[item['path']]=data
    if freeze_package(store,files,{e['path']:e['mode'] for e in entries})!=manifest:raise ValueError('PACKAGE_MANIFEST_DRIFT')
    return files


def snapshot_package(store, root):
    root=Path(root)
    if root.is_symlink() or any(p.is_symlink() for p in root.parents) or not root.is_dir():raise ValueError('PACKAGE_ROOT_REJECTED')
    if stat.S_IMODE(root.stat().st_mode)&0o7000:raise ValueError('PACKAGE_DIRECTORY_MODE_REJECTED')
    files={};modes={}
    for p in sorted(root.rglob('*')):
        if any(x in {'.git','__pycache__','.venv','node_modules'} for x in p.relative_to(root).parts):continue
        if p.is_symlink():raise ValueError('PACKAGE_SYMLINK_REJECTED')
        mode=stat.S_IMODE(p.stat().st_mode)
        if p.is_dir():
            if mode&0o7000:raise ValueError('PACKAGE_DIRECTORY_MODE_REJECTED')
            continue
        if not stat.S_ISREG(p.stat().st_mode):raise ValueError('PACKAGE_TYPE_REJECTED')
        if p.is_file():
            if p.stat().st_size>8_000_000:raise ValueError('PACKAGE_FILE_TOO_LARGE')
            if sum(len(b) for b in files.values())+p.stat().st_size>32*1024*1024:raise ValueError('PACKAGE_TOTAL_TOO_LARGE')
            name=p.relative_to(root).as_posix();files[name]=p.read_bytes();modes[name]=mode
    return freeze_package(store,files,modes)


def changed_files(store, parent, candidate, authorized=None):
    a=read_package(store,parent);b=read_package(store,candidate)
    before={e['path']:e for e in parent['entries']};after={e['path']:e for e in candidate['entries']}
    changed=sorted(n for n in set(a)|set(b) if before.get(n)!=after.get(n))
    if authorized is not None:
        validate_names(authorized)
        if len(authorized)!=len(set(authorized)) or set(changed)!=set(authorized):raise ValueError('PACKAGE_AUTHORIZED_FILES_MISMATCH')
    return changed
