"""Real container runner and frozen paired final gate. No model-generated scores."""
from __future__ import annotations
import hashlib
import base64
import json
import math
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from .store import canonical, digest, now
from .packages import execution_manifest,validate_execution_manifest,trial_manifest

RUNNER_SHA256=digest(Path(__file__).read_bytes())


class EvaluationHold(ValueError):pass


@dataclass(frozen=True)
class Environment:
    image_digest: str
    timeout: int = 30
    memory: str = '256m'
    cpus: float = 1.0

    def validate(self):
        import re
        if not re.fullmatch(r'[A-Za-z0-9./_-]+@sha256:[a-f0-9]{64}',self.image_digest):raise EvaluationHold('IMMUTABLE_IMAGE_REQUIRED')
        if not 1<=self.timeout<=300 or not .1<=self.cpus<=2 or self.memory not in {'128m','256m','512m','1g'}:raise EvaluationHold('RESOURCE_LIMIT_INVALID')


class DockerSandbox:
    def __init__(self,environment:Environment):
        environment.validate();self.environment=environment;self.id=None;self.receipt={}
    def _docker(self,*args,timeout=20,check=True,input=None):
        try:
            r=subprocess.run(['docker',*args],capture_output=True,timeout=timeout,input=input)
        except (OSError,subprocess.TimeoutExpired) as e:raise EvaluationHold('DOCKER_UNAVAILABLE_OR_TIMEOUT') from e
        if check and r.returncode:raise EvaluationHold('DOCKER_OPERATION_FAILED:'+args[0])
        return r
    def prepare(self,files:dict[str,bytes],manifest=None):
        if self.id:raise EvaluationHold('SANDBOX_ALREADY_PREPARED')
        manifest=manifest or execution_manifest(files)
        validate_execution_manifest(files,manifest)
        e=self.environment
        # Never accept extra Docker arguments, mounts, devices, env or network from a candidate.
        r=self._docker('create','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
          '--user','1000:1000','--pids-limit','64','--memory',e.memory,'--cpus',str(e.cpus),
          '--tmpfs','/work:rw,noexec,nosuid,size=32m,uid=1000,gid=1000',
          '--tmpfs','/out:rw,noexec,nosuid,size=16m,uid=1000,gid=1000',
          '--tmpfs','/tmp:rw,noexec,nosuid,size=16m,uid=1000,gid=1000',
          '--workdir','/work',e.image_digest,'python','-c',f'import time; time.sleep({e.timeout+45})')
        self.id=r.stdout.decode().strip();self._docker('start',self.id)
        try:
            encoded={}
            for name,b in files.items():
                p=Path(name)
                if p.is_absolute() or '..' in p.parts or not p.parts or len(b)>8_000_000:raise EvaluationHold('INPUT_PATH_OR_SIZE_INVALID')
                encoded[name]={'bytes':base64.b64encode(b).decode(),'mode':next(e['mode'] for e in manifest['entries'] if e['path']==name)}
            # Docker archive copy cannot reliably target tmpfs under read-only root.
            # A fixed broker writes validated file bytes as the unprivileged user.
            loader="import sys,json,base64,os,hashlib,stat;from pathlib import Path\nentries=[]\nfor n,v in json.load(sys.stdin).items():\n p=Path('/work')/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(base64.b64decode(v['bytes']));os.chmod(p,v['mode']);data=p.read_bytes();entries.append({'path':n,'type':'file','sha256':hashlib.sha256(data).hexdigest(),'size':len(data),'mode':stat.S_IMODE(p.stat().st_mode)})\nprint(json.dumps({'schema_version':2,'entries':sorted(entries,key=lambda e:e['path'])},sort_keys=True,separators=(',',':')))"
            loaded=json.loads(self._docker('exec','-i',self.id,'python','-I','-B','-c',loader,input=canonical(encoded)).stdout)
            if loaded!={k:v for k,v in manifest.items() if k!='package_digest'}:raise EvaluationHold('INPUT_MODE_READBACK_FAILED')
            inspect=json.loads(self._docker('inspect',self.id).stdout)[0]
            h=inspect['HostConfig']
            if h['NetworkMode']!='none' or not h['ReadonlyRootfs'] or h['Privileged'] or h.get('Binds'):raise EvaluationHold('ISOLATION_READBACK_FAILED')
            self.receipt={'container_id':self.id,'image_digest':e.image_digest,'network':'none','root_readonly':True,'user':inspect['Config']['User'],'host_mounts':h.get('Binds') or [],'created_at':now(),'profile':'container-clean','input_manifest_sha256':manifest['package_digest'],'input_manifest':manifest}
            return self.receipt
        except BaseException:self.destroy();raise
    def execute(self,entrypoint:str):
        # This is a registered Python task runner, not a raw shell escape hatch.
        p=validated_entrypoint(entrypoint)
        start=time.monotonic()
        try:
            r=self._docker('exec',self.id,'python','-I','-B','/work/'+str(p),timeout=self.environment.timeout,check=False)
            self.receipt.update(exit_code=r.returncode,wall_seconds=time.monotonic()-start,stdout_sha256=digest(r.stdout),stderr_sha256=digest(r.stderr),status='completed')
        except EvaluationHold:
            self.receipt.update(exit_code=None,wall_seconds=time.monotonic()-start,status='timeout',reason_code='ATTEMPT_CONSUMED')
        return dict(self.receipt)
    def collect(self):
        # Export artifact files, never use assistant/log claims as oracle.
        collector="import json,base64;from pathlib import Path\nr={}\nfor p in Path('/out').rglob('*'):\n if p.is_symlink():raise ValueError('OUTPUT_SYMLINK_REJECTED')\n if p.is_file():\n  if p.stat().st_size>8000000:raise ValueError('OUTPUT_TOO_LARGE')\n  r[str(p.relative_to('/out'))]=base64.b64encode(p.read_bytes()).decode()\nprint(json.dumps(r))"
        r=self._docker('exec',self.id,'python','-I','-B','-c',collector)
        return {n:base64.b64decode(b,validate=True) for n,b in json.loads(r.stdout).items()}
    def reset(self):self.destroy()
    def destroy(self):
        if self.id:
            id=self.id;self.id=None;self._docker('rm','-f',id,check=False)


