import json
import pytest
from skill_observatory.store import Store
from skill_observatory.transcripts import observe_session
from skill_observatory.runtime import register,ingest


def test_current_transcript_exact_bytes_and_cursor(tmp_path):
    project=tmp_path/'project';project.mkdir();s=Store(tmp_path/'state');s.settings({'scopes':[str(project)]})
    skill=project/'flow';skill.mkdir();text='---\nname: flow\ndescription: flow\n---\nUse actual flow.\n';(skill/'SKILL.md').write_text(text)
    register(s,skill,'owner')
    records=[{'type':'session_meta','payload':{'id':'s','cwd':str(project),'cli_version':'0.162.0-alpha.2'}},
             {'type':'turn_context','payload':{'turn_id':'t'}},
             {'type':'response_item','payload':{'type':'custom_tool_call','call_id':'call','name':'exec','input':'cat '+str(skill/'SKILL.md')}},
             {'type':'response_item','payload':{'type':'custom_tool_call_output','call_id':'call','output':text}}]
    p=tmp_path/'session.jsonl';p.write_text(''.join(json.dumps(x)+'\n' for x in records))
    assert observe_session(s,p,'s','codex-desktop')['new_events']==2
    ingest(s)
    inv=s.list('capability_invocations');assert len(inv)==1
    assert set(inv[0]['stages'])=={'mentioned','verified_read'}
    assert observe_session(s,p,'s','codex-desktop')['new_events']==0
    p.write_text(p.read_text().replace('0.162.0-alpha.2','0.163.0'))
    with pytest.raises(ValueError,match='SOURCE_SCHEMA_UNVERIFIED'):observe_session(s,p,'s','codex-desktop')


def test_call_time_version_stays_bound_after_disk_change(tmp_path):
    project=tmp_path/'project';project.mkdir();s=Store(tmp_path/'state');s.settings({'scopes':[str(project)]})
    skill=project/'flow';skill.mkdir();old='---\nname: flow\ndescription: old\n---\nOld instructions.\n';(skill/'SKILL.md').write_text(old)
    register(s,skill,'owner');cap=s.list('capability_catalog')[0];version=cap['version_id']
    p=tmp_path/'session.jsonl';records=[{'type':'session_meta','payload':{'id':'s','cwd':str(project),'cli_version':'0.162.0-alpha.2'}},{'type':'turn_context','payload':{'turn_id':'t'}},{'type':'response_item','payload':{'type':'function_call','call_id':'call','name':'exec_command','arguments':'cat '+str(skill/'SKILL.md')}}]
    p.write_text(''.join(json.dumps(x)+'\n' for x in records));observe_session(s,p,'s','codex-desktop')
    (skill/'SKILL.md').write_text(old.replace('old','new'));register(s,skill,'owner')
    with p.open('a') as f:f.write(json.dumps({'type':'response_item','payload':{'type':'function_call_output','call_id':'call','output':old}})+'\n')
    observe_session(s,p,'s','codex-desktop');ingest(s)
    assert any(x['version_id']==version and 'verified_read' in x['stages'] for x in s.list('capability_invocations'))


def test_hook_attachment_skips_previous_history_and_follows_current_read(tmp_path):
    from skill_observatory.transcripts import track_hook_session
    project=tmp_path/'project';project.mkdir();s=Store(tmp_path/'state');s.settings({'scopes':[str(project)]})
    skill=project/'flow';skill.mkdir();text='---\nname: flow\ndescription: current\n---\nInstructions.\n';(skill/'SKILL.md').write_text(text);register(s,skill,'owner')
    p=tmp_path/'session.jsonl';p.write_text(json.dumps({'type':'session_meta','payload':{'id':'s','cwd':str(project),'cli_version':'0.162.0-alpha.2'}})+'\n'+json.dumps({'type':'event_msg','payload':{'type':'task_complete','turn_id':'historical'}})+'\n')
    selected=track_hook_session(s,{'session_id':'s','turn_id':'now','transcript_path':str(p),'event':'SessionStart'})
    assert selected['missing']==['BEFORE_ATTACHMENT_NOT_OBSERVED']
    assert observe_session(s,p,'s','codex-desktop')['new_events']==0
    with p.open('a') as f:
        for payload in [{'type':'custom_tool_call','call_id':'new','name':'exec','input':'cat '+str(skill/'SKILL.md')},{'type':'custom_tool_call_output','call_id':'new','output':text}]:f.write(json.dumps({'type':'response_item','payload':payload})+'\n')
    observe_session(s,p,'s','codex-desktop');ingest(s)
    assert all(x['turn_id']!='historical' for x in s.list('runs'))
    assert any('verified_read' in x['stages'] for x in s.list('capability_invocations'))
    assert track_hook_session(s,{'session_id':'s','transcript_path':str(p),'event':'SessionEnd'})['closed']


