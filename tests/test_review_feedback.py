"""Independent review regressions: synthetic mechanism evidence, never gain."""
import copy
import json
from datetime import datetime,timedelta,timezone
from pathlib import Path
import pytest
from skill_observatory.store import Store,canonical,digest,now
from skill_observatory.evaluation import EvaluationHold
from skill_observatory.evidence import evidence_plan
from skill_observatory.task_families import seal_native_execution,_ticket_binding
from skill_observatory.outcomes import (freeze_cohort,record_cohort_sample,cohort_report,
    seal_task_receipt,accept_task_result,seal_natural_source,run_binding)
from skill_observatory.semantic_progress import project
from test_task_family_driver import prepared
from test_evidence_recovery import fixture as evidence_fixture
from test_outcomes import fixture as outcome_fixture
from test_outcome_lineage import cohort


def native_trace(tmp_path,change=None):
    s,p,d,*rest=prepared(tmp_path);oracle=rest[-1]
    tid=s.get('task_family_runs',p['id'])['trial_ids'][0]
    a={'ok':True,'provider':'fixture','model':'fixture','reasoning_effort':'max','lease_id':'lease','fork_context':False,'compatibility_contract_sha256':'b'*64}
    row=d.dispatch(tid,a,'child','root');work=Path(row['workdir'])
    # Spawn is after prepare and before dispatch; metadata is not required to
    # be after bind. Actual operation timestamps remain in natural order.
    created=row['created_at'];meta={'id':'child','session_id':'root','cwd':str(work),'cli_version':'0.162.0-alpha.17.2','originator':'codex_exec','thread_source':'subagent','source':{'subagent':{'thread_spawn':{'parent_thread_id':'root'}}}}
    records=[{'timestamp':created,'type':'session_meta','payload':meta}]
    def add(kind,value):records.append({'timestamp':now(),'type':kind,'payload':value})
    add('event_msg',{'type':'task_started','turn_id':'turn'})
    add('turn_context',{'turn_id':'turn','model':'fixture','effort':'max','cwd':str(work)})
    for name in ('SKILL.md','TASK.txt'):
        add('response_item',{'type':'function_call','name':'exec_command','call_id':name,'arguments':json.dumps({'cmd':'cat '+name,'workdir':str(work)})})
        add('response_item',{'type':'function_call_output','call_id':name,'output':json.dumps({'exit_code':0,'output':(work/name).read_text()})})
    add('response_item',{'type':'function_call','name':'exec_command','call_id':'failed','arguments':json.dumps({'cmd':'false','workdir':str(work)})})
    add('response_item',{'type':'function_call_output','call_id':'failed','output':json.dumps({'exit_code':1,'output':'recoverable unrelated failed probe'})})
    add('response_item',{'type':'function_call','name':'exec_command','call_id':'domain','arguments':json.dumps({'cmd':'python3 task.py','workdir':str(work)})})
    add('response_item',{'type':'function_call_output','call_id':'domain','output':json.dumps({'exit_code':0,'output':'actual domain process fixture'})})
    add('event_msg',{'type':'task_complete','turn_id':'turn'})
    (work/'result.json').write_bytes(b'{}')
    proof={'trial_id':tid,'child_id':'child','ticket_sha256':_ticket_binding(row),'admission_sha256':row['admission_sha256'],
           'workdir':row['workdir'],'package_digest':row['package']['package_digest'],'runtime_sha256':p['execution_identity']['runtime_sha256'],'tool_contract_sha256':p['execution_identity']['tool_contract_sha256'],
           'input_read_calls':{'SKILL.md':'SKILL.md','TASK.txt':'TASK.txt'},'domain_call_ids':['domain'],
           'artifact_calls':{'result.json':{'call_id':'domain','sha256':digest(b'{}')}}}
    if change:change(records,proof,row)
    proof['trace_sha256']=digest(canonical(records));proof=seal_native_execution(s,proof)
    trace=tmp_path/'native.jsonl';trace.write_bytes(b''.join(canonical(o)+b'\n' for o in records))
    return s,d,tid,trace,oracle,proof


