"""Native task-family bridge over the existing evaluation ledger/final kernel.

Codex's admitted native spawn/bind tools own execution. This bridge freezes work,
claims final samples before dispatch and consumes actual native traces/artifacts.
It never launches shell workers, signs domain truth or supplies guessed costs.
"""
from __future__ import annotations
import json
import math
import secrets
import os
from pathlib import Path
from .store import canonical,digest,now,atomic_write
from .evaluation import claim_evaluation,EvaluationHold
from .packages import freeze_package,read_package,trial_manifest,snapshot_package


class NativeTaskFamilyDriver:
    def __init__(self,store,protocol_id):
        self.store=store;self.protocol_id=protocol_id

    @classmethod
    def prepare(cls,store,protocol,parent,candidate,cases,oracle,work_root):
        identity=protocol.get('execution_identity',{})
        if identity.get('kind')!='native-task-family' or not all(identity.get(k) for k in ('model','provider','effort','runtime_sha256','tool_contract_sha256')):
            raise EvaluationHold('TASK_FAMILY_NATIVE_IDENTITY_REQUIRED')
        if (identity['model'],identity['effort'])!=(protocol['model'],protocol['max_verified_effort']):raise EvaluationHold('EXECUTION_IDENTITY_DRIFT')
        from .packages import validate_names
        output_names=identity.get('output_files',['result.json']);validate_names(output_names)
        if not output_names:raise EvaluationHold('TASK_OUTPUT_CONTRACT_REQUIRED')
        for arm,files in [('parent',parent),('candidate',candidate)]:
            if {n:digest(b) for n,b in files.items()}!=protocol['arm_files'][arm]:raise EvaluationHold('ARM_HASH_DRIFT')
            if set(output_names)&set(files):raise EvaluationHold('TASK_OUTPUT_OVERWRITES_INPUT')
        if any(set(output_names)&set(c.input_files) for c in cases):raise EvaluationHold('TASK_OUTPUT_OVERWRITES_INPUT')
        actual=[{'id':c.id,'source':c.source,'split':c.split,'evidence_sha256':c.evidence_sha256,'inputs_sha256':digest(canonical({k:digest(v) for k,v in c.input_files.items()})),'input_files':{k:digest(v) for k,v in c.input_files.items()},'categories':list(c.categories)} for c in cases]
        if actual!=protocol['cases'] or oracle.sha256!=protocol['oracle_sha256']:raise EvaluationHold('TASK_FAMILY_FROZEN_INPUT_DRIFT')
        if not any(c.split=='final' for c in cases):raise EvaluationHold('FROZEN_FINAL_ALLOCATION_REQUIRED')
        root=Path(work_root)
        from .transcripts import _inside_scope
        if root.is_symlink() or any(p.is_symlink() for p in root.parents):raise EvaluationHold('TASK_WORKSPACE_SYMLINK')
        if not _inside_scope(store,root):raise EvaluationHold('OUTSIDE_SCOPE')
        root.mkdir(parents=True,exist_ok=True,mode=0o700)
        if any(root.iterdir()):raise EvaluationHold('TASK_FAMILY_FRESH_WORKSPACE_REQUIRED')
        attempt,claims,missing=claim_evaluation(store,protocol,actual)
        if missing:raise EvaluationHold(missing[0])
        store.artifact(canonical(oracle.descriptor))
        tickets=[]
        for case in cases:
            if case.split!='final':continue
            for arm,files in [('parent',parent),('candidate',candidate)]:
                if set(files)&set(case.input_files):raise EvaluationHold('CASE_OVERWRITES_SKILL')
                id_=attempt+'_'+case.id+'_'+arm
                work=root/id_;work.mkdir(mode=0o700)
                package=trial_manifest(protocol,arm,files,case.input_files)
                package=freeze_package(store,{**files,**case.input_files},{e['path']:e['mode'] for e in package['entries']})
                for name,data in read_package(store,package).items():
                    atomic_write(work/name,data)
                    os.chmod(work/name,next(e['mode'] for e in package['entries'] if e['path']==name))
                ticket={'id':id_,'attempt_id':attempt,'protocol_id':protocol['id'],'case_id':case.id,'arm':arm,
                        'status':'prepared','package':package,'workdir':str(work.resolve()),'request_sha256':store.artifact(case.input_files['TASK.txt']),
                        'model':identity['model'],'provider':identity['provider'],'effort':identity['effort'],'created_at':now(),
                        'money':None,'tokens':None}
                store.put('task_family_attempts',ticket);tickets.append(id_)
        row={'id':protocol['id'],'protocol_sha256':digest(canonical(protocol)),'attempt_id':attempt,'trial_ids':tickets,
             'claims':claims,'status':'prepared','readiness':'configured','created_at':now()}
        store.put('task_family_runs',row)
        return cls(store,protocol['id'])

    def dispatch(self,trial_id,admission,child_id,root_id):
        row=self.store.get('task_family_attempts',trial_id);protocol=self.store.get('protocols',self.protocol_id)
        if not row or row['protocol_id']!=self.protocol_id:raise EvaluationHold('TASK_TRIAL_NOT_FOUND')
        if row['status']!='prepared':raise EvaluationHold('TASK_ATTEMPT_READBACK_REQUIRED')
        if admission.get('ok') is not True or (admission.get('provider'),admission.get('model'),admission.get('reasoning_effort'))!=(row['provider'],row['model'],row['effort']):raise EvaluationHold('TASK_ADMISSION_MISMATCH')
        if admission.get('fork_context') is not False or admission.get('compatibility_contract_sha256')!=protocol['execution_identity']['tool_contract_sha256']:raise EvaluationHold('TASK_TOOL_CONTEXT_CONTRACT_DRIFT')
        if not admission.get('lease_id') or not child_id or not root_id:raise EvaluationHold('TASK_NATIVE_BINDING_REQUIRED')
        row.update(status='dispatched',lease_id=admission['lease_id'],child_id=child_id,root_id=root_id,admission_sha256=self.store.artifact(canonical(admission)),dispatched_at=now())
        row['ticket_sha256']=_ticket_binding(row)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if self.store.get('task_family_attempts',trial_id,db).get('status')!='prepared':raise EvaluationHold('TASK_ATTEMPT_READBACK_REQUIRED')
            if db.execute("SELECT 1 FROM entities WHERE kind='task_family_attempts' AND (json_extract(data,'$.child_id')=? OR json_extract(data,'$.lease_id')=?)",(child_id,admission['lease_id'])).fetchone():raise EvaluationHold('TASK_CONTEXT_REUSED')
            self.store.put('task_family_attempts',row,db)
        run=self.store.get('task_family_runs',self.protocol_id);run.update(readiness='executable',status='running');self.store.put('task_family_runs',run)
        return row

    def collect(self,trial_id,transcript,oracle,execution_evidence=None):
        from .transcripts import _identity
        row=self.store.get('task_family_attempts',trial_id)
        if not row or row.get('protocol_id')!=self.protocol_id:raise EvaluationHold('TASK_TRIAL_NOT_FOUND')
        if row['status']!='dispatched':raise EvaluationHold('TASK_ATTEMPT_READBACK_REQUIRED')
        protocol=self.store.get('protocols',self.protocol_id)
        if oracle.sha256!=protocol['oracle_sha256']:raise EvaluationHold('ORACLE_DRIFT')
        identity=_identity(self.store,transcript,'codex-subagent',expected_session_id=row['child_id'])
        if identity['execution_session_id']!=row['child_id'] or identity['parent_session_id']!=row['root_id']:raise EvaluationHold('TASK_CONTEXT_BINDING_DRIFT')
        trace,calls,outputs,usage,born,elapsed=_read_native_trace(transcript,row,protocol,identity)
        work=Path(row['workdir']);artifacts={}
        for name in protocol['execution_identity'].get('output_files',['result.json']):
            path=work/name
            if path.is_symlink() or any(p.is_symlink() for p in path.parents) or not path.is_file() or path.stat().st_size>2*1024*1024:raise EvaluationHold('TASK_OUTPUT_NOT_REGULAR')
            artifacts[name]=path.read_bytes()
        try:
            actual=snapshot_package(self.store,work)
            expected_names={e['path'] for e in row['package']['entries']}
            if set(e['path'] for e in actual['entries'])-expected_names-set(artifacts):raise ValueError('UNEXPECTED_INPUT')
            entries=[e for e in actual['entries'] if e['path'] in expected_names]
            if entries!=row['package']['entries']:raise ValueError('INPUT_DRIFT')
        except (ValueError,OSError) as ex:raise EvaluationHold('TASK_INPUT_CHANGED:'+str(ex)) from ex
        trace_hash=self.store.artifact(canonical(trace))
        _verify_execution_evidence(self.store,row,protocol,execution_evidence,trace_hash,calls,outputs,artifacts)
        receipt={'status':'completed','exit_code':0,'context_id':row['child_id'],'fresh_context':True,
                 'context_created_at':born.isoformat(),'prepared_at':row['created_at'],
                 'execution_identity':protocol['execution_identity'],'trace_sha256':trace_hash,
                 'execution_evidence_sha256':self.store.artifact(canonical(execution_evidence)),
                 'domain_operation_source':'independent trusted owner, bound to paired native tool results',
                 'tool_calls':len(calls),'tool_results':len(outputs),'wall_seconds':elapsed,
                 'input_manifest_sha256':row['package']['package_digest'],'input_manifest':row['package'],'created_at':now()}
        # Native usage is authoritative for token components, absent money stays
        # unknown. Cached input remains part of input, never a third token sum.
        cost={'money':None,'currency':None,'tokens':None,'input_tokens':None,'output_tokens':None,'cached_input_tokens':None}
        if usage:
            cost.update(input_tokens=usage.get('input_tokens'),output_tokens=usage.get('output_tokens'),cached_input_tokens=usage.get('cached_input_tokens'),tokens=usage.get('total_tokens'))
        row.update(status='completed',receipt=receipt,cost=cost,artifacts={n:self.store.artifact(b) for n,b in artifacts.items()},
                   passed=bool(oracle.grade(row['case_id'],artifacts,receipt)),finished_at=now())
        self.store.put('task_family_attempts',row)
        return row

    def result(self):
        run=self.store.get('task_family_runs',self.protocol_id);p=self.store.get('protocols',self.protocol_id)
        if not run or not p:raise EvaluationHold('TASK_FAMILY_NOT_FOUND')
        if run.get('evaluation_id'):return self.store.get('evaluations',run['evaluation_id'])
        rows=[self.store.get('task_family_attempts',id_) for id_ in run['trial_ids']]
        if any(r['status']!='completed' for r in rows):raise EvaluationHold('TASK_FAMILY_READBACK_REQUIRED')
        trials=[]
        for r in rows:
            t={k:r[k] for k in ('case_id','arm','passed','receipt','artifacts','cost')};t['trial_id']=r['id'];t['receipt_artifact']=self.store.artifact(canonical(t));trials.append(t)
        cases=[c for c in p['cases'] if c['split']=='final'];diffs=[]
        for c in cases:
            pair={r['arm']:r for r in rows if r['case_id']==c['id']}
            if set(pair)!={'parent','candidate'}:raise EvaluationHold('FINAL_CASE_ARM_COVERAGE_MISMATCH')
            diffs.append(int(pair['candidate']['passed'])-int(pair['parent']['passed']))
        gain=sum(diffs)/len(diffs);lower=gain-math.sqrt(2*math.log(1/p['alpha'])/len(diffs))
        missing=['DOMAIN_GUARDRAIL_RECEIPT_REQUIRED','COST_COVERAGE_REQUIRED']
        if p.get('final_exposed'):missing.append('FINAL_SET_EXPOSED')
        if lower<=p['min_gain']:missing.append('NO_CONFIRMED_GAIN')
        if len(cases)<p['minimum_cases']:missing.append('INSUFFICIENT_INDEPENDENT_CASES')
        time_limit=p['execution_identity'].get('budget',{}).get('max_wall_per_arm_seconds')
        if type(time_limit) in {int,float} and any((r.get('receipt') or {}).get('wall_seconds') is not None and r['receipt']['wall_seconds']>time_limit for r in rows):missing.append('TASK_TIME_BUDGET_EXCEEDED')
        tokens=[r.get('cost',{}).get('tokens') for r in rows]
        limit=(p.get('cost_limits') or {}).get('tokens')
        if all(type(x) is int for x in tokens) and type(limit) in {int,float} and sum(tokens)>limit:missing.append('COST_BUDGET_EXCEEDED')
        result={'schema_version':2,'id':'eval_'+secrets.token_hex(12),'protocol_id':p['id'],'protocol_sha256':digest(canonical(p)),
                'attempt_id':run['attempt_id'],'status':'hold','missing':missing,'trials':trials,'paired_cases':len(diffs),
                'paired_gain':gain,'paired_gain_lower_bound':lower,'wall_seconds':None,'created_at':now()}
        self.store.put('evaluations',result)
        attempt=self.store.get('evaluation_attempts',run['attempt_id']);attempt.update(status='completed_hold',result_sha256=self.store.artifact(canonical(result)),money=None,tokens=None,finished_at=now());self.store.put('evaluation_attempts',attempt)
        run.update(status='completed_hold',readiness='exercised',evaluation_id=result['id'],completed_at=now());self.store.put('task_family_runs',run)
        return result