def validated_entrypoint(entrypoint:str):
    p=Path(entrypoint)
    if p.is_absolute() or '..' in p.parts or p.suffix!='.py':raise EvaluationHold('ENTRYPOINT_NOT_AUTHORIZED')
    return p


@dataclass(frozen=True)
class Case:
    id: str
    input_files: dict[str,bytes]
    source: str
    split: str
    evidence_sha256: str
    categories: tuple[str, ...] = ()


class FixedArtifactOracle:
    """Held by the host verifier; labels are not copied to containers."""
    def __init__(self,labels:dict[str,dict[str,bytes]]):
        self._labels=labels
        self.descriptor={k:{n:digest(b) for n,b in v.items()} for k,v in labels.items()}
        self.sha256=digest(canonical(self.descriptor))
    def label_digest(self,case_id):
        if case_id not in self._labels:raise EvaluationHold('LABEL_MISSING')
        return digest(canonical({n:digest(b) for n,b in self._labels[case_id].items()}))
    def grade(self,case_id,artifacts,receipt):
        if case_id not in self._labels:raise EvaluationHold('LABEL_MISSING')
        expected=self._labels[case_id]
        return bool(receipt.get('exit_code')==0 and artifacts==expected)


def freeze_protocol(parent, candidate, cases, oracle, environment, model, max_verified_effort, budget_seconds=300, min_gain=0., alpha=.05, minimum_cases=1, cost_limits=None, entrypoint=None,execution_identity=None,cost_accounting=None,arm_packages=None):
    environment.validate()
    if entrypoint is None:
        runners={k for k in parent.keys() & candidate.keys() if k.endswith('.py')}
        if len(runners)!=1:raise EvaluationHold('FROZEN_ENTRYPOINT_REQUIRED')
        entrypoint=next(iter(runners))
    validated_entrypoint(entrypoint)
    if entrypoint not in parent or entrypoint not in candidate:raise EvaluationHold('FROZEN_ENTRYPOINT_REQUIRED')
    if execution_identity is None:
        execution_identity={'kind':'deterministic-python','model':model,'effort':max_verified_effort,
                            'runner_sha256':RUNNER_SHA256}
    if not model or not max_verified_effort:raise EvaluationHold('EXACT_MODEL_EFFORT_REQUIRED')
    if not 0<alpha<1 or not 0<=min_gain<1 or not math.isfinite(budget_seconds) or budget_seconds<=0 or type(minimum_cases) is not int or minimum_cases<1:raise EvaluationHold('INVALID_PROTOCOL')
    if len(set(c.id for c in cases))!=len(cases):raise EvaluationHold('CASE_ID_COLLISION')
    if cost_limits is not None:
        if set(cost_limits)!={'money','tokens','wall_seconds'} or any(type(v) not in {int,float} or not math.isfinite(v) or v<0 for v in cost_limits.values()):raise EvaluationHold('INVALID_COST_POLICY')
    arm_packages=arm_packages or {'parent':execution_manifest(parent),'candidate':execution_manifest(candidate)}
    if set(arm_packages)!={'parent','candidate'}:raise EvaluationHold('EXECUTION_MANIFEST_REQUIRED')
    for arm,files in [('parent',parent),('candidate',candidate)]:validate_execution_manifest(files,arm_packages[arm])
    return {'schema_version':2,'arm_packages':arm_packages,'cost_accounting':cost_accounting,'id':'proto_'+secrets.token_hex(12),'entrypoint':entrypoint,'execution_identity':execution_identity,'parent_sha256':digest(canonical({k:digest(v) for k,v in parent.items()})),
      'candidate_sha256':digest(canonical({k:digest(v) for k,v in candidate.items()})),
      'arm_files':{'parent':{k:digest(v) for k,v in parent.items()},'candidate':{k:digest(v) for k,v in candidate.items()}},
      'oracle_sha256':oracle.sha256,'environment':environment.__dict__,'model':model,'max_verified_effort':max_verified_effort,
      'cases':[{'id':c.id,'source':c.source,'split':c.split,'evidence_sha256':c.evidence_sha256,'inputs_sha256':digest(canonical({k:digest(v) for k,v in c.input_files.items()})),'input_files':{k:digest(v) for k,v in c.input_files.items()},'categories':list(c.categories)} for c in cases],
      'budget_seconds':budget_seconds,'cost_limits':cost_limits,'min_gain':min_gain,'alpha':alpha,'minimum_cases':minimum_cases,'final_exposed':False,'max_attempts':1,'created_at':now()}


