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
    if not str(meta.get('cli_version','')).startswith('0.160.'):raise ValueError('TRANSCRIPT_VERSION_UNVERIFIED')
    cursor_id='cursor_'+digest(str(path).encode())[:24]
    cursor=store.get('cursors',cursor_id) or {'offset':0,'prefix_sha256':digest(b'')}
    offset=cursor['offset']
    # A replaced/truncated session file cannot inherit the previous cursor.
    with path.open('rb') as f:
        prefix=f.read(offset)
        if len(prefix)!=offset or digest(prefix)!=cursor['prefix_sha256']:raise ValueError('TRANSCRIPT_DRIFT_HOLD')
        f.seek(offset);tail=f.read()
    complete=tail[:tail.rfind(b'\n')+1] if b'\n' in tail else b''
    turn=cursor.get('turn_id');calls=cursor.get('calls',{});count=0
    registered=store.list('skills')
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
            calls[v.get('call_id')]=[s['id'] for s in registered if str(Path(s['path'])/'SKILL.md') in raw]
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
            for s in registered:
                if s['id'] in calls.get(v.get('call_id'),[]):
                    content=(Path(s['path'])/'SKILL.md').read_text()
                    if any(content in t for t in expanded):
                        base.setdefault('verified_attributions',[]).append({'skill_id':s['id'],'package_sha256':s['package_sha256'],'file_sha256':digest(content.encode()),'attribution':'verified_read','loaded_version_source':'exact_whole_tool_output','observed_at':o.get('timestamp')})
            calls.pop(v.get('call_id'),None)
        if event:
            base['hook_event_name']=event;base['transcript_record_sha256']=digest(line)
            # Same persistence path as lifecycle hooks; no second event store.
            r=spool(store,base,source=source)
            if r['status']=='spooled':count+=1
    end=offset+len(complete)
    store.put('cursors',{'id':cursor_id,'offset':end,'prefix_sha256':digest(prefix+complete),'turn_id':turn,'calls':calls,'created_at':now(),'source':source})
    return {'source':source,'session_id':expected_session_id,'new_events':count,'offset':end,'coverage':'partial_versioned_adapter','global_denominator':None}