def _ticket_binding(row):
    return digest(canonical({k:row[k] for k in ('id','protocol_id','case_id','arm','package','workdir','request_sha256','created_at','model','provider','effort')}))


def seal_native_execution(store,value):
    """Independent local execution owner only; never exposed as a signing CLI.

    The owner reviews actual input reads, domain operations and artifact writes.
    Signing does not replace the driver's own time/workspace/trace/hash checks.
    """
    import hmac
    from .installations import key
    value=dict(value);value.pop('signature',None)
    return {**value,'signature':hmac.new(key(store),b'native-family-execution-v1\0'+canonical(value),'sha256').hexdigest()}


def _stamp(value):
    from datetime import datetime
    try:
        dt=datetime.fromisoformat(value.replace('Z','+00:00'))
        if dt.tzinfo is None:raise ValueError()
        return dt
    except (ValueError,TypeError,AttributeError):raise EvaluationHold('TASK_TRACE_TIME_INVALID')


def _read_native_trace(path,row,protocol,identity):
    trace=[];contexts=[];usage=None;calls={};outputs={};active=None;terminal=False;previous=None;born=None
    expected_cwd=Path(protocol['execution_identity'].get('context_cwd',row['workdir'])).resolve()
    if Path(identity['cwd']).resolve()!=expected_cwd:raise EvaluationHold('TASK_CONTEXT_WORKSPACE_DRIFT')
    before=Path(path).stat();total=0
    with Path(path).open('rb') as file:
        while line:=file.readline(2*1024*1024+1):
            total+=len(line)
            if len(line)>2*1024*1024 or total>64*1024*1024 or len(trace)>=65536 or not line.endswith(b'\n'):raise EvaluationHold('TASK_TRACE_INCOMPLETE')
            o=json.loads(line);p=o.get('payload',{});stamp=_stamp(o.get('timestamp'))
            if previous and stamp<previous:raise EvaluationHold('TASK_TRACE_TIME_INVALID')
            previous=stamp
            if not trace:
                if o.get('type')!='session_meta':raise EvaluationHold('TASK_CONTEXT_CREATION_REQUIRED')
                born=stamp
                if born<_stamp(row['created_at']) or born>_stamp(now()):raise EvaluationHold('TASK_STALE_CONTEXT')
            elif o.get('type')=='session_meta':raise EvaluationHold('TASK_CONTEXT_REUSED')
            if o.get('type')=='turn_context':
                contexts.append(p)
                if Path(p.get('cwd','')).resolve()!=expected_cwd:raise EvaluationHold('TASK_CONTEXT_WORKSPACE_DRIFT')
                if p.get('turn_id') and p['turn_id']!=active:active=p['turn_id'];terminal=False
            if o.get('type')=='event_msg':
                kind=p.get('type')
                if kind=='task_started':active=p.get('turn_id');terminal=False
                elif kind in {'task_complete','turn_aborted','task_interrupted'}:
                    if p.get('turn_id') and active and p['turn_id']!=active:raise EvaluationHold('TASK_TERMINAL_BINDING_DRIFT')
                    terminal=kind=='task_complete'
                elif kind=='token_count':usage=(p.get('info') or {}).get('total_token_usage') or usage
            if o.get('type')=='response_item':
                kind=p.get('type');cid=p.get('call_id')
                if kind in {'function_call','custom_tool_call'}:
                    if not cid or cid in calls:raise EvaluationHold('TASK_TOOL_PAIRING_INVALID')
                    calls[cid]=p;terminal=False
                elif kind in {'function_call_output','custom_tool_call_output'}:
                    if cid not in calls or cid in outputs:raise EvaluationHold('TASK_TOOL_PAIRING_INVALID')
                    outputs[cid]=p
            trace.append(o)
    after=Path(path).stat()
    if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns):raise EvaluationHold('TASK_TRACE_CHANGED')
    if not terminal:raise EvaluationHold('TASK_TERMINAL_READBACK_REQUIRED')
    if not contexts or any(p.get('model')!=protocol['execution_identity']['transcript_model'] or p.get('effort')!=row['effort'] for p in contexts):raise EvaluationHold('TASK_MODEL_EFFORT_DRIFT')
    if not calls or set(calls)!=set(outputs):raise EvaluationHold('TASK_TOOL_PAIRING_INVALID')
    return trace,calls,outputs,usage,born,(previous-born).total_seconds()


