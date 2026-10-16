"""Composition regressions; synthetic engineering fixtures, not outcome gain."""
import copy,json,os
from datetime import datetime,timedelta,timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pytest
from skill_observatory.store import canonical,digest,now
from skill_observatory.evaluation import Environment,DockerSandbox,Case,FixedArtifactOracle,freeze_protocol,paired_evaluate,EvaluationHold
from skill_observatory.packages import execution_manifest
from skill_observatory.final_gate import finalize,seal_owner_receipt
from skill_observatory.outcomes import bind_method_comparison,method_report,cohort_report,record_cohort_sample,seal_task_receipt,accept_task_result
from test_final_reconciliation import prepared,verdict
from test_review_feedback import native_trace,cohort_fixture,natural_sample
from test_method_comparison_flow import real_order_fixture
from test_evaluation import image


@pytest.mark.parametrize('change',['setuid','regular_mode','fifo','directory'])
def test_native_execution_boundary_rejects_full_mode_and_type_drift(tmp_path,change):
    s,d,tid,path,o,proof=native_trace(tmp_path);work=Path(s.get('task_family_attempts',tid)['workdir']);task=work/'TASK.txt'
    if change=='setuid':task.chmod(0o4644)
    elif change=='regular_mode':task.chmod(0o600)
    elif change=='fifo':task.unlink();os.mkfifo(task)
    else:work.chmod(0o1700)
    with pytest.raises(EvaluationHold,match='TASK_INPUT_CHANGED'):d.collect(tid,path,o,proof)
    assert s.get('task_family_attempts',tid)['status']=='dispatched'


@pytest.mark.parametrize('change',['bytes','symlink','expiry'])
def test_accepted_cache_rechecks_disk_and_natural_authority_expiry(tmp_path,monkeypatch,change):
    s,c,p,e,d,cost=prepared(tmp_path);clock={'value':datetime.now(timezone.utc)}
    if change=='expiry':
        grant=s.get('authority_grants','g');grant['expires_at']=(clock['value']+timedelta(seconds=10)).isoformat();s.put('authority_grants',grant)
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):return clock['value']
        monkeypatch.setattr('skill_observatory.installations.datetime',Clock)
    first=verdict(s,d,cost);assert first['status']=='accepted'
    assert verdict(s,d,cost)==first;consumed=s.list('final_sets')
    target=Path(c['target'])
    if change=='bytes':target.write_bytes(b'other')
    elif change=='symlink':target.unlink();target.symlink_to(tmp_path/'absent')
    else:clock['value']+=timedelta(seconds=20)
    with pytest.raises(ValueError,match='DRIFT_HOLD|OWNER_AUTHORITY_HOLD'):verdict(s,d,cost)
    current=s.get('verdicts',first['id']);assert current['status']=='hold' and 'signature' not in current
    assert json.loads(s.read_artifact(current['previous_verdict_sha256']))==first
    assert s.list('final_sets')==consumed


def test_exact_original_owner_installed_candidate_keeps_historical_final_usable(tmp_path):
    s,c,p,e,d,cost=prepared(tmp_path);first=verdict(s,d,cost);target=Path(c['target'])
    target.write_bytes(s.read_artifact(c['candidate_sha256']))
    s.put('installations',{'id':'owner_inst_c','owner':'skill-evolution-loop','candidate_id':'c','status':'activated','target':str(target),
        'before_sha256':c['parent_sha256'],'after_sha256':c['candidate_sha256'],'applied_at':now()})
    assert verdict(s,d,cost)==first


def packaged_kernel(tmp_path):
    from skill_observatory.packages import freeze_package
    manifests={arm:execution_manifest({'SKILL.md':data}) for arm,data in [('parent',b'parent'),('candidate',b'candidate')]}
    def transform(p):return {**p,'arm_packages':manifests,'parent_package_digest':manifests['parent']['package_digest'],'candidate_package_digest':manifests['candidate']['package_digest']}
    s,c,p,e,d,cost=prepared(tmp_path,protocol_transform=transform)
    owned=tmp_path/'owned';owned.mkdir();(owned/'SKILL.md').write_bytes(b'parent')
    for arm,data in [('parent',b'parent'),('candidate',b'candidate')]:assert freeze_package(s,{'SKILL.md':data})==manifests[arm]
    c.update(target=str(owned),parent_package=manifests['parent'],candidate_package=manifests['candidate']);s.put('candidates',c)
    grant=s.get('authority_grants','g');grant.update(target=str(owned),surface='package',changed_files=['SKILL.md'],parent_package_digest=manifests['parent']['package_digest'],candidate_package_digest=manifests['candidate']['package_digest']);s.put('authority_grants',grant)
    return s,c,p,e,d,cost


