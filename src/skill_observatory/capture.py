"""Evidence-bound workflow capture and local replay; no model or scheduler.

Creator agents supply a structured receipt after a real stage succeeds. The owner
retains authorship. Subprocess validation is functional, not a security sandbox.
"""
from __future__ import annotations
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid
from .store import canonical, digest, now, atomic_write
from .runtime import redact


def scoped(store, cwd):
    p = Path(cwd).resolve()
    if not any(p == Path(s).resolve() or Path(s).resolve() in p.parents for s in store.settings()['scopes']):
        raise ValueError('OUTSIDE_SCOPE')
    return p


def _manifest(path, kind):
    files = {}
    for p in sorted(path.rglob('*')):
        if any(x in {'.git', '__pycache__', '.venv', 'node_modules'} for x in p.relative_to(path).parts): continue
        if p.is_symlink(): raise ValueError('SYMLINK_OWNER_REQUIRED')
        if p.is_file():
            if p.stat().st_size > 8_000_000: raise ValueError('PACKAGE_FILE_TOO_LARGE')
            files[str(p.relative_to(path))] = digest(p.read_bytes())
    if ('SKILL.md' if kind == 'skill' else 'command.json') not in files: raise ValueError('CAPABILITY_ENTRY_MISSING')
    return {'files': files, 'package_sha256': digest(canonical(files))}


