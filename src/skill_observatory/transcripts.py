"""Explicit incremental adapter, limited to a selected session in an authorized scope."""
from __future__ import annotations
import json
from pathlib import Path
from .runtime import spool
from .store import atomic_write, canonical, digest, now


def observe_session(store,path,expected_session_id,source):
    if source not in {'codex-desktop','codex-cli','codex-subagent'}:raise ValueError('SOURCE_NOT_SUPPORTED')
    path=Path(path).resolve()
    if not path.is_file() or path.is_symlink():raise ValueError('TRANSCRIPT_NOT_REGULAR')
    # No enumeration or historical bulk import. User explicitly supplies exact session.
    with path.open() as f:
        first=json.loads(f.readline())
    meta=first.get('payload',{})
    if first.get('type')!='session_meta' or meta.get('id',meta.get('session_id'))!=expected_session_id:raise ValueError('SESSION_ID_MISMATCH')
    cwd=Path(meta['cwd']).resolve()
    if not any(cwd==Path(s).resolve() or Path(s).resolve() in cwd.parents for s in store.settings()['scopes']):raise ValueError('OUTSIDE_SCOPE')
    # Exact current adapter shape verified against 0.162.0-alpha.2; future versions stay held.
    version=str(meta.get('cli_version',''))
    if not (version.startswith('0.160.') or version=='0.162.0-alpha.2'):raise ValueError('TRANSCRIPT_VERSION_UNVERIFIED')
    cursor_id='cursor_'+digest(str(path).encode())[:24]
    cursor=store.get('cursors',cursor_id) or {'offset':0,'prefix_sha256':digest(b'')}
    offset=cursor['offset']
    stat=path.stat()
    if cursor.get('mtime_ns')==stat.st_mtime_ns and cursor.get('inode')==stat.st_ino and cursor.get('size')==stat.st_size:
        return {'source':source,'session_id':expected_session_id,'new_events':0,'offset':offset,'coverage':'partial_versioned_adapter','global_denominator':None}
    # A replaced/truncated session file cannot inherit the previous cursor.
    with path.open('rb') as f:
        prefix=f.read(offset)
        if len(prefix)!=offset or digest(prefix)!=cursor['prefix_sha256']:raise ValueError('TRANSCRIPT_DRIFT_HOLD')
        f.seek(offset);tail=f.read()
    complete=tail[:tail.rfind(b'\n')+1] if b'\n' in tail else b''
    turn=cursor.get('turn_id');calls=cursor.get('calls',{});count=0
    registered=store.list('skills');catalog=store.list('capability_catalog')
    for line in complete.splitlines():
        o=json.loads(line);v=o.get('payload',{});type=o.get('type')
        if type=='turn_context':turn=v.get('turn_id',turn)
        base={'session_id':expected_session_id,'turn_id':turn,'cwd':str(cwd),'origin':'user_run'}
        if source=='codex-subagent':base['agent_id']=expected_session_id
        event=None
        if type=='event_msg':
            event={'task_started':'UserPromptSubmit','task_complete':'Stop','turn_aborted':'Interrupt','task_interrupted':'Interrupt'}.get(v.get('type'))
            if v.get('turn_id'):base['turn_id']=v['turn_id'];turn=v['turn_id']
        elif type=='response_item' and v.get('type') in {'function_call','custom_tool_call'}:
            event='PreToolUse';base.update(tool_use_id=v.get('call_id'),tool_name=v.get('name'))
            raw=v.get('arguments',v.get('input',''))
            calls[v.get('call_id')]={'skills':[s['id'] for s in registered if str(Path(s['path'])/'SKILL.md') in raw],
                'caps':[{'capability_id':c['id'],'version_id':c['version_id'],'file_sha256':digest((Path(c['path'])/'SKILL.md').read_bytes()),
                         'content_sha256':store.artifact((Path(c['path'])/'SKILL.md').read_bytes())}
                        for c in catalog if c['kind']=='skill' and str(Path(c['path'])/'SKILL.md') in raw and (Path(c['path'])/'SKILL.md').is_file()]}
            base['tool_input']=raw  # spool persists only digest/path attribution, never raw input
        elif type=='response_item' and v.get('type') in {'function_call_output','custom_tool_call_output'}:
            event='PostToolUse';base.update(tool_use_id=v.get('call_id'))
            # Confirm exact whole Skill bytes present in a trusted native tool response.
            outputs=v.get('output',[]);texts=[]
            if isinstance(outputs,str):texts.append(outputs)
            elif isinstance(outputs,list):texts.extend(x.get('text','') for x in outputs if isinstance(x,dict))
            expanded=list(texts)
            for t in texts:
                try:
                    j=json.loads(t)
                    if isinstance(j,dict) and isinstance(j.get('output'),str):expanded.append(j['output'])
                except (ValueError,TypeError):pass
            binding=calls.get(v.get('call_id'),{})
            ids=binding.get('skills',[]) if isinstance(binding,dict) else binding
            for c in binding.get('caps',[]) if isinstance(binding,dict) else []:
                content=store.read_artifact(c['content_sha256']).decode()
                version_record=store.get('capability_versions',c['version_id'])
                if version_record and version_record['manifest']['files'].get('SKILL.md')==c['file_sha256'] and any(content in t for t in expanded):
                    base.setdefault('capability_observations',[]).append({'capability_id':c['capability_id'],'version_id':c['version_id'],'stage':'verified_read'})
            for s in registered:
                if s['id'] in ids:
                    cap_binding=next((c for c in binding.get('caps',[]) if store.get('capability_catalog',c['capability_id'])['path']==s['path']),None) if isinstance(binding,dict) else None
                    content=store.read_artifact(cap_binding['content_sha256']).decode() if cap_binding else (Path(s['path'])/'SKILL.md').read_text()
                    if any(content in t for t in expanded):
                        base.setdefault('verified_attributions',[]).append({'skill_id':s['id'],'package_sha256':s['package_sha256'],'file_sha256':digest(content.encode()),'attribution':'verified_read','loaded_version_source':'exact_whole_tool_output','observed_at':o.get('timestamp')})
            calls.pop(v.get('call_id'),None)
        if event:
            base['hook_event_name']=event;base['transcript_record_sha256']=digest(line)
            # Same persistence path as lifecycle hooks; no second event store.
            r=spool(store,base,source=source)
            if r['status']=='spooled':count+=1
    end=offset+len(complete)
    store.put('cursors',{'id':cursor_id,'offset':end,'prefix_sha256':digest(prefix+complete),'turn_id':turn,'calls':calls,'created_at':now(),'source':source,'mtime_ns':stat.st_mtime_ns,'inode':stat.st_ino,'size':stat.st_size})
    return {'source':source,'session_id':expected_session_id,'new_events':count,'offset':end,'coverage':'partial_versioned_adapter','global_denominator':None}


