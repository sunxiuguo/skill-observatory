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
    with pytest.raises(ValueError,match='VERSION_UNVERIFIED'):observe_session(s,p,'s','codex-desktop')


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