def test_current_trace_recoverable_failure_and_spawn_before_bind_pass(tmp_path):
    s,d,tid,path,o,proof=native_trace(tmp_path)
    result=d.collect(tid,path,o,proof)
    assert result['passed'] and result['receipt']['fresh_context']
    assert result['receipt']['context_created_at']<=s.get('task_family_attempts',tid)['dispatched_at']
    assert result['receipt']['tool_calls']==4
    with pytest.raises(EvaluationHold,match='READBACK_REQUIRED'):d.collect(tid,path,o,proof)


@pytest.mark.parametrize('change,reason',[
    (lambda r,p,t:r[0].update(timestamp='2025-01-01T00:00:00Z'),'STALE_CONTEXT'),
    (lambda r,p,t:r.append({'timestamp':now(),'type':'event_msg','payload':{'type':'task_started','turn_id':'still-running'}}),'TERMINAL_READBACK'),
    (lambda r,p,t:r[0]['payload'].update(cwd=str(Path(t['workdir']).parent)),'WORKSPACE_DRIFT'),
    (lambda r,p,t:r.insert(-1,{'timestamp':now(),'type':'response_item','payload':{'type':'function_call_output','call_id':'unpaired','output':'orphan'}}),'PAIRING_INVALID'),
    (lambda r,p,t:p.update(domain_call_ids=['failed'],artifact_calls={'result.json':{'call_id':'failed','sha256':digest(b'{}')}}),'DOMAIN_EXECUTION_FAILED'),
    (lambda r,p,t:p['input_read_calls'].update({'TASK.txt':'domain'}),'INPUT_LOAD_REQUIRED'),
    (lambda r,p,t:p.update(artifact_calls={'result.json':{'call_id':'domain','sha256':'a'*64}}),'ARTIFACT_EXECUTION_BINDING'),
])
def test_stale_pending_wrong_workspace_unpaired_unrelated_and_unloaded_refuse(tmp_path,change,reason):
    s,d,tid,path,o,proof=native_trace(tmp_path,change)
    with pytest.raises(EvaluationHold,match=reason):d.collect(tid,path,o,proof)
    assert s.get('task_family_attempts',tid)['status']=='dispatched'


def test_arbitrary_tools_and_valid_file_are_not_domain_evidence(tmp_path):
    s,d,tid,path,o,proof=native_trace(tmp_path)
    with pytest.raises(EvaluationHold,match='DOMAIN_EXECUTION_REQUIRED'):d.collect(tid,path,o)
    proof['signature']='untrusted'
    with pytest.raises(EvaluationHold,match='EVIDENCE_UNTRUSTED'):d.collect(tid,path,o,proof)


def test_backlog_all_13_in_four_ticks_and_built_latest_does_not_starve(tmp_path):
    s,r,_=evidence_fixture(tmp_path)
    for i in range(12):s.put('runs',{**r,'id':f'backlog-{i:02}','terminal':True,'updated_at':f'2026-10-{i+1:02}T00:00:00+00:00'})
    seen=set()
    for _ in range(4):seen.update(x['run_id'] for x in evidence_plan(s,limit=4))
    assert len(seen)==13 and len(s.list('evidence_builds'))==13
    for row in s.list('evidence_builds'):s.put('evidence_builds',{**row,'status':'built'})
    assert evidence_plan(s,limit=4)==[]
    assert len(s.list('evidence_builds'))==13


def test_limit_one_continuous_arrival_restart_and_old_source_change(tmp_path):
    s,r,_=evidence_fixture(tmp_path);initial=[]
    for i in range(5):
        id_='old-'+str(i);initial.append(id_);s.put('runs',{**r,'id':id_,'terminal':True})
    seen=set()
    for i in range(18):
        s.put('runs',{**r,'id':'new-'+str(i),'terminal':True})
        seen.update(x['run_id'] for x in evidence_plan(s,limit=1))
        s=Store(s.root)
    assert set(initial)<=seen and any(x.startswith('new-') for x in seen)
    assert all(x['model_attempts']==0 for x in s.list('evidence_builds'))