def capture(store, spec, auto=False):
    """Route a successful receipt; a Stop event cannot certify success."""
    if spec.get('existing_version_id') and (not spec.get('existing_capability_id') or spec.get('update_capability_id')):
        raise ValueError('HISTORICAL_VERSION_REQUIRES_EXISTING_OWNER')
    historical=spec.get('historical_backfill',False)
    if type(historical) is not bool:raise ValueError('HISTORICAL_BACKFILL_BOOLEAN_REQUIRED')
    pinned=None
    if historical:
        if auto or not spec.get('existing_capability_id') or not spec.get('existing_version_id') or spec.get('update_capability_id'):
            raise ValueError('HISTORICAL_BACKFILL_METADATA_ONLY')
        pinned=store.get('capability_catalog',spec['existing_capability_id'])
        version=store.get('capability_versions',spec['existing_version_id'])
        if not pinned or pinned['owner']!=spec.get('owner') or not version or version['capability_id']!=pinned['id']:
            raise ValueError('HISTORICAL_BACKFILL_OWNER_VERSION_MISMATCH')
    for flag in ('successful','reusable'):
        if type(spec.get(flag)) is not bool:raise ValueError('CAPTURE_BOOLEAN_REQUIRED:'+flag)
    for key in ('name', 'owner', 'purpose', 'background', 'origin'):
        if not spec.get(key): raise ValueError('CAPTURE_FIELD_REQUIRED:' + key)
    from .capabilities import _text
    for key in ('name','owner','purpose','background'):_text(spec[key],key,True)
    origin = spec['origin']
    for key in ('session_id', 'turn_id', 'project', 'scenario', 'evidence_sha256'):
        if not origin.get(key): raise ValueError('ORIGIN_FIELD_REQUIRED:' + key)
    # Explicit historical metadata may name the original scratch workspace.
    # It never grants observation, discovery, execution or installation there.
    if not historical:scoped(store, origin['project'])
    store.read_artifact(origin['evidence_sha256'])
    if redact(spec) != spec: raise ValueError('SENSITIVE_CAPTURE_REJECTED')
    cid = 'capture_' + digest(canonical([origin, spec['name']]))[:24]
    prior = store.get('captures', cid); sh = digest(canonical(spec))
    if prior:
        if prior['spec_sha256'] != sh: raise ValueError('CAPTURE_RECEIPT_CONFLICT')
        return prior
    roots=[x for x in store.settings()['scopes'] if Path(x).resolve()==Path(origin['project']).resolve() or Path(x).resolve() in Path(origin['project']).resolve().parents]
    target_scope=spec.get('scope') or (pinned['scope'] if historical else min(roots,key=len))
    scoped(store,target_scope)
    if historical and str(Path(target_scope).resolve())!=pinned['scope']:raise ValueError('HISTORICAL_BACKFILL_SCOPE_CHANGE')
    if not historical and not (Path(origin['project']).resolve()==Path(target_scope).resolve() or Path(target_scope).resolve() in Path(origin['project']).resolve().parents):raise ValueError('ORIGIN_OUTSIDE_CAPABILITY_SCOPE')
    r = {'scope':str(Path(target_scope).resolve()),'id': cid, 'name': spec['name'], 'owner': spec['owner'], 'purpose': spec['purpose'],
         'background': spec['background'], 'origin': origin, 'created_at': now(), 'updated_at': now(),
         'spec_sha256': sh, 'spec_artifact': store.artifact(canonical(spec)), 'missing': [],
         'kind': spec.get('kind'), 'decision': 'hold', 'status': 'hold', 'validation': {'status': 'not_run'}}
    if not spec.get('successful'):
        r.update(reason_code='SUCCESS_EVIDENCE_REQUIRED', missing=['validated_success'])
    elif not spec.get('reusable'):
        r.update(decision='no_change', status='no_change', reason_code='NO_REUSABLE_PROCEDURE')
    else:
        from .capabilities import discover
        found = discover(store, spec['name'], origin['project'])
        existing = next((x for x in found if x['name'] == spec['name']), None)
        if spec.get('update_capability_id'):
            existing=store.get('capability_catalog',spec['update_capability_id'])
            if not existing or existing['owner']!=spec['owner']:raise ValueError('UPDATE_CANONICAL_OWNER_REQUIRED')
            if existing['scope']!=r['scope']:raise ValueError('UPDATE_SCOPE_CHANGE_HOLD')
            r['update_capability_id']=existing['id']
        if spec.get('existing_capability_id'):
            existing = store.get('capability_catalog', spec['existing_capability_id'])
            if not existing: raise ValueError('EXISTING_OWNER_NOT_FOUND')
        if existing and not spec.get('update_capability_id'):
            version_id=spec.get('existing_version_id') or existing['version_id']
            version=store.get('capability_versions',version_id)
            if not version or version['capability_id']!=existing['id']:
                raise ValueError('HISTORICAL_VERSION_CAPABILITY_MISMATCH')
            r.update(decision='existing', status='existing', capability_id=existing['id'],version_id=version_id, reason_code='REUSE_CANONICAL_OWNER')
        elif not spec.get('source_path'):
            r.update(reason_code='CREATOR_PACKAGE_REQUIRED', missing=['creator_package'])
        else:
            if Path(spec['source_path']).is_symlink():raise ValueError('SOURCE_PACKAGE_NOT_REGULAR')
            source = scoped(store, spec['source_path'])
            if not source.is_dir() or source.is_symlink(): raise ValueError('SOURCE_PACKAGE_NOT_REGULAR')
            kind = spec.get('kind') or ('script' if (source/'command.json').is_file() else 'skill')
            if kind not in {'script', 'skill'}: raise ValueError('CAPABILITY_KIND_INVALID')
            m = _manifest(source, kind)
            snapshot = {k: store.artifact((source/k).read_bytes()) for k in m['files']}
            r.update(kind=kind, decision=kind, status='candidate', manifest=m, snapshot=snapshot,
                     candidate_path=str(store.root/'candidates'/cid), source_path=str(source))
            target = Path(r['candidate_path'])
            if target.exists(): raise ValueError('CANDIDATE_PATH_CONFLICT')
            target.mkdir(parents=True, mode=0o700)
            for name, h in snapshot.items(): atomic_write(target/name, store.read_artifact(h))
    store.put('captures', r)
    if auto and r['status'] == 'candidate':
        r = validate_capture(store, cid)
        if r['validation']['status'] == 'passed' and r['kind'] == 'script': r = activate_capture(store, cid)
    return r


def _command(path):
    spec = json.loads((path/'command.json').read_text())
    for k in ('entrypoint', 'inputs', 'result', 'permissions', 'positive', 'negative'):
        if k not in spec: raise ValueError('COMMAND_CONTRACT_REQUIRED:' + k)
    entry = Path(spec['entrypoint'])
    if entry.is_absolute() or '..' in entry.parts or entry.suffix != '.py': raise ValueError('ENTRYPOINT_INVALID')
    if not (path/entry).is_file(): raise ValueError('ENTRYPOINT_MISSING')
    if spec['permissions'] != ['pure_json']: raise ValueError('OWNER_REPLAY_REQUIRED_FOR_SIDE_EFFECTS')
    if not isinstance(spec['positive'], list) or not spec['positive'] or not isinstance(spec['negative'], list) or not spec['negative']:
        raise ValueError('FORWARD_AND_COUNTEREXAMPLE_REQUIRED')
    return spec