def test_package_cached_final_mode_drift_refuses_with_history(tmp_path):
    s,c,p,e,d,cost=packaged_kernel(tmp_path);first=verdict(s,d,cost);assert first['status']=='accepted',first['missing']
    (Path(c['target'])/'SKILL.md').chmod(0o600)
    with pytest.raises(ValueError,match='DRIFT_HOLD'):verdict(s,d,cost)
    assert s.get('verdicts',first['id'])['status']=='hold'


def test_final_rejects_resealed_trial_that_loaded_wrong_full_mode(tmp_path):
    s,c,p,e,d,cost=packaged_kernel(tmp_path)
    trial=e['trials'][0];actual=copy.deepcopy(trial['receipt']['input_manifest']);actual['entries'][0]['mode']=0o600
    actual['package_digest']=digest(canonical({k:v for k,v in actual.items() if k!='package_digest'}))
    trial['receipt'].update(input_manifest=actual,input_manifest_sha256=actual['package_digest'])
    row={k:v for k,v in trial.items() if k!='receipt_artifact'};trial['receipt_artifact']=s.artifact(canonical(row));s.put('evaluations',e)
    eh=s.artifact(canonical(e));attempt=s.get('evaluation_attempts',e['attempt_id']);attempt['result_sha256']=eh;s.put('evaluation_attempts',attempt)
    d.update(evaluation_sha256=eh,trial_receipt_sha256=[t['receipt_artifact'] for t in e['trials']]);cost['evaluation_sha256']=eh;cost['attempt_refs'][0]['sha256']=s.artifact(canonical(attempt))
    result=verdict(s,d,cost);assert result['status']=='hold' and 'TRIAL_INPUT_BINDING_DRIFT' in result['missing']


def sample_input(sample):return {k:sample[k] for k in ('id','cohort_id','arm','task_receipt_id','source_receipt','rework','takeovers','elapsed_seconds','attempt_refs')}


def test_resigned_receipt_parallel_delivery_cannot_increase_natural_denominator(tmp_path):
    s,r,c=cohort_fixture(tmp_path);sample=natural_sample(s,c,r,'one','candidate');task=s.get('task_receipts',sample['task_receipt_id'])
    duplicate={k:v for k,v in task.items() if k!='signature'};duplicate['id']='resigned';accept_task_result(s,seal_task_receipt(s,duplicate))
    def submit(n):
        try:record_cohort_sample(s,{**sample_input(sample),'id':'duplicate-'+str(n),'task_receipt_id':'resigned'});return 'accepted'
        except ValueError as ex:return str(ex)
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(submit,[1,2]))
    assert all('DUPLICATE_LOGICAL_TASK' in x for x in results)
    report=cohort_report(s,c['id'])['arms']['candidate']
    assert report['observed']==report['independent_observed']==1 and report['money']==1.5 and report['tokens']==10


def test_same_context_distinct_turns_and_arms_count_but_retry_is_not_independent(tmp_path):
    s,r,c=cohort_fixture(tmp_path)
    natural_sample(s,c,r,'parent','parent',session_id='shared',turn_id='parent-turn')
    natural_sample(s,c,r,'one','candidate',session_id='shared',turn_id='one-turn',logical_task_id='one-task')
    natural_sample(s,c,r,'two','candidate',session_id='shared',turn_id='two-turn')
    assert cohort_report(s,c['id'])['arms']['candidate']['missing']==[]
    with pytest.raises(ValueError,match='DUPLICATE_LOGICAL_TASK'):
        natural_sample(s,c,r,'retry','candidate',session_id='shared',turn_id='retry-turn',logical_task_id='one-task')
    # The rejected retry is still an actual signed task/cost in the ledger.
    report=cohort_report(s,c['id'])['arms']['candidate']
    assert report['independent_observed']==2 and report['money'] is None and 'ALL_ATTEMPT_COST_REQUIRED' in report['missing']