def natural_sample(s,c,base,id_,arm,*,known=True,complete=True,zero=False,currency='USD',extra_failed=False,family=None,installation=None,session_id=None,turn_id=None,logical_task_id=None):
    iid=installation or c['arm_bindings'][arm]['installation_id'];i=s.get('installations',iid)
    run={**s.get('runs','r'),'id':'run-'+id_,'session_id':'context-'+id_,'origin':'user_run','event_ids':['ev-'+id_],
         'attributions':[{'attribution':'verified_read','file_sha256':i['after_sha256']}]}
    if session_id:run['session_id']=session_id
    if turn_id:run['turn_id']=turn_id
    s.put('runs',run)
    context=s.artifact(canonical({'context_id':run['session_id'],'origin':'trusted_broker','fresh':True,
        **c['comparison'],'created_at':'2026-01-04T00:00:00+00:00'}))
    refs=[]
    if known and not zero:
        attempt={'id':'attempt-'+id_,'run_id':run['id'],'status':'completed','cost':{'money':1.5,'tokens':10,'currency':currency}}
        s.put('review_attempts',attempt);refs=[{'kind':'review_attempts','id':attempt['id'],'sha256':digest(canonical(attempt))}]
    receipt={**base,'id':'receipt-'+id_,'run_id':run['id'],'run_binding_sha256':run_binding(run),'installation_id':iid,
             'skill_sha256':i['after_sha256'],'context_receipt_sha256':context,'task_family_sha256':family or c['task_family_sha256'],
             'logical_task_id':logical_task_id or 'task-'+id_,'natural_source_definition_sha256':c['source_definition_sha256']}
    if complete:
        manifest={'run_id':run['id'],'complete':True,'attempt_refs':refs}
        if zero:manifest['zero_cost']={'money':0,'tokens':0,'currency':currency}
        receipt['cost_manifest_sha256']=s.artifact(canonical(manifest))
    accept_task_result(s,seal_task_receipt(s,receipt))
    if extra_failed:s.put('broker_attempts',{'id':'failed-'+id_,'run_id':run['id'],'status':'failed','cost':{'money':.5,'tokens':5,'currency':currency}})
    source=seal_natural_source(s,{'run_id':run['id'],'source_class':'natural','logical_task_id':receipt['logical_task_id'],'definition_sha256':c['source_definition_sha256'],'evidence_sha256':s.artifact(b'synthetic independent natural-source fixture')})
    return record_cohort_sample(s,{'id':'sample-'+id_,'cohort_id':c['id'],'arm':arm,'task_receipt_id':receipt['id'],'source_receipt':source,'rework':0,'takeovers':0,'elapsed_seconds':1,'attempt_refs':refs})


def cohort_fixture(tmp_path):
    s=Store(tmp_path/'state');r=outcome_fixture(s,tmp_path);c=cohort(s);c['denominator']={'parent':1,'candidate':2};freeze_cohort(s,c)
    return s,r,c


def test_legitimate_parent_candidate_and_all_sample_costs(tmp_path):
    s,r,c=cohort_fixture(tmp_path)
    natural_sample(s,c,r,'parent','parent');natural_sample(s,c,r,'one','candidate');natural_sample(s,c,r,'two','candidate')
    report=cohort_report(s,c['id']);assert report['arms']['candidate']['money']==3 and report['arms']['candidate']['tokens']==20
    assert report['arms']['candidate']['missing']==[] and report['natural_gain']=='UNKNOWN'


@pytest.mark.parametrize('kind',['same_installation','same_candidate_other_installation','unrelated_version','task_family'])
def test_wrong_parent_or_family_cannot_be_natural_comparison(tmp_path,kind):
    s,r,c=cohort_fixture(tmp_path)
    iid='i'
    if kind in {'same_candidate_other_installation','unrelated_version'}:
        value={**s.get('installations','i'),'id':'alias'}
        if kind=='unrelated_version':value['after_sha256']=s.artifact(b'unrelated')
        s.put('installations',value);iid='alias'
    with pytest.raises(ValueError,match='INSTALLATION_MISMATCH|TASK_FAMILY_MISMATCH'):
        natural_sample(s,c,r,'bad','parent' if kind!='task_family' else 'candidate',installation=iid,
                       family=s.artifact(b'different family') if kind=='task_family' else None)
    assert not s.list('cohort_samples')