def _run(path, spec, value, cwd):
    # Restricted deterministic JSON lane. External/filesystem flows retain their owner.
    # This static guard is defense in depth, NOT isolation of untrusted code.
    tree = ast.parse((path/spec['entrypoint']).read_text())
    allowed = {'json', 'sys', 'math', 're', 'collections', 'statistics', 'decimal', 'datetime', 'hashlib'}
    banned = {'open', 'eval', 'exec', 'compile', '__import__', 'getattr', 'setattr', 'delattr', 'globals', 'locals', 'vars', 'breakpoint', 'input'}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = [x.name.split('.')[0] for x in node.names] if isinstance(node, ast.Import) else [(node.module or '').split('.')[0]]
            if any(x not in allowed for x in modules) or getattr(node, 'level', 0) or any(x.name.startswith('_') for x in node.names) or (isinstance(node,ast.ImportFrom) and node.module=='sys'): raise ValueError('PURE_JSON_IMPORT_REJECTED')
        if isinstance(node, ast.Name) and node.id in banned: raise ValueError('PURE_JSON_DYNAMIC_ACCESS_REJECTED')
        if isinstance(node, ast.Attribute) and (node.attr.startswith('_') or node.attr in {'modules', 'path', 'argv', 'exit', 'stdout', 'stderr', 'settrace', 'setprofile'}):
            raise ValueError('PURE_JSON_DYNAMIC_ACCESS_REJECTED')
    payload = canonical(value)
    if len(payload) > 1_000_000: raise ValueError('INPUT_TOO_LARGE')
    def limits():
        import resource
        resource.setrlimit(resource.RLIMIT_CPU,(30,30))
        resource.setrlimit(resource.RLIMIT_FSIZE,(1_100_000,1_100_000))
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        p = subprocess.Popen([sys.executable, '-I', '-B', str(path/spec['entrypoint'])], cwd=cwd,
                             stdin=subprocess.PIPE, stdout=out, stderr=err,
                             env={'PATH': os.defpath, 'PYTHONIOENCODING': 'utf-8'},preexec_fn=limits)
        try: p.communicate(payload, timeout=max(1, min(int(spec.get('timeout_seconds', 10)), 30)))
        except subprocess.TimeoutExpired:
            p.kill(); p.communicate(); raise ValueError('REPLAY_TIMEOUT')
        out.seek(0); stdout = out.read(1_000_001)
        if len(stdout) > 1_000_000: raise ValueError('RESULT_TOO_LARGE')
        if p.returncode != 0: return {'exit_code': p.returncode, 'result': None}
        try: result = json.loads(stdout)
        except ValueError: raise ValueError('RESULT_NOT_JSON')
        if redact(result) != result: raise ValueError('SENSITIVE_RESULT_REJECTED')
        return {'exit_code': 0, 'result': result}


def validate_capture(store, cid):
    r = store.get('captures', cid)
    if not r or r['status'] not in {'candidate', 'validated', 'failed'}: raise ValueError('CAPTURE_NOT_VALIDATABLE')
    path = Path(r['candidate_path'])
    if _manifest(path, r['kind']) != r['manifest']: raise ValueError('CANDIDATE_DRIFT_HOLD')
    evidence = {'capture_id': cid, 'package_sha256': r['manifest']['package_sha256'], 'python': sys.version.split()[0]}
    try:
        if r['kind'] == 'skill':
            content = (path/'SKILL.md').read_text()
            if not content.startswith('---') or 'description:' not in content or 'name:' not in content: raise ValueError('SKILL_FRONTMATTER_REQUIRED')
            r['validation'] = {'status': 'hold', 'reason_code': 'INDEPENDENT_FORWARD_SKILL_TEST_REQUIRED'}
            r.update(missing=['independent_forward_skill_test'], status='hold')
        else:
            spec = _command(path)
            with tempfile.TemporaryDirectory(prefix='skillobs-check-') as cwd:
                for sample in spec['positive']:
                    v = _run(path, spec, sample['input'], cwd)
                    if v['exit_code'] != 0 or v['result'] != sample['expected']: raise ValueError('POSITIVE_CASE_FAILED')
                for sample in spec['negative']:
                    if _run(path, spec, sample['input'], cwd)['exit_code'] == 0: raise ValueError('COUNTEREXAMPLE_FAILED')
            evidence.update(positive_passed=len(spec['positive']), negative_passed=len(spec['negative']))
            r['validation'] = {'status': 'passed', **evidence, 'evidence_sha256': store.artifact(canonical(evidence)), 'security_sandbox': False}
            r.update(status='validated', missing=[])
    except (ValueError, KeyError, SyntaxError) as ex:
        r.update(status='failed', reason_code=str(ex), validation={'status': 'failed', 'reason_code': str(ex)})
    r['updated_at'] = now(); store.put('captures', r); return r