def test_legacy_duplicate_history_is_visible_and_never_certifies_cost_or_coverage(tmp_path):
    s,r,c=cohort_fixture(tmp_path);sample=natural_sample(s,c,r,'one','candidate')
    s.put('cohort_samples',{**sample,'id':'retained-legacy-duplicate'})
    report=cohort_report(s,c['id'])['arms']['candidate']
    assert report['observed']==2 and report['independent_observed']==1 and report['duplicate_sample_groups']
    assert report['money'] is None and report['tokens'] is None and report['accepted'] is None
    assert 'DUPLICATE_LOGICAL_NATURAL_TASK' in report['missing'] and 'INCOMPLETE_COHORT_COVERAGE' in report['missing']


def failed_generation(s,plan,id_='failed',status='failed',money=0,tokens=0,plan_id=None):
    row={'id':id_,'status':status,'comparison_plan_id':plan_id or plan['id'],'method_version_id':'next',
         'input_capsule_sha256':plan['input_capsule_sha256'],'cost':{'money':money,'tokens':tokens,'input_tokens':tokens,'output_tokens':0,'cached_input_tokens':0,'currency':'USD','wall_seconds':.01}}
    s.put('generation_attempts',row);return row


@pytest.mark.parametrize('status,money,tokens,reason',[('failed',100,100,'BUDGET_EXCEEDED'),('unknown_after_dispatch',0,0,'READBACK_REQUIRED'),('interrupted',0,0,'READBACK_REQUIRED')])
def test_method_plan_includes_failed_unknown_and_interrupted_exploration(tmp_path,status,money,tokens,reason):
    s,plan,g,p,value=real_order_fixture(tmp_path);failed_generation(s,plan,status=status,money=money,tokens=tokens)
    with pytest.raises(ValueError,match=reason):bind_method_comparison(s,value)
    assert method_report(s,'next')['method_rsi']=='UNVERIFIED'


def test_method_missing_plan_binding_cannot_hide_attempt_under_same_input(tmp_path):
    s,plan,g,p,value=real_order_fixture(tmp_path);row=failed_generation(s,plan);row.pop('comparison_plan_id');s.put('generation_attempts',row)
    with pytest.raises(ValueError,match='METHOD_PLAN_COST_BINDING_REQUIRED'):bind_method_comparison(s,value)


def test_known_zero_cost_failed_retry_and_source_are_charged_once_unrelated_plan_excluded(tmp_path):
    s,plan,g,p,value=real_order_fixture(tmp_path)
    first=failed_generation(s,plan);retry=failed_generation(s,plan,id_='retry')
    retry['retry_of_ref']={'kind':'generation_attempts','id':first['id'],'sha256':digest(canonical(first))};s.put('generation_attempts',retry)
    failed_generation(s,plan,id_='unrelated',money=100,tokens=100,plan_id='other-plan')
    result=bind_method_comparison(s,value)
    ids={r['id'] for r in result['generation_attempt_refs']}
    assert {'failed','retry','exec-next','exec-previous','generation-next','generation-previous'}<=ids and 'unrelated' not in ids
    assert result['generation_costs']['money']==result['generation_costs']['tokens']==0
    assert method_report(s,'next')['method_rsi']=='VERIFIED_BOUNDED_DOWNSTREAM'