@pytest.mark.parametrize('kind',['same_version','unknown_parent','unrelated_parent'])
def test_freeze_requires_actual_predecessor_not_just_different_id(tmp_path,kind):
    s=Store(tmp_path/'state');outcome_fixture(s,tmp_path);c=cohort(s)
    if kind=='same_version':
        i={**s.get('installations','i'),'id':'alias'};s.put('installations',i);c['arm_bindings']['parent']={'installation_id':'alias','version_sha256':i['after_sha256']}
    elif kind=='unknown_parent':c['arm_bindings']['parent']['installation_id']='missing'
    else:s.put('installations',{**s.get('installations','i'),'before_sha256':'a'*64})
    with pytest.raises(ValueError,match='DISTINCT_PARENT|INSTALLATION_UNKNOWN|PARENT_VERSION_UNKNOWN'):freeze_cohort(s,c)


@pytest.mark.parametrize('kind',['missing_task','missing_failed_attempt','mixed_currency'])
def test_one_task_cannot_hide_another_tasks_cost_gap(tmp_path,kind):
    s,r,c=cohort_fixture(tmp_path);natural_sample(s,c,r,'one','candidate')
    natural_sample(s,c,r,'two','candidate',known=kind!='missing_task',complete=kind!='missing_task',extra_failed=kind=='missing_failed_attempt',currency='CNY' if kind=='mixed_currency' else 'USD')
    arm=cohort_report(s,c['id'])['arms']['candidate']
    assert arm['observed']==arm['denominator']==2 and arm['money'] is None and arm['tokens'] is None
    assert 'ALL_ATTEMPT_COST_REQUIRED' in arm['missing']


def test_explicit_complete_zero_cost_and_later_failed_attempt_reconciliation(tmp_path):
    s,r,c=cohort_fixture(tmp_path);natural_sample(s,c,r,'one','candidate',zero=True);natural_sample(s,c,r,'two','candidate',zero=True)
    assert cohort_report(s,c['id'])['arms']['candidate']['money']==0
    s.put('generation_attempts',{'id':'late-failure','run_id':'run-two','status':'failed','cost':{'money':1,'tokens':2,'currency':'USD'}})
    arm=cohort_report(s,c['id'])['arms']['candidate']
    assert arm['money'] is None and 'KNOWN_ATTEMPT_COST_MISSING' in next(x for x in arm['sample_cost_coverage'] if x['sample_id']=='sample-two')['missing']


def test_material_blockers_follow_real_pending_chain_not_cumulative_counts(tmp_path):
    s=Store(tmp_path/'state');assert project(s)['first_blocker'] is None
    s.put('task_family_attempts',{'id':'t','protocol_id':'p','status':'completed'})
    s.put('verdicts',{'id':'v','protocol_id':'p','status':'hold','missing':['COST_COVERAGE_REQUIRED']})
    assert project(s)['first_blocker']=='COST_COVERAGE_REQUIRED'
    s.put('verdicts',{'id':'v2','protocol_id':'p','status':'accepted','missing':[]})
    assert project(s)['first_blocker']=='OWNER_AUTHORITY_AND_INSTALLATION_REQUIRED'
    s.put('candidates',{'id':'c','verdict_id':'v2'});s.put('installations',{'id':'i','candidate_id':'c','status':'activation_pending','applied_at':now()})
    assert project(s)['first_blocker']=='FRESH_ACTIVATION_REQUIRED'
    s.put('installations',{**s.get('installations','i'),'status':'activated','activated':True})
    assert project(s)['first_blocker'] is None


def test_no_gain_is_closed_without_fictitious_pending_work(tmp_path):
    s=Store(tmp_path/'state');s.put('verdicts',{'id':'v','status':'hold','protocol_id':'p','missing':['NO_CONFIRMED_GAIN']})
    p=project(s);assert p['first_blocker'] is None and p['flow_state']=='no_gain' and p['next_action']=='await_changed_input'