def _tool_result(payload):
    """Read actual native result envelopes, not an exit string in task prose."""
    import re
    texts=[];codes=[]
    def visit(v):
        if isinstance(v,str):
            texts.append(v)
            try:obj=json.loads(v)
            except ValueError:
                match=re.search(r'^Process exited with code (-?\d+)\s*$',v,re.M)
                if match:codes.append(int(match[1]))
            else:
                if isinstance(obj,(dict,list)):visit(obj)
        elif isinstance(v,list):
            for part in v:visit(part)
        elif isinstance(v,dict):
            for k in ('exit_code','exitCode'):
                if type(v.get(k)) is int:codes.append(v[k])
            for k in ('text','output','content'):
                if k in v:
                    # Output bodies are text; their contents cannot override a
                    # real enclosing process exit status.
                    if codes and isinstance(v[k],str):texts.append(v[k])
                    else:visit(v[k])
    visit(payload.get('output',payload.get('content')))
    return texts,codes


def _verify_execution_evidence(store,row,protocol,value,trace_hash,calls,outputs,artifacts):
    import hmac
    if not isinstance(value,dict):raise EvaluationHold('TASK_DOMAIN_EXECUTION_REQUIRED')
    signature=value.get('signature','');expected=seal_native_execution(store,value)['signature']
    if not isinstance(signature,str) or not hmac.compare_digest(signature,expected):raise EvaluationHold('TASK_EXECUTION_EVIDENCE_UNTRUSTED')
    required={'trial_id':row['id'],'child_id':row['child_id'],'ticket_sha256':_ticket_binding(row),
              'admission_sha256':row['admission_sha256'],'trace_sha256':trace_hash,
              'workdir':row['workdir'],'package_digest':row['package']['package_digest'],
              'runtime_sha256':protocol['execution_identity']['runtime_sha256'],
              'tool_contract_sha256':protocol['execution_identity']['tool_contract_sha256']}
    if any(value.get(k)!=v for k,v in required.items()):raise EvaluationHold('TASK_EXECUTION_EVIDENCE_DRIFT')
    reads=value.get('input_read_calls',{});files=read_package(store,row['package'])
    required_reads=protocol['execution_identity'].get('required_read_files',['SKILL.md','TASK.txt'])
    if not isinstance(required_reads,list) or not {'SKILL.md','TASK.txt'}<=set(required_reads):raise EvaluationHold('TASK_INPUT_LOAD_REQUIRED')
    for name in required_reads:
        cid=reads.get(name)
        if name not in files or cid not in outputs:raise EvaluationHold('TASK_INPUT_LOAD_REQUIRED')
        texts,codes=_tool_result(outputs[cid])
        try:content=files[name].decode()
        except UnicodeDecodeError:raise EvaluationHold('TASK_INPUT_LOAD_REQUIRED')
        if not content or not any(content in text for text in texts) or (codes and any(x!=0 for x in codes)):raise EvaluationHold('TASK_INPUT_LOAD_REQUIRED')
    domain=value.get('domain_call_ids')
    if not isinstance(domain,list) or not domain or len(set(domain))!=len(domain):raise EvaluationHold('TASK_DOMAIN_EXECUTION_REQUIRED')
    for cid in domain:
        if cid not in calls or cid not in outputs:raise EvaluationHold('TASK_DOMAIN_EXECUTION_REQUIRED')
        _,codes=_tool_result(outputs[cid])
        if not codes or any(x!=0 for x in codes):raise EvaluationHold('TASK_DOMAIN_EXECUTION_FAILED')
    bindings=value.get('artifact_calls',{})
    if set(bindings)!=set(artifacts):raise EvaluationHold('TASK_ARTIFACT_EXECUTION_BINDING_REQUIRED')
    for name,binding in bindings.items():
        cid=binding.get('call_id')
        if cid not in domain or binding.get('sha256')!=digest(artifacts[name]):raise EvaluationHold('TASK_ARTIFACT_EXECUTION_BINDING_REQUIRED')