def test_method_report_rechecks_real_kernel_cost_revocation_and_preserves_history(tmp_path):
    s,plan,g,p,value=real_order_fixture(tmp_path);comparison=bind_method_comparison(s,value)
    assert method_report(s,'next')['method_rsi']=='VERIFIED_BOUNDED_DOWNSTREAM'
    original=s.get('verdicts',value['verdict_id']);cost=json.loads(s.read_artifact(original['cost_receipt_sha256']));domain=json.loads(s.read_artifact(original['domain_receipt_sha256']))
    s.put('task_family_attempts',{'id':'late-unknown','protocol_id':p['id'],'status':'unknown_after_dispatch','cost':{'money':0,'tokens':0,'currency':'USD','wall_seconds':1}})
    with pytest.raises(ValueError,match='COVERAGE_REQUIRED'):finalize(s,'c','e',domain,cost)
    assert s.get('verdicts',value['verdict_id'])['status']=='hold'
    report=method_report(s,'next');assert report['method_rsi']=='UNVERIFIED' and report['missing']
    assert s.get('method_comparisons',comparison['id'])==comparison and report['comparison_history'][0]['historical_status']=='independent_downstream_verified'


@pytest.mark.parametrize('change',['method','source','new_unknown'])
def test_method_report_current_dependencies_never_reuse_cached_green(tmp_path,change):
    s,plan,g,p,value=real_order_fixture(tmp_path);bind_method_comparison(s,value)
    if change=='method':
        method=s.get('method_versions','next');method['content_sha256']=s.artifact(b'drift');s.put('method_versions',method)
    elif change=='source':
        source=s.get('broker_attempts','exec-next');source['status']='unknown_after_dispatch';s.put('broker_attempts',source)
    else:failed_generation(s,plan,id_='new-unknown',status='unknown_after_dispatch')
    assert method_report(s,'next')['method_rsi']=='UNVERIFIED'


@pytest.mark.parametrize('mode',[0o600,0o700,0o755])
def test_real_container_executes_exact_mode_only_package_difference(image,tmp_path,mode):
    s=__import__('skill_observatory.store',fromlist=['Store']).Store(tmp_path/'state')
    files={'SKILL.md':b'mode fixture','helper.py':b'pass','task.py':b"from pathlib import Path;import stat;Path('/out/mode').write_text(str(stat.S_IMODE(Path('helper.py').stat().st_mode)))"}
    parent=execution_manifest(files);candidate=execution_manifest(files,{'helper.py':mode})
    case=Case('mode',{},'adversarial','final',s.artifact(b'synthetic real container mode fixture'))
    oracle=FixedArtifactOracle({'mode':{'mode':str(mode).encode()}})
    p=freeze_protocol(files,files,[case],oracle,Environment(image),'deterministic-python','none',entrypoint='task.py',arm_packages={'parent':parent,'candidate':candidate})
    p.update(parent_package_digest=parent['package_digest'],candidate_package_digest=candidate['package_digest'])
    result=paired_evaluate(p,files,files,[case],oracle,'task.py',s)
    trials={t['arm']:t for t in result['trials']}
    assert not trials['parent']['passed'] and trials['candidate']['passed']
    for arm,wanted in [('parent',0o644),('candidate',mode)]:
        assert s.read_artifact(trials[arm]['artifacts']['mode'])==str(wanted).encode()
        assert next(e['mode'] for e in trials[arm]['receipt']['input_manifest']['entries'] if e['path']=='helper.py')==wanted
    assert trials['parent']['receipt']['input_manifest_sha256']!=trials['candidate']['receipt']['input_manifest_sha256']
    assert len({t['receipt']['container_id'] for t in trials.values()})==2


def test_loader_missing_or_wrong_mode_manifest_refuses_before_execution():
    files={'task.py':b'pass'};m=execution_manifest(files);bad=copy.deepcopy(m);bad['entries'][0]['mode']=0o600
    sandbox=DockerSandbox(Environment('python@sha256:'+'a'*64))
    with pytest.raises(ValueError,match='MANIFEST_DRIFT'):sandbox.prepare(files,bad)
    assert sandbox.id is None


def test_package_protocol_cannot_fall_back_to_missing_mode_manifest(tmp_path):
    files={'task.py':b'pass'};oracle=FixedArtifactOracle({'one':{}});case=Case('one',{},'adversarial','final','a'*64)
    p=freeze_protocol(files,files,[case],oracle,Environment('python@sha256:'+'a'*64),'deterministic-python','none')
    p.pop('arm_packages');p['parent_package_digest']='b'*64
    with pytest.raises(ValueError,match='EXECUTION_MANIFEST_REQUIRED'):paired_evaluate(p,files,files,[case],oracle,'task.py')