def test_growing_9mib_source_continues_with_bounded_snapshot_reads_and_restart(tmp_path,monkeypatch):
    from test_collection_recovery import setup,record,drain
    from skill_observatory import transcripts as t
    s,p=setup(tmp_path)
    with p.open('ab') as f:f.write(record('response_item',{'type':'function_call_output','output':'x'*(9*1024*1024)}))
    drain(s,p)
    original=t._snapshot_view;read_bytes=[0];capable=[None]
    class Meter:
        def __init__(self,f):self.f=f
        def read(self,n):
            assert 0<n<=256*1024
            data=self.f.read(n);read_bytes[0]+=len(data);return data
        def __getattr__(self,key):return getattr(self.f,key)
    def measured(*args):
        view=original(*args);capable[0]=view is not None
        return Meter(view) if view is not None else None
    monkeypatch.setattr(t,'_snapshot_view',measured)
    consumed=0
    for n in range(12):
        with p.open('ab') as f:f.write(record('event_msg',{'type':'task_complete','turn_id':'later-'+str(n)}))
        read_bytes[0]=0
        try:r=t.observe_session(s,p,'s','codex-desktop')
        except ValueError as ex:
            # An unsupported filesystem must explicitly HOLD, never claim that
            # a growing prefix is verified or silently lose its integrity gate.
            assert capable[0] is False and str(ex)=='TRANSCRIPT_STABLE_SNAPSHOT_UNAVAILABLE'
            return
        assert read_bytes[0]<=t.SCAN_BYTES
        consumed+=r['new_events']
        if n==3:s=Store(s.root)
    assert capable[0] and consumed>=6
    drain(s,p)
    assert len(s.list('transcript_gaps'))==1


def test_growing_archive_relocation_and_true_prefix_drift_refusal(tmp_path):
    from test_collection_recovery import setup,record,drain
    from skill_observatory.transcripts import observe_session,track_hook_session,relocate_archived_transcript,SCAN_BYTES
    s,p=setup(tmp_path);track_hook_session(s,{'session_id':'s','transcript_path':str(p),'event':'SessionStart'})
    with p.open('ab') as f:f.write(record('response_item',{'type':'function_call_output','output':'x'*(9*1024*1024)}))
    drain(s,p);old=p;dest=tmp_path/'archived';dest.mkdir();p.rename(dest/p.name);p=dest/p.name
    migrated=None
    for n in range(6):
        with p.open('ab') as f:f.write(record('event_msg',{'type':'task_complete','turn_id':'later-'+str(n)}))
        try:migrated=relocate_archived_transcript(s,p,old_path=old,scan_budget=SCAN_BYTES)
        except ValueError as ex:
            assert str(ex)=='TRANSCRIPT_STABLE_SNAPSHOT_UNAVAILABLE';return
        if migrated:break
    assert migrated is not None
    drain(s,p)
    # Corrupt a consumed byte while also growing: size growth cannot authorize
    # a changed prefix. The next fixed view must reject before new consumption.
    with p.open('r+b') as f:f.seek(1000);f.write(b'Z')
    with p.open('ab') as f:f.write(record('event_msg',{'type':'task_complete','turn_id':'tampered'}))
    before=s.list('cursors')[0]['offset']
    with pytest.raises(ValueError,match='DRIFT_HOLD'):
        for _ in range(8):observe_session(s,p,'s','codex-desktop')
    assert s.list('cursors')[0]['offset']==before


def test_snapshot_does_not_retain_raw_transcript_and_truncation_refuses(tmp_path):
    from test_collection_recovery import setup,record,drain
    from skill_observatory.transcripts import observe_session
    s,p=setup(tmp_path)
    with p.open('ab') as f:f.write(record('response_item',{'type':'function_call_output','output':'x'*(9*1024*1024)}))
    drain(s,p)
    with p.open('ab') as f:f.write(record('event_msg',{'type':'task_complete','turn_id':'later'}))
    observe_session(s,p,'s','codex-desktop')
    assert not list(s.root.glob('transcript-view-*'))
    with p.open('r+b') as f:f.truncate(512)
    with pytest.raises(ValueError,match='DRIFT_HOLD|SOURCE_CHANGED'):
        for _ in range(8):observe_session(s,p,'s','codex-desktop')
