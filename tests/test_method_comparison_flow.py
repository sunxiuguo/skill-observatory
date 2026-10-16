"""Finite real subprocess lineage; trusted kernel fixtures are not RSI proof."""
import json
import subprocess
import sys
import time
from pathlib import Path
import pytest
from skill_observatory.store import Store,canonical,digest,now
from skill_observatory.evaluation import Case,Environment,FixedArtifactOracle,freeze_protocol
from skill_observatory.installations import seal_verdict
from skill_observatory.outcomes import (register_method_version,preregister_method_comparison,
    method_comparison_design,bind_generation,bind_method_comparison)
from test_final_reconciliation import prepared,verdict as compile_fixture_final


def real_order_fixture(tmp_path):
    s=Store(tmp_path/'state')
    previous_text=b'Generate the baseline script printing baseline.'
    next_text=b'Generate the next script printing next.'
    acceptance_protocol={'id':'method-acceptance-fixture','synthetic':False}
    s.put('protocols',acceptance_protocol)
    methods=[]
    for name,text,parent in [('previous',previous_text,None),('next',next_text,'previous')]:
        content=s.artifact(text)
        # Explicit trusted-kernel fixture acceptance, no independent gain claim.
        acceptance={'id':'accept-'+name,'status':'accepted','candidate_sha256':content,'protocol_id':acceptance_protocol['id'],'protocol_sha256':digest(canonical(acceptance_protocol)),
            'gates':{g:True for g in ('authorization_matches','hashes_current','comparable','independent_final','coverage_sufficient','gain_pass','guardrails_pass','regressions_pass','budget_pass')}}
        s.put('verdicts',seal_verdict(s,acceptance))
        methods.append(register_method_version(s,{'id':name,'content_sha256':content,'parent_version_id':parent,
            'mutable_surface':['proposer'],'authority_evidence_sha256':s.artifact(b'synthetic method fixture authority'),
            'acceptance_verdict_id':acceptance['id']}))
    # Eight frozen, explicitly synthetic kernel fixtures; these labels are
    # independent of the later unknown generation bytes, not domain RSI truth.
    cases=[Case(str(i),{'case':str(i).encode()},'real_incident','final',s.artifact(('provenance '+str(i)).encode()),('regression','guardrail')) for i in range(8)]
    for case in cases:
        for data in case.input_files.values():s.artifact(data)
    oracle=FixedArtifactOracle({str(i):{'result':str(i).encode()} for i in range(8)});s.artifact(canonical(oracle.descriptor))
    env=Environment('python@sha256:'+'a'*64)
    def protocol(parent,candidate):return freeze_protocol(parent,candidate,cases,oracle,env,'fixture','fixture',entrypoint='task.py',cost_limits={'money':10,'tokens':1000,'wall_seconds':100},cost_accounting={'currency':'USD','wall_basis':'sum_duration'})
    # Only knowable design is frozen here: no output file or output digest yet.
    template=protocol({'task.py':b'placeholder'},{'task.py':b'placeholder'})
    input_capsule=s.artifact(b'common authorized synthetic input')
    identity={'kind':'deterministic-python','model':'deterministic-python','effort':'none','harness':'fresh-python-subprocess','runtime_sha256':digest(Path(sys.executable).read_bytes())}
    plan=preregister_method_comparison(s,{'id':'design','method_version_id':'next','previous_method_version_id':'previous',
        'input_capsule_sha256':input_capsule,'generation_identity':identity,'generation_budget':{'money':0,'tokens':0,'wall_seconds':30,'currency':'USD'},'downstream_design':method_comparison_design(template)})
    artifacts=[];generations=[]
    for method in methods:
        work=tmp_path/method['id'];work.mkdir();(work/'METHOD.txt').write_bytes(s.read_artifact(method['content_sha256']))
        started=now();clock=time.monotonic()
        # Actual subprocess reads the actual method bytes and produces previously
        # unknown code + manifest. All timestamps come from execution, no sleeps
        # or prewritten candidate result/historical timestamp manipulation.
        script="""from pathlib import Path
import hashlib,json,uuid
text=Path('METHOD.txt').read_text()
code=('print('+repr(text)+')\\n# '+uuid.uuid4().hex).encode()
Path('SKILL.md').write_bytes(code)
manifest=json.dumps({'SKILL.md':hashlib.sha256(code).hexdigest()},sort_keys=True,separators=(',',':')).encode()
Path('package.json').write_bytes(manifest)
print(text)
print(hashlib.sha256(manifest).hexdigest())
"""
        r=subprocess.run([sys.executable,'-I','-c',script],cwd=work,capture_output=True,text=True,check=True)
        elapsed=time.monotonic()-clock;code=(work/'SKILL.md').read_bytes();artifact=s.artifact(code);artifacts.append({'SKILL.md':code,'task.py':b'pass'})
        trace=[{'timestamp':started,'type':'response_item','payload':{'type':'function_call','name':'exec_command','call_id':method['id'],'arguments':json.dumps({'cmd':'python3 generation fixture','workdir':str(work)})}},
               {'timestamp':now(),'type':'response_item','payload':{'type':'function_call_output','call_id':method['id'],'output':json.dumps({'exit_code':r.returncode,'output':r.stdout})}}]
        th=s.artifact(canonical(trace));source={'id':'exec-'+method['id'],'status':'completed','artifacts':{'SKILL.md':artifact},
            'receipt':{'trace_sha256':th,'tool_results':1,'created_at':now(),'execution_identity':identity,'wall_seconds':elapsed},'cost':{'money':0,'tokens':0,'input_tokens':0,'output_tokens':0,'cached_input_tokens':0,'currency':'USD'}}
        s.put('broker_attempts',source)
        gp=s.artifact(b'synthetic deterministic generation policy, separate from downstream final')
        attempt={'id':'generation-'+method['id'],'status':'completed','method_version_id':method['id'],'comparison_plan_id':plan['id'],'execution_identity':identity,
            'input_capsule_sha256':input_capsule,'protocol_sha256':gp,'candidate_sha256':artifact,'trace_sha256':th,'started_at':started,
            'source_attempt_ref':{'kind':'broker_attempts','id':source['id'],'sha256':digest(canonical(source))}}
        s.put('generation_attempts',attempt)
        generations.append(bind_generation(s,{'id':'bound-'+method['id'],'method_version_id':method['id'],
            'attempt_ref':{'kind':'generation_attempts','id':attempt['id'],'sha256':digest(canonical(attempt))},
            'input_capsule_sha256':input_capsule,'protocol_sha256':gp,'candidate_sha256':artifact,'trace_sha256':th}))
    for arm in artifacts:
        for data in arm.values():s.artifact(data)
    _,c,downstream,e,d,cost=prepared(tmp_path/'kernel',store=s,parent_bytes=artifacts[0]['SKILL.md'],candidate_bytes=artifacts[1]['SKILL.md'],protocol_transform=lambda _:protocol(*artifacts))
    verdict=compile_fixture_final(s,d,cost);assert verdict['status']=='accepted',verdict['missing']
    value={'id':'comparison','plan_id':plan['id'],'method_version_id':'next','previous_method_version_id':'previous',
        'baseline_generation_id':generations[0]['id'],'next_generation_id':generations[1]['id'],'verdict_id':verdict['id']}
    return s,plan,generations,downstream,value


def test_preregister_then_real_read_generate_then_bind_outputs_and_compare(tmp_path):
    s,plan,generations,p,value=real_order_fixture(tmp_path)
    for g in generations:
        a=s.get('generation_attempts',g['attempt_ref']['id'])
        assert plan['created_at']<a['started_at']<=g['created_at']<=p['created_at']
    assert bind_method_comparison(s,value)['status']=='independent_downstream_verified'
    # This asserts the engineering ingress/order only. The fixture verifier
    # acceptance above is not a real downstream domain evaluation or RSI gain.


def test_changed_design_or_missing_preregistration_cannot_use_generated_outputs(tmp_path):
    s,plan,generations,p,value=real_order_fixture(tmp_path)
    with pytest.raises(ValueError,match='DESIGN_DRIFT'):bind_method_comparison(s,{**value,'plan_id':'unknown'})
    changed={**p,'budget_seconds':p['budget_seconds']+1};s.put('protocols',changed)
    v=s.get('verdicts',value['verdict_id']);s.put('verdicts',seal_verdict(s,{**v,'protocol_sha256':digest(canonical(changed))}))
    with pytest.raises(ValueError,match='DESIGN_DRIFT'):bind_method_comparison(s,value)