def paired_evaluate(protocol,parent,candidate,cases,oracle,entrypoint,store=None,runner=None):
    """Trusted verifier orchestrates both exact arms; proposer never grades itself."""
    frozen=digest(canonical(protocol));e=Environment(**protocol['environment']);start=time.monotonic();trials=[];missing=[]
    for arm,files in [('parent',parent),('candidate',candidate)]:
        if digest(canonical({k:digest(v) for k,v in files.items()}))!=protocol[arm+'_sha256']:raise EvaluationHold('ARM_HASH_DRIFT')
        trial_manifest(protocol,arm,files,{})
    if oracle.sha256!=protocol['oracle_sha256']:raise EvaluationHold('ORACLE_DRIFT')
    actual=[{'id':c.id,'source':c.source,'split':c.split,'evidence_sha256':c.evidence_sha256,'inputs_sha256':digest(canonical({k:digest(v) for k,v in c.input_files.items()})),'input_files':{k:digest(v) for k,v in c.input_files.items()},'categories':list(c.categories)} for c in cases]
    if actual!=protocol['cases']:raise EvaluationHold('CASE_DRIFT')
    if store:
        from .packages import freeze_package
        for arm,files in [('parent',parent),('candidate',candidate)]:
            manifest=trial_manifest(protocol,arm,files,{})
            freeze_package(store,files,{entry['path']:entry['mode'] for entry in manifest['entries']})
        for case in cases:
            for data in case.input_files.values():store.artifact(data)
    if entrypoint!=protocol.get('entrypoint'):raise EvaluationHold('EXECUTION_IDENTITY_DRIFT')
    execution=protocol.get('execution_identity')
    if runner is not None:
        if execution!=runner.execution_identity:raise EvaluationHold('EXECUTION_IDENTITY_DRIFT')
    elif execution!={'kind':'deterministic-python','model':protocol['model'],'effort':protocol['max_verified_effort'],
                     'runner_sha256':RUNNER_SHA256}:
        raise EvaluationHold('EXECUTION_IDENTITY_DRIFT')
    # Final feedback is consumed once per leakage-equivalence class, not once
    # per set. A consumed final sample is identified by the exact input bytes
    # the arm sees plus that case's own oracle labels: renaming the case,
    # adding or removing sibling cases, switching protocol IDs/candidates, or
    # editing labels of unrelated cases must not launder it into fresh truth.
    # The whole batch claims atomically before any arm executes, or refuses.
    if store and hasattr(oracle,'descriptor'):store.artifact(canonical(oracle.descriptor))
    attempt_id,claims,claim_missing=claim_evaluation(store,protocol,actual)
    missing.extend(claim_missing)
    for case in cases:
        if case.split!='final':continue
        order=['parent','candidate'];secrets.SystemRandom().shuffle(order)
        for arm in order:
            if time.monotonic()-start>=protocol['budget_seconds']:missing.append('BUDGET_EXHAUSTED');break
            files=parent if arm=='parent' else candidate
            if set(files)&set(case.input_files):raise EvaluationHold('CASE_OVERWRITES_SKILL')
            sandbox=None if runner else DockerSandbox(e)
            try:
                if runner:
                    manifest=trial_manifest(protocol,arm,files,case.input_files)
                    if protocol.get('parent_package_digest') or protocol.get('candidate_package_digest'):
                        raise EvaluationHold('FULL_PACKAGE_RUNNER_UNSUPPORTED')
                    execution_result=runner.run_trial(attempt_id+'_'+case.id+'_'+arm,{**files,**case.input_files},entrypoint,e)
                    receipt=execution_result['receipt'];artifacts=execution_result['artifacts']
                    cost=execution_result['cost']
                else:
                    sandbox.prepare({**files,**case.input_files},trial_manifest(protocol,arm,files,case.input_files));receipt=sandbox.execute(entrypoint);artifacts=sandbox.collect()
                    cost={'money':None,'tokens':None}
                passed=oracle.grade(case.id,artifacts,receipt)
                row={'case_id':case.id,'arm':arm,'passed':passed,'receipt':receipt,'artifacts':{k:digest(v) for k,v in artifacts.items()},'cost':cost}
                row.update(trial_id=attempt_id+'_'+case.id+'_'+arm)
                if store:
                    for data in artifacts.values():store.artifact(data)
                    row['receipt_artifact']=store.artifact(canonical(row))
                trials.append(row)
            except EvaluationHold as ex:missing.append(str(ex));trials.append({'case_id':case.id,'arm':arm,'passed':False,'reason_code':str(ex),'cost':{'money':None,'tokens':None}})
            finally:
                if sandbox:sandbox.destroy()
    paired=[]
    for c in cases:
        rows={x['arm']:x for x in trials if x['case_id']==c.id}
        if len(rows)==2:paired.append(int(rows['candidate']['passed'])-int(rows['parent']['passed']))
    n=len(paired);mean=sum(paired)/n if n else None
    lower=mean-math.sqrt(2*math.log(1/protocol['alpha'])/n) if n else None
    if not n or n<protocol['minimum_cases']:missing.append('INSUFFICIENT_INDEPENDENT_CASES')
    if any(c.source not in {'real_incident','real_success','regression','prospective_real','adversarial'} or not c.evidence_sha256 for c in cases):missing.append('REAL_CASE_EVIDENCE_REQUIRED')
    if protocol['final_exposed']:missing.append('FINAL_SET_EXPOSED')
    if protocol.get('entrypoint') is None:missing.append('EXECUTION_IDENTITY_NOT_FROZEN')
    if lower is None or lower<=protocol['min_gain']:missing.append('NO_CONFIRMED_GAIN')
    # Domain guardrail and cost truth are mandatory, not inferred from artifact matches.
    missing+=['DOMAIN_GUARDRAIL_RECEIPT_REQUIRED','COST_COVERAGE_REQUIRED']
    if protocol['model']!='deterministic-python' and not runner:missing.append('MODEL_EXECUTION_RECEIPT_REQUIRED')
    result={'schema_version':2,'id':'eval_'+secrets.token_hex(12),'protocol_id':protocol['id'],'protocol_sha256':frozen,'attempt_id':attempt_id,'status':'hold','reason_code':missing[0] if missing else 'FINAL_GATE_HOLD','missing':sorted(set(missing)),'final_cases':[c['id'] for c in claims],'trials':trials,'paired_cases':n,'paired_gain':mean,'paired_gain_lower_bound':lower,'confidence':1-protocol['alpha'],'method':'Hoeffding paired bound on independent task differences [-1,1]','wall_seconds':time.monotonic()-start,'created_at':now()}
    if store:
        evidence=store.artifact(canonical(result));store.put('evaluations',result)
        store.put('evaluation_attempts',{'id':attempt_id,'protocol_id':protocol['id'],'protocol_sha256':frozen,'final_cases':[c['id'] for c in claims],'status':'completed_hold','result_sha256':evidence,'wall_seconds':result['wall_seconds'],'money':None,'tokens':None,'created_at':now()})
    return result