def activate_capture(store, cid):
    from .capabilities import register_capability
    r = store.get('captures', cid)
    if r and r['status'] == 'active': return r
    if not r or r['status'] != 'validated' or r['validation']['status'] != 'passed': raise ValueError('VALIDATION_REQUIRED')
    if r['kind']=='skill' and not r.get('forward_receipt_sha256'):raise ValueError('SKILL_OWNER_ADMISSION_REQUIRED')
    source = Path(r['candidate_path'])
    if _manifest(source, r['kind']) != r['manifest']: raise ValueError('CANDIDATE_DRIFT_HOLD')
    target = store.root/'capabilities'/cid
    if target.exists() and _manifest(target, r['kind']) != r['manifest']: raise ValueError('INSTALLATION_DRIFT_HOLD')
    if not target.exists():
        temporary=target.parent/('.install-'+uuid.uuid4().hex)
        temporary.mkdir(parents=True,mode=0o700)
        for name,h in r['snapshot'].items():atomic_write(temporary/name,store.read_artifact(h))
        if _manifest(temporary,r['kind'])!=r['manifest']:raise ValueError('INSTALLATION_READBACK_FAILED')
        temporary.rename(target)
    roots = [s for s in store.settings()['scopes'] if Path(s).resolve() == Path(r['origin']['project']).resolve() or Path(s).resolve() in Path(r['origin']['project']).resolve().parents]
    cap = register_capability(store, target, r['owner'], kind=r['kind'], purpose=r['purpose'], background=r['background'], origin=r['origin'], capability_id=r.get('update_capability_id'), scope=json.loads(store.read_artifact(r['forward_receipt_sha256']))['scope'] if r['kind']=='skill' else r['scope'])
    cap.update(status='active', name=r['name'], born_at=cap.get('born_at') if r.get('update_capability_id') else r['created_at'], permissions=['pure_json'] if r['kind']=='script' else json.loads(store.read_artifact(r['forward_receipt_sha256']))['permissions'], activation_capture_id=cid,
               activation={'status': 'installed', 'validation_evidence_sha256': r['validation']['evidence_sha256'], 'created_at': now()})
    store.put('capability_catalog', cap)
    r.update(status='active', capability_id=cap['id'],version_id=cap['version_id'], updated_at=now()); store.put('captures', r); return r


