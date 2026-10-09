"""CLI uses the same kernel as the UI and daemon."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time
from .store import Store, atomic_write, canonical, digest, now
from .runtime import EVENTS, spool, tick, state, register, accept_review
from .installations import recover, rollback


def install_hooks(store, project, scope=None):
    root=Path(project).resolve();p=root/'.codex/hooks.json'
    scope_root=Path(scope).resolve() if scope is not None else root
    before=p.read_bytes() if p.exists() else None
    data=json.loads(before) if before else {'description':'Skill Observatory scoped observation; native trust required','hooks':{}}
    command=' '.join([shlex.quote(sys.executable),'-m','skill_observatory.cli','--state',shlex.quote(str(store.root)),'hook'])
    existing=[]
    for event in sorted(EVENTS):
        groups=data.setdefault('hooks',{}).setdefault(event,[])
        if any(h.get('command')==command for g in groups for h in g.get('hooks',[])):continue
        groups.append({'hooks':[{'type':'command','command':command,'timeout':1 if event in {'SessionEnd','Interrupt'} else 3}]})
    after=canonical(data)
    if before==after:
        scopes=store.settings()['scopes']
        if str(scope_root) not in scopes:store.settings({'scopes':scopes+[str(scope_root)]})
        return {'status':'already_installed','trust':'native_review_required'}
    receipt={'id':'hooks_'+digest(str(p).encode())[:20],'target':str(p),'before_sha256':store.artifact(before) if before else None,'after_sha256':store.artifact(after),'created_at':now(),'status':'installed','trust':'native_review_required'}
    if p.exists() and before!=p.read_bytes():raise ValueError('HOOK_DRIFT_HOLD')
    atomic_write(p,after);store.put('hook_installations',receipt)
    scopes=store.settings()['scopes']
    if str(scope_root) not in scopes:store.settings({'scopes':scopes+[str(scope_root)]})
    return receipt


def uninstall_hooks(store,project):
    p=Path(project).resolve()/'.codex/hooks.json';id='hooks_'+digest(str(p).encode())[:20]
    r=store.get('hook_installations',id)
    if not r:raise ValueError('HOOK_INSTALLATION_NOT_FOUND')
    if digest(p.read_bytes())!=r['after_sha256']:raise ValueError('HOOK_DRIFT_HOLD')
    if r['before_sha256']:atomic_write(p,store.read_artifact(r['before_sha256']))
    else:p.unlink()
    r['status']='uninstalled';store.put('hook_installations',r);return r


def doctor(store):
    docker=shutil.which('docker');check=None
    if docker:
        try:
            r=subprocess.run([docker,'info','--format','{{.ServerVersion}}'],capture_output=True,text=True,timeout=10)
            check={'available':r.returncode==0,'version':r.stdout.strip() if r.returncode==0 else None,'reason_code':None if r.returncode==0 else 'DOCKER_UNAVAILABLE'}
        except (subprocess.TimeoutExpired,OSError):check={'available':False,'reason_code':'DOCKER_UNAVAILABLE'}
    return {'runtime':'skill-observatory','python':sys.version.split()[0],'codex_cli':shutil.which('codex') is not None,'docker':check or {'available':False,'reason_code':'DOCKER_MISSING'},'state_private':oct(store.root.stat().st_mode&0o777),'hook_trust':'NATIVE_REVIEW_REQUIRED','model_broker':(store.get('runtime','reviewer') or {}).get('status','UNCONFIGURED'),'claim_layers':{'loop_operational':'PARTIAL','skill_task_improved':'UNVERIFIED','real_user_outcome_improved':'UNKNOWN'}}


def main():
    ap=argparse.ArgumentParser(prog='skillobs');ap.add_argument('--state')
    sub=ap.add_subparsers(dest='command',required=True)
    for c in ['doctor','status','hook','tick','daemon','recover']:sub.add_parser(c)
    p=sub.add_parser('register');p.add_argument('path');p.add_argument('--owner',required=True);p.add_argument('--license')
    p=sub.add_parser('capability-register');p.add_argument('path');p.add_argument('--owner',required=True);p.add_argument('--kind',choices=['skill','script'],default='skill');p.add_argument('--purpose');p.add_argument('--background');p.add_argument('--origin-file');p.add_argument('--scope',required=True);p.add_argument('--id')
    p=sub.add_parser('discover');p.add_argument('--query',default='');p.add_argument('--cwd',required=True)
    p=sub.add_parser('artifact-import');p.add_argument('file')
    p=sub.add_parser('usage-import');p.add_argument('file')
    p=sub.add_parser('capture');p.add_argument('--spec',required=True);p.add_argument('--auto',action='store_true')
    for command in ('capture-validate','capture-activate'):
        p=sub.add_parser(command);p.add_argument('id')
    p=sub.add_parser('capture-forward');p.add_argument('id');p.add_argument('--receipt',required=True)
    p=sub.add_parser('capability-retire');p.add_argument('id');p.add_argument('--reason',required=True)
    p=sub.add_parser('replay');p.add_argument('id');p.add_argument('--input',required=True);p.add_argument('--cwd',required=True);p.add_argument('--session-id',required=True);p.add_argument('--turn-id',required=True);p.add_argument('--scenario',required=True);p.add_argument('--invocation-id',required=True)
    for c in ['install-hooks','uninstall-hooks']:
        p=sub.add_parser(c);p.add_argument('--project',required=True)
        if c=='install-hooks':p.add_argument('--scope',help='Authorized observation root; defaults to the hook project')
    p=sub.add_parser('serve');p.add_argument('--port',type=int,default=8765);p.add_argument('--web-root')
    p=sub.add_parser('observe-session');p.add_argument('path');p.add_argument('--session-id',required=True);p.add_argument('--source',choices=['codex-desktop','codex-cli','codex-subagent'],required=True)
    for c in ['service-install','service-start','service-stop','service-uninstall','service-status']:
        p=sub.add_parser(c)
        if c=='service-install':p.add_argument('--port',type=int,default=8765);p.add_argument('--web-root')
    p=sub.add_parser('review-import');p.add_argument('file');p.add_argument('--reviewer',required=True)
    p=sub.add_parser('rollback');p.add_argument('id')
    p=sub.add_parser('export');p.add_argument('--output',required=True)
    args=ap.parse_args();s=Store(args.state)
    try:
        if args.command=='hook':
            # No LLM/network/transcript scan here. Fast atomic spool only.
            raw=sys.stdin.buffer.read(1_000_001)
            if len(raw)>1_000_000:raise ValueError('HOOK_INPUT_TOO_LARGE')
            spool(s,json.loads(raw));print('{}');return
        if args.command=='doctor':result=doctor(s)
        elif args.command=='status':result=state(s)
        elif args.command=='register':result=register(s,args.path,args.owner,license=args.license)
        elif args.command=='capability-register':
            from .capabilities import register_capability
            result=register_capability(s,args.path,args.owner,kind=args.kind,purpose=args.purpose,background=args.background,origin=json.loads(Path(args.origin_file).read_text()) if args.origin_file else None,scope=args.scope,capability_id=args.id)
        elif args.command=='discover':
            from .capabilities import discover
            result=discover(s,args.query,args.cwd)
        elif args.command=='artifact-import':
            data=Path(args.file).read_bytes()
            if len(data)>8_000_000:raise ValueError('ARTIFACT_TOO_LARGE')
            from .runtime import redact
            if redact(data.decode('utf-8'))!=data.decode('utf-8'):raise ValueError('SENSITIVE_ARTIFACT_REJECTED')
            result={'evidence_sha256':s.artifact(data)}
        elif args.command=='usage-import':
            from .capabilities import record_usage
            result=record_usage(s,json.loads(Path(args.file).read_text()))
        elif args.command=='capture':
            from .capture import capture
            result=capture(s,json.loads(Path(args.spec).read_text()),auto=args.auto)
        elif args.command=='capture-validate':
            from .capture import validate_capture
            result=validate_capture(s,args.id)
        elif args.command=='capture-activate':
            from .capture import activate_capture
            result=activate_capture(s,args.id)
        elif args.command=='capture-forward':
            from .capture import accept_skill_forward
            result=accept_skill_forward(s,args.id,json.loads(Path(args.receipt).read_text()))
        elif args.command=='capability-retire':
            from .capture import retire_capability
            result=retire_capability(s,args.id,args.reason)
        elif args.command=='replay':
            from .capture import replay
            result=replay(s,args.id,json.loads(Path(args.input).read_text()),args.cwd,args.session_id,args.turn_id,args.scenario,args.invocation_id)
        elif args.command=='install-hooks':result=install_hooks(s,args.project,args.scope)
        elif args.command=='uninstall-hooks':result=uninstall_hooks(s,args.project)
        elif args.command=='tick':
            from .configuration import load_reviewer,load_pipeline
            result=tick(s,load_reviewer(s),load_pipeline(s))
        elif args.command=='observe-session':
            from .transcripts import observe_session
            result=observe_session(s,args.path,args.session_id,args.source)
            s.put('selected_sessions',{'id':'selected_'+digest(str(Path(args.path).resolve()).encode())[:24],'path':str(Path(args.path).resolve()),'session_id':args.session_id,'source':args.source})
        elif args.command.startswith('service-'):
            from .service import service
            result=service(s,args.command,port=getattr(args,'port',8765),web_root=getattr(args,'web_root',None))
        elif args.command=='recover':result=recover(s)
        elif args.command=='review-import':result=accept_review(s,json.loads(Path(args.file).read_text()),args.reviewer)
        elif args.command=='rollback':result=rollback(s,args.id)
        elif args.command=='daemon':
            from .configuration import load_reviewer,load_pipeline
            reviewer=load_reviewer(s);pipeline=load_pipeline(s)
            while True:tick(s,reviewer,pipeline);time.sleep(1)
        elif args.command=='serve':
            import uvicorn
            from .api import create_app
            from .configuration import load_reviewer,load_pipeline
            uvicorn.run(create_app(s,args.web_root,reviewer=load_reviewer(s),pipeline=load_pipeline(s)),host='127.0.0.1',port=args.port);return
        elif args.command=='export':
            # Deliberate allowlist; excludes names, sessions, paths, artifacts and free text.
            data=state(s);result={'schema_version':1,'claim_layers':doctor(s)['claim_layers'],'counts':{k:len(data[k]) for k in ['skills','runs','reviews','experiments','installations']},'coverage':{'global':None,'reason_code':'GLOBAL_DENOMINATOR_UNKNOWN'}}
            atomic_write(Path(args.output),canonical(result))
        print(json.dumps(result,ensure_ascii=False,indent=2))
        if args.command=='replay' and result['exit_code']!=0:raise SystemExit(1)
    except KeyboardInterrupt:return
    except Exception as ex:
        print(json.dumps({'status':'hold','reason_code':str(ex)},ensure_ascii=False),file=sys.stderr);raise SystemExit(1)


if __name__=='__main__':main()