def claim_evaluation(store,protocol,actual):
    frozen=digest(canonical(protocol));missing=[]
    attempt_id='final_attempt_'+secrets.token_hex(12)
    claims=[]
    if store:
        for c in actual:
            if c['split']!='final':continue
            # Multiple non-replaceable identities close label/provenance washing.
            # The owner can add lineage but cannot replace these byte/source keys.
            for kind,value in [('input',c['inputs_sha256']),('evidence',c['evidence_sha256'])]:
                claims.append({'id':'final_case_'+digest(canonical([kind,value])),'identity_kind':kind,
                    'case_id':c['id'],'inputs_sha256':c['inputs_sha256'],'evidence_sha256':c['evidence_sha256'],'source':c['source']})
        if len({c['id'] for c in claims})!=len(claims):raise EvaluationHold('FINAL_CASE_DUPLICATE')
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            existing=store.get('protocols',protocol['id'],db)
            if existing and digest(canonical(existing))!=frozen:raise EvaluationHold('PROTOCOL_DRIFT')
            # Old set-level records still own their exposed samples. A migration
            # must not erase the historical consumption barrier.
            legacy=[json.loads(x[0]) for x in db.execute("SELECT data FROM entities WHERE kind='final_sets' AND json_extract(data,'$.identity_kind') IS NULL")]
            protocols=[json.loads(x[0]) for x in db.execute("SELECT data FROM entities WHERE kind='protocols'")]
            for consumed in legacy:
                old=next((p for p in protocols if digest(canonical(p))==consumed.get('protocol_sha256')),None)
                if old is None:raise EvaluationHold('LEGACY_FINAL_CONSUMPTION_READBACK_REQUIRED')
                for oldcase in old.get('cases',[]):
                    if oldcase.get('split')=='final' and any(c['split']=='final' and
                        (c['inputs_sha256']==oldcase.get('inputs_sha256') or c['evidence_sha256']==oldcase.get('evidence_sha256')) for c in actual):
                        raise EvaluationHold('FINAL_SET_ALREADY_CONSUMED')
            for claim in claims:
                if store.get('final_sets',claim['id'],db):raise EvaluationHold('FINAL_SET_ALREADY_CONSUMED')
            store.put('protocols',protocol,db)
            for claim in claims:
                store.put('final_sets',{**claim,'attempt_id':attempt_id,'protocol_sha256':frozen,'status':'consumed','created_at':now()},db)
            store.put('evaluation_attempts',{'id':attempt_id,'protocol_id':protocol['id'],'protocol_sha256':frozen,'final_cases':[c['id'] for c in claims],'status':'prepared','created_at':now(),'money':None,'tokens':None},db)
    else:missing.append('DURABLE_ATTEMPT_LEDGER_REQUIRED')
    return attempt_id,claims,missing