def track_hook_session(store, event):
    """Follow one trusted native hook pointer from NOW, never enumerate history."""
    path=Path(event['transcript_path'])
    if path.is_symlink() or not path.is_file():raise ValueError('TRANSCRIPT_NOT_REGULAR')
    path=path.resolve();sid=event.get('session_id')
    with path.open('rb') as f:first=json.loads(f.readline())
    meta=first.get('payload',{})
    if first.get('type')!='session_meta' or meta.get('id',meta.get('session_id'))!=sid:raise ValueError('SESSION_ID_MISMATCH')
    cwd=Path(meta['cwd']).resolve()
    if not any(cwd==Path(s).resolve() or Path(s).resolve() in cwd.parents for s in store.settings()['scopes']):raise ValueError('OUTSIDE_SCOPE')
    if not (str(meta.get('cli_version','')).startswith('0.160.') or meta.get('cli_version')=='0.162.0-alpha.2'):
        raise ValueError('TRANSCRIPT_VERSION_UNVERIFIED')
    selected_id='selected_'+digest(str(path).encode())[:24]
    selected=store.get('selected_sessions',selected_id)
    if not selected:
        content=path.read_bytes();offset=content.rfind(b'\n')+1
        stat=path.stat()
        store.put('cursors',{'id':'cursor_'+digest(str(path).encode())[:24],'offset':offset,
            'prefix_sha256':digest(content[:offset]),'turn_id':event.get('turn_id'),'calls':{},'created_at':now(),
            'mtime_ns':stat.st_mtime_ns,'inode':stat.st_ino,'size':stat.st_size,'coverage_start':'native_hook_attachment'})
        selected={'id':selected_id,'path':str(path),'session_id':sid,'source':'codex-subagent' if event.get('agent_id') else 'codex-desktop',
                  'created_at':now(),'coverage_start':'native_hook_attachment','missing':['BEFORE_ATTACHMENT_NOT_OBSERVED']}
    selected['closed']=event['event']=='SessionEnd'
    store.put('selected_sessions',selected)
    return selected
