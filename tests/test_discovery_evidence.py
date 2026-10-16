import pytest
from skill_observatory.store import Store,canonical
from skill_observatory.runtime import register,spool,ingest
from skill_observatory.capabilities import discover,record_usage,register_capability
from skill_observatory.evidence import attach_evidence,build_capsule


def fixture(tmp_path):
 s=Store(tmp_path/'state');s.settings({'scopes':[str(tmp_path)]});p=tmp_path/'flow';p.mkdir()
 (p/'SKILL.md').write_text('---\nname: flow\ndescription: 修复采集身份与预算延期，安全复用证据。\n---\nKeep boundaries.')
 register(s,p,'owner');cap=s.list('capability_catalog')[0]
 spool(s,dict(hook_event_name='Stop',session_id='s',turn_id='t',cwd=str(tmp_path)));ingest(s)
 r=s.list('runs')[0];h=s.artifact(b'private selected receipt')
 record_usage(s,dict(capability_id=cap['id'],version_id=cap['version_id'],cwd=str(tmp_path),session_id='s',turn_id='t',invocation_id='read',stage='verified_read',source='fixture',event_id='verified',evidence_sha256=h))
 return s,p,cap,r,h


def test_chinese_long_query_detects_frozen_version_drift(tmp_path):
 s,p,cap,r,h=fixture(tmp_path)
 found=discover(s,'希望在修复采集身份时保持预算延期并安全复用证据',tmp_path)
 assert found[0]['id']==cap['id'] and found[0]['eligible_for_reuse'] is True
 (p/'SKILL.md').write_text((p/'SKILL.md').read_text()+'\nnew owner text')
 found=discover(s,'采集身份',tmp_path)
 assert found[0]['eligible_for_reuse'] is False and found[0]['reason_code']=='CAPABILITY_VERSION_DRIFT'
 oldversion=cap['version_id'];newcap=register_capability(s,p,'owner',scope=tmp_path)
 assert newcap['version_id']!=oldversion
 projection=s.list('skills')[0]
 assert projection['version_id']==newcap['version_id'] and projection['manifest']==s.get('capability_versions',newcap['version_id'])['manifest']
 assert not s.list('authority_grants')


def test_capsule_bound_to_actual_version_run_and_redacted_facts(tmp_path):
 s,p,cap,r,h=fixture(tmp_path)
 value=dict(run_id=r['id'],goal='Process a scoped event',success_criteria='Correct identity and durable evidence',owner='owner',version_id=cap['version_id'],result={'status':'failed','reason_code':'IDENTITY_MISMATCH'},steps=[{'event_id':r['event_ids'][0],'fact':'Execution ended with an identity mismatch.'}],receipt_sha256=h)
 attach_evidence(s,value);r=s.get('runs',r['id']);capsule=build_capsule(s,r)
 assert capsule['facts']==value and not capsule['missing']
 assert capsule['outcome_truth']=='runtime_only_unverified'
 with pytest.raises(ValueError,match='EVIDENCE_CAPSULE_CONTRACT_INVALID'):attach_evidence(s,{**value,'goal':'api_key=secret'})
 with pytest.raises(ValueError,match='OWNER_VERSION_MISMATCH'):attach_evidence(s,{**value,'owner':'different'})
 with pytest.raises(ValueError,match='STEP_NOT_BOUND'):attach_evidence(s,{**value,'steps':[{'event_id':'unknown','fact':'fake'}]})
 s.put('runs',{**r,'event_ids':[*r['event_ids'],'new']})
 assert 'EVIDENCE_CAPSULE_RUN_DRIFT' in build_capsule(s,s.get('runs',r['id']))['missing']