def parser_contract(source):
    """Extract the original CLI's argparse-only prefix, never its mutations."""
    import ast
    tree=ast.parse(source)
    function=next((x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='main'),None)
    if function is None:raise EvaluationHold('ORIGINAL_CLI_PARSER_REQUIRED')
    body=[];found=False
    for node in function.body:
        if isinstance(node,ast.Try):break
        body.append(node)
        if isinstance(node,ast.Assign) and isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Attribute) and node.value.func.attr=='parse_args':
            found=True;break
    if not found:raise EvaluationHold('ORIGINAL_CLI_PARSER_REQUIRED')
    constants=[x for x in tree.body if isinstance(x,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='WORK_PROFILES' for t in x.targets)]
    ret=ast.parse('return vars(a)').body[0]
    fun=ast.FunctionDef(name='parse_contract',args=ast.arguments(posonlyargs=[],args=[ast.arg(arg='argv')],kwonlyargs=[],kw_defaults=[],defaults=[]),body=body+[ret],decorator_list=[])
    module=ast.fix_missing_locations(ast.Module(body=constants+[fun],type_ignores=[]))
    text=ast.unparse(module)
    _safe_parser(text)
    return text


def _safe_parser(source):
    import ast,argparse
    tree=ast.parse(source)
    allowed={'ArgumentParser','add_argument','add_subparsers','add_parser','parse_args'}
    for node in ast.walk(tree):
        if isinstance(node,(ast.Import,ast.ImportFrom,ast.Global,ast.Nonlocal,ast.With,ast.AsyncFunctionDef,ast.ClassDef,ast.While,ast.Lambda)):
            raise EvaluationHold('ORACLE_PARSER_CODE_REJECTED')
        if isinstance(node,ast.Attribute) and node.attr not in allowed:raise EvaluationHold('ORACLE_PARSER_CODE_REJECTED')
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id not in {'range','vars','Path','str','int','float'}:raise EvaluationHold('ORACLE_PARSER_CODE_REJECTED')
    namespace={'__builtins__':{'range':range,'vars':vars,'str':str,'int':int,'float':float},'__doc__':'Original CLI parse-only contract','argparse':argparse,'Path':Path}
    exec(compile(tree,'<frozen-argparse-contract>','exec'),namespace)
    return namespace['parse_contract']