def replay(store, capability_id, value, cwd, session_id, turn_id, scenario, invocation_id):
    from .capabilities import record_usage
    scoped(store, cwd)
    cap = store.get('capability_catalog', capability_id)
    if not cap or cap['status'] != 'active' or cap['kind'] != 'script': raise ValueError('ACTIVE_SCRIPT_REQUIRED')
    scope = Path(cap['scope']).resolve(); original = Path(cwd).resolve()
    if original != scope and scope not in original.parents: raise ValueError('OUTSIDE_CAPABILITY_SCOPE')
    path = Path(cap['path']); version = store.get('capability_versions', cap['version_id'])
    if _manifest(path, 'script')['package_sha256'] != version['package_sha256']: raise ValueError('INSTALLED_VERSION_DRIFT_HOLD')
    spec = _command(path); capture_record = store.get('captures', cap['activation_capture_id'])
    if capture_record['validation']['python'] != sys.version.split()[0]: raise ValueError('ENVIRONMENT_REVALIDATION_REQUIRED')
    if not all((session_id, turn_id, scenario, invocation_id)): raise ValueError('INVOCATION_CONTEXT_REQUIRED')
    attempt = 'attempt_' + uuid.uuid4().hex
    base = {'capability_id': cap['id'], 'version_id': cap['version_id'], 'cwd': str(original), 'session_id': session_id,
            'turn_id': turn_id, 'scenario': scenario, 'invocation_id': invocation_id, 'source': 'replay-cli', 'attempt_id': attempt,
            'origin': 'activation_canary' if scenario.startswith('canary:') else 'user_run'}
    record_usage(store, {**base, 'stage': 'selected', 'event_id': attempt + '_selected'})
    try:
        with tempfile.TemporaryDirectory(prefix='skillobs-replay-') as temporary: outcome = _run(path, spec, value, temporary)
        evidence = store.artifact(canonical({'capability_id': cap['id'], 'version_id': cap['version_id'], 'input_sha256': digest(canonical(value)), 'outcome': outcome, 'attempt_id': attempt}))
        record_usage(store, {**base, 'stage': 'executed', 'event_id': attempt + '_executed', 'status': 'completed' if outcome['exit_code'] == 0 else 'failed', 'evidence_sha256': evidence})
        return {**outcome, 'attempt_id': attempt, 'evidence_sha256': evidence, 'acceptance': 'unverified'}
    except Exception as ex:
        evidence = store.artifact(canonical({'attempt_id': attempt, 'reason_code': str(ex), 'status': 'failed'}))
        record_usage(store, {**base, 'stage': 'executed', 'event_id': attempt + '_failed', 'status': 'failed', 'evidence_sha256': evidence})
        raise


def accept_skill_forward(store, cid, receipt):
    """Trusted root ingress after actual independent forward/counterexample review.

Not available over HTTP. Root must inspect actual artifacts before invoking it;
this function validates bindings, not the semantic truth of a review statement.
"""
    r=store.get('captures',cid)
    if not r or r['kind']!='skill' or r['status'] not in {'candidate','hold'}:
        raise ValueError('SKILL_FORWARD_CANDIDATE_REQUIRED')
    if _manifest(Path(r['candidate_path']),'skill')!=r['manifest']:raise ValueError('CANDIDATE_DRIFT_HOLD')
    if receipt.get('package_sha256')!=r['manifest']['package_sha256']:raise ValueError('FORWARD_VERSION_MISMATCH')
    if receipt.get('reviewed_by_root')!=r['origin']['session_id']:raise ValueError('ROOT_REVIEW_REQUIRED')
    if not receipt.get('scope'):raise ValueError('CLASSIFIED_SCOPE_REQUIRED')
    scoped(store,receipt['scope'])
    if str(Path(receipt['scope']).resolve())!=r['scope']:raise ValueError('CLASSIFIED_SCOPE_MISMATCH')
    if receipt.get('owner')!=r['owner'] or receipt.get('trusted_source')!='user-owned':raise ValueError('CREATOR_OWNER_ADMISSION_REQUIRED')
    if not isinstance(receipt.get('permissions'),list):raise ValueError('PERMISSIONS_REQUIRED')
    for case in ('positive','negative'):
        v=receipt.get(case,{})
        if not v.get('session_id') or v['session_id']==r['origin']['session_id'] or not v.get('turn_id') or v.get('status')!='passed':
            raise ValueError('INDEPENDENT_FORWARD_CASE_REQUIRED')
        for key in ('input_sha256','result_sha256'):store.read_artifact(v.get(key,''))
    h=store.artifact(canonical(redact(receipt)))
    r.update(status='validated',missing=[],updated_at=now(),forward_receipt_sha256=h,
             validation={'status':'passed','evidence_sha256':h,'positive_passed':1,'negative_passed':1,'basis':'root_reviewed_independent_forward','python':sys.version.split()[0]})
    store.put('captures',r);return r


def retire_capability(store, capability_id, reason):
    """Keep historical versions and uses; stop future discovery/execution."""
    cap=store.get('capability_catalog',capability_id)
    if not cap:raise ValueError('CAPABILITY_NOT_FOUND')
    if not reason or redact(reason)!=reason:raise ValueError('RETIRE_REASON_REQUIRED')
    cap.update(status='retired',retired_at=now(),retire_reason=reason);store.put('capability_catalog',cap);return cap