@pytest.mark.parametrize("shape", ["settled", "nested_content", "json_output", "result_lines"])
@pytest.mark.parametrize("case", ["exact", "partial", "drift", "unbound", "metadata"])
def test_structured_tool_result_preserves_exact_skill_read(tmp_path, shape, case):
    project = tmp_path / 'project'; project.mkdir()
    store = Store(tmp_path / 'state'); store.settings({'scopes': [str(project)]})
    skill = project / 'flow'; skill.mkdir()
    text = '---\nname: flow\ndescription: flow\n---\nExact instructions.\n'
    (skill / 'SKILL.md').write_text(text); register(store, skill, 'owner')
    returned = text[:-12] if case == 'partial' else text
    if case == 'drift':
        (skill / 'SKILL.md').write_text(text + 'Changed.\n')
    result = {'metadata': text} if case == 'metadata' else {'output': returned, 'exit_code': 0}
    if shape == 'settled':
        result = {'i': 0, 'status': 'fulfilled', 'value': result}
    elif shape == 'nested_content':
        result = {'content': [{'type': 'text', 'text': json.dumps({'value': result})}]}
    else:
        result = {'output': json.dumps(result)}
    serialized = json.dumps(result)
    if shape == 'result_lines':
        serialized = 'Script completed\nOutput:\n' + json.dumps({'i': 0, 'value': {'output': 'Other result'}}) + '\n' + json.dumps({'i': 1, 'status': 'fulfilled', 'value': result})
    records = [
        {'type': 'session_meta', 'payload': {'id': 's', 'cwd': str(project), 'cli_version': '0.162.0-alpha.2'}},
        {'type': 'turn_context', 'payload': {'turn_id': 't'}},
        {'type': 'response_item', 'payload': {'type': 'custom_tool_call', 'call_id': 'read', 'name': 'exec', 'input': 'cat ' + str(skill / 'SKILL.md')}},
        {'type': 'response_item', 'payload': {'type': 'custom_tool_call_output', 'call_id': 'other' if case == 'unbound' else 'read', 'output': [{'type': 'input_text', 'text': serialized}]}},
    ]
    path = tmp_path / 'session.jsonl'
    path.write_text(''.join(json.dumps(row) + '\n' for row in records))
    observe_session(store, path, 's', 'codex-desktop'); ingest(store)
    usages = store.list('capability_invocations')
    assert len(usages) == 1
    assert ('verified_read' in usages[0]['stages']) == (case == 'exact')
    restarted = Store(store.root)
    assert observe_session(restarted, path, 's', 'codex-desktop')['new_events'] == 0
    assert len(restarted.list('capability_invocations')) == 1


def test_structured_read_parser_keeps_bounds_and_invalid_json_safe():
    from skill_observatory.transcripts import _tool_output_texts
    content = 'Exact instructions.\n'
    deep = {'output': content}
    for _ in range(20):
        deep = {'value': deep}
    assert content not in _tool_output_texts(deep)
    assert content not in _tool_output_texts([{}] * 64 + [{'output': content}])
    malformed = '{"output": "unterminated'
    assert _tool_output_texts(malformed) == [malformed]
    too_deep_json = '[' * 1200 + '0' + ']' * 1200
    assert _tool_output_texts(too_deep_json) == [too_deep_json]