class ArgparseTaskOracle:
    """Independent deterministic oracle over actual original CLI parse semantics."""
    def __init__(self,store,source,cases):
        self.store=store;self.parse=_safe_parser(source)
        self.descriptor={'kind':'argparse-cli-v1','schema_version':2,'oracle_code_sha256':digest(Path(__file__).read_bytes()),'parser_sha256':store.artifact(source.encode()),'cases':cases}
        self.sha256=store.artifact(canonical(self.descriptor))

    @classmethod
    def from_descriptor(cls,store,descriptor):
        if descriptor.get('schema_version')!=2 or descriptor.get('oracle_code_sha256')!=digest(Path(__file__).read_bytes()):raise EvaluationHold('ORACLE_CODE_DRIFT')
        return cls(store,store.read_artifact(descriptor['parser_sha256']).decode(),descriptor['cases'])

    def grade(self,case_id,artifacts,receipt):
        import contextlib,io
        if receipt.get('exit_code')!=0 or set(artifacts)!={'result.json'}:return False
        try:
            value=json.loads(artifacts['result.json']);expected=self.descriptor['cases'][case_id]
            if set(value)!={'argv'} or not isinstance(value['argv'],list) or not all(isinstance(x,str) for x in value['argv']):return False
            argv=value['argv']
            if argv[:2]!=['model-dispatch','subagents']:return False
            with contextlib.redirect_stderr(io.StringIO()):parsed=self.parse(argv[2:])
            return all(set(v)<=set(parsed.get('evidence') or []) if k=='evidence_required' else parsed.get(k)==v for k,v in expected.items())
        except (ValueError,KeyError,TypeError,SystemExit):return False
