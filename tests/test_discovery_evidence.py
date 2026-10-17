import json

import pytest
from skill_observatory.store import Store,canonical
from skill_observatory.runtime import register,spool,ingest,package_manifest
from skill_observatory.transcripts import observe_session
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


def _versioned_setup(tmp_path, old):
    project = tmp_path / 'project'
    project.mkdir()
    s = Store(tmp_path / 'state')
    s.settings({'scopes': [str(project)]})
    skill = project / 'flow'
    skill.mkdir()
    (skill / 'SKILL.md').write_text(old)
    register(s, skill, 'owner')
    cap = s.list('capability_catalog')[0]
    transcript = tmp_path / 'session.jsonl'
    records = [
        {'timestamp': '2026-10-17T00:00:00Z', 'type': 'session_meta', 'payload': {'id': 's', 'cwd': str(project), 'cli_version': '0.162.0-alpha.2'}},
        {'timestamp': '2026-10-17T00:00:00Z', 'type': 'turn_context', 'payload': {'turn_id': 't'}},
        {'timestamp': '2026-10-17T00:00:00Z', 'type': 'response_item', 'payload': {'type': 'function_call', 'call_id': 'call', 'name': 'exec_command', 'arguments': 'cat ' + str(skill / 'SKILL.md')}},
    ]
    transcript.write_text(''.join(json.dumps(record) + '\n' for record in records))
    return s, transcript, skill, cap


def _append_output(transcript, content):
    record = {
        'timestamp': '2026-10-17T00:00:02Z',
        'type': 'response_item',
        'payload': {'type': 'function_call_output', 'call_id': 'call', 'output': content},
    }
    with transcript.open('a') as f:
        f.write(json.dumps(record) + '\n')


def _post_tool_use_events(s):
    with s.connect() as db:
        rows = db.execute(
            "SELECT data FROM events WHERE json_extract(data, '$.event') = 'PostToolUse'"
        ).fetchall()
    return [json.loads(row[0]) for row in rows]


def _run(s):
    return next(run for run in s.list('runs') if run['turn_id'] == 't')


def test_post_tool_use_keeps_pre_call_frozen_package(tmp_path):
    old = '---\nname: flow\ndescription: old\n---\nOld instructions.\n'
    s, transcript, skill, old_cap = _versioned_setup(tmp_path, old)
    old_version = s.get('capability_versions', old_cap['version_id'])
    assert observe_session(s, transcript, 's', 'codex-desktop')['new_events'] == 1

    new = old.replace('old', 'new')
    (skill / 'SKILL.md').write_text(new)
    new_cap = register(s, skill, 'owner')
    assert new_cap['package_sha256'] != old_version['package_sha256']
    _append_output(transcript, old)

    assert observe_session(s, transcript, 's', 'codex-desktop')['new_events'] == 1
    ingest(s)
    expected = {
        'skill_id': s.list('skills')[0]['id'],
        'package_sha256': old_version['package_sha256'],
        'file_sha256': old_version['manifest']['files']['SKILL.md'],
        'attribution': 'verified_read',
        'capability_id': old_cap['id'],
        'version_id': old_cap['version_id'],
        'loaded_version_source': 'exact_whole_tool_output',
        'observed_at': '2026-10-17T00:00:02Z',
    }
    post_events = _post_tool_use_events(s)
    assert len(post_events) == 1
    assert post_events[0]['attributions'] == [expected]
    assert 'tool_input' not in post_events[0]
    assert old not in json.dumps(post_events[0], ensure_ascii=False)

    run = _run(s)
    assert [a for a in run['attributions'] if a['attribution'] == 'verified_read'] == [expected]
    assert {a['package_sha256'] for a in run['attributions']} == {old_version['package_sha256']}
    invocation = s.list('capability_invocations')[0]
    assert invocation['version_id'] == old_cap['version_id']
    assert 'verified_read' in invocation['stages']

    assert observe_session(s, transcript, 's', 'codex-desktop')['new_events'] == 0
    ingest(s)
    run = _run(s)
    assert [a for a in run['attributions'] if a['attribution'] == 'verified_read'] == [expected]


def test_post_tool_use_rejects_output_from_newer_registered_version(tmp_path):
    old = '---\nname: flow\ndescription: old\n---\nOld instructions.\n'
    s, transcript, skill, old_cap = _versioned_setup(tmp_path, old)
    assert observe_session(s, transcript, 's', 'codex-desktop')['new_events'] == 1

    new = old.replace('old', 'new')
    (skill / 'SKILL.md').write_text(new)
    register(s, skill, 'owner')
    _append_output(transcript, new)

    assert observe_session(s, transcript, 's', 'codex-desktop')['new_events'] == 1
    ingest(s)
    post_event = _post_tool_use_events(s)[0]
    assert 'attributions' not in post_event
    assert 'capability_observations' not in post_event
    run = _run(s)
    assert not [a for a in run['attributions'] if a['attribution'] == 'verified_read']
    invocation = s.list('capability_invocations')[0]
    assert invocation['version_id'] == old_cap['version_id']
    assert invocation['stages'] == ['mentioned']


def test_post_tool_use_without_frozen_binding_does_not_read_current_disk(tmp_path):
    old = '---\nname: flow\ndescription: old legacy\n---\nOld legacy instructions.\n'
    s, transcript, skill, _ = _versioned_setup(tmp_path, old)
    with s.connect() as db:
        db.execute("DELETE FROM entities WHERE kind IN ('capability_catalog', 'capability_versions')")
    s._catalog_cache.clear()

    assert observe_session(s, transcript, 's', 'codex-desktop')['new_events'] == 1
    new = old.replace('old', 'current')
    (skill / 'SKILL.md').write_text(new)
    legacy = s.list('skills')[0]
    manifest = package_manifest(skill)
    s.put('skills', {**legacy, 'package_sha256': manifest['package_sha256'], 'manifest': manifest})
    _append_output(transcript, new)

    assert observe_session(s, transcript, 's', 'codex-desktop')['new_events'] == 1
    ingest(s)
    post_event = _post_tool_use_events(s)[0]
    assert 'attributions' not in post_event
    run = _run(s)
    assert not [a for a in run['attributions'] if a['attribution'] == 'verified_read']
    assert manifest['package_sha256'] not in json.dumps(run)
