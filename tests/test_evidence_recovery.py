import json
import pytest
from skill_observatory.store import Store
from skill_observatory.runtime import register,spool,ingest,process_one
from skill_observatory.capabilities import record_usage
from skill_observatory.evidence import attach_evidence,build_capsule,diagnostic_from_output
from skill_observatory.reviewer import CodexReviewer


def fixture(tmp_path):
    s=Store(tmp_path/'state');s.settings({'scopes':[str(tmp_path)]})
    p=tmp_path/'flow';p.mkdir();(p/'SKILL.md').write_text('---\nname: flow\ndescription: scoped proof\n---\nKeep boundaries.')
    register(s,p,'owner');cap=s.list('capability_catalog')[0]
    spool(s,dict(hook_event_name='Stop',session_id='s',turn_id='t',cwd=str(tmp_path)));ingest(s)
    run=s.list('runs')[0];h=s.artifact(b'selected private receipt')
    record_usage(s,dict(capability_id=cap['id'],version_id=cap['version_id'],cwd=str(tmp_path),session_id='s',turn_id='t',invocation_id='read',stage='verified_read',source='fixture',event_id='read',evidence_sha256=h))
    reviewer=CodexReviewer(None,None,'unused','unused','max',tmp_path)
    process_one(s,reviewer)
    assert s.jobs()[0]['reason_code']=='DIAGNOSTIC_FACTS_REQUIRED'
    facts=dict(run_id=run['id'],goal='Complete the scoped CLI task',success_criteria='Correct arguments and validated result',owner='owner',version_id=cap['version_id'],result={'status':'failed','reason_code':'CLI_ARGUMENT_MISMATCH','exit_code':2},steps=[{'event_id':run['event_ids'][0],'fact':'The tool rejected an unsupported argument and exited with code 2.'}],receipt_sha256=h)
    return s,run,facts


def test_facts_arrival_resumes_predispatch_once(tmp_path):
    s,run,facts=fixture(tmp_path)
    receipt=attach_evidence(s,facts)
    assert receipt['resumed_pre_dispatch_jobs']==1 and s.jobs()[0]['status']=='queued'
    assert build_capsule(s,run)['missing']==[]
    assert s.lease() is not None
    with s.connect() as db:db.execute("UPDATE jobs SET status='hold',reason_code='DIAGNOSTIC_FACTS_REQUIRED'")
    assert attach_evidence(s,facts)==receipt
    assert s.jobs()[0]['status']=='hold'


@pytest.mark.parametrize('attempt',[{'status':'prepared','admission_sha256':'a'*64},{'status':'unknown_after_dispatch'},{'status':'completed'}])
def test_unknown_or_dispatched_attempt_never_reopens(tmp_path,attempt):
    s,run,facts=fixture(tmp_path)
    s.put('review_attempts',{'id':'ambiguous','run_id':run['id'],**attempt})
    assert attach_evidence(s,facts)['resumed_pre_dispatch_jobs']==0
    assert s.jobs()[0]['status']=='hold'


def test_typed_failure_extraction_does_not_copy_output_or_secrets():
    output=json.dumps({'output':'usage: tool: error: unrecognized arguments: --root sk-private-credential','exit_code':2})
    fact=diagnostic_from_output(output)
    assert fact=={'status':'failed','exit_code':2,'reason_code':'CLI_ARGUMENT_MISMATCH'}
    assert 'private' not in json.dumps(fact)
    assert diagnostic_from_output({'exit_code':0,'output':'all good'}) is None


def test_diagnostic_scope_and_trusted_source_are_separate(tmp_path):
    s=Store(tmp_path/'state');s.settings({'scopes':[str(tmp_path)]})
    payload=dict(hook_event_name='PostToolUse',session_id='s',turn_id='t',cwd=str(tmp_path),tool_use_id='call',diagnostic_fact={'status':'failed','exit_code':2,'reason_code':'CLI_ARGUMENT_MISMATCH'})
    spool(s,payload,'codex-desktop');ingest(s);assert not s.list('run_diagnostics')
    s.settings({'diagnostic_scopes':[str(tmp_path)]})
    payload['tool_use_id']='authorized';spool(s,payload,'codex-desktop');ingest(s)
    facts=s.list('run_diagnostics');assert len(facts)==1 and len(facts[0]['steps'])==1
    assert facts[0]['goal'] is None
