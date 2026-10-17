import json
import pytest
from skill_observatory.store import Store
from skill_observatory.runtime import register,ingest,spool
from skill_observatory.transcripts import observe_session,track_hook_session,relocate_archived_transcript


def setup(tmp_path,version='0.162.0-alpha.17.2',child=False,parent='parent',root='parent'):
 s=Store(tmp_path/'state');s.settings({'scopes':[str(tmp_path)]})
 meta={'id':'child' if child else 'parent','session_id':root,'cwd':str(tmp_path),'cli_version':version,'originator':'Codex Desktop','source':'vscode'}
 if child:meta.update(thread_source='subagent',source={'subagent':{'thread_spawn':{'parent_thread_id':parent,'depth':2 if parent!=root else 1}}})
 p=tmp_path/'session.jsonl';p.write_text(json.dumps({'type':'session_meta','payload':meta})+'\n')
 return s,p,meta


def append(p,payload,type='event_msg'):
 with p.open('a') as f:f.write(json.dumps({'type':type,'timestamp':'2026-10-13T03:00:00Z','payload':payload})+'\n')


def test_certified_app_child_nested_identity_and_exact_future_rejection(tmp_path):
 s,p,m=setup(tmp_path,child=True,parent='immediate-parent',root='root')
 selected=track_hook_session(s,dict(event='SubagentStart',session_id='root',agent_id='child',transcript_path=str(p)))
 assert selected['execution_session_id']=='child' and selected['parent_session_id']=='immediate-parent'
 append(p,{'type':'task_complete','turn_id':'t'})
 observe_session(s,p,selected['session_id'],selected['source']);ingest(s)
 r=s.list('runs')[0];assert r['session_id']=='child' and r['parent_session_id']=='immediate-parent' and r['root_session_id']=='root'
 with pytest.raises(ValueError,match='SESSION_ID_MISMATCH'):track_hook_session(s,dict(event='SubagentStop',session_id='unrelated',agent_id='child',transcript_path=str(p)))
 m['cli_version']='0.162.0-alpha.17.3';p.write_text(json.dumps({'type':'session_meta','payload':m})+'\n')
 with pytest.raises(ValueError,match='VERSION_UNVERIFIED'):observe_session(s,p,'child','codex-subagent')


@pytest.mark.parametrize('version,source',[('0.160.1','codex-cli'),('0.162.0-alpha.17.2','codex-desktop')])
def test_certified_cli_and_app_schema_and_source_controls(tmp_path,version,source):
 s,p,m=setup(tmp_path,version)
 append(p,{'type':'task_complete','turn_id':'t'})
 assert observe_session(s,p,'parent',source)['new_events']==1
 if version.startswith('0.162.'):
  with pytest.raises(ValueError,match='SOURCE_SCHEMA_UNVERIFIED'):observe_session(s,p,'parent','codex-cli')
  m.pop('session_id');p.write_text(json.dumps({'type':'session_meta','payload':m})+'\n')
  with pytest.raises(ValueError,match='SCHEMA_UNVERIFIED'):observe_session(s,p,'parent',source)


def test_stable_cli_exec_identity_and_unverified_source_refusal(tmp_path):
 s,p,m=setup(tmp_path,'0.162.1');m.update(originator='codex_exec',source='exec')
 p.write_text(json.dumps({'type':'session_meta','payload':m})+'\n')
 append(p,{'type':'task_complete','turn_id':'t'})
 assert observe_session(s,p,'parent','codex-cli')['new_events']==1
 for source in ['codex-desktop','codex-subagent']:
  with pytest.raises(ValueError,match='SOURCE_SCHEMA_UNVERIFIED'):observe_session(s,p,'parent',source)
 for patch,reason in [({'source':'vscode'},'SOURCE_SCHEMA_UNVERIFIED'),({'originator':'Codex Desktop'},'SOURCE_SCHEMA_UNVERIFIED'),({'session_id':'other'},'SCHEMA_UNVERIFIED'),({'session_id':None},'SCHEMA_UNVERIFIED'),({'cli_version':'0.162.2'},'VERSION_UNVERIFIED')]:
  p.write_text(json.dumps({'type':'session_meta','payload':{**m,**patch}})+'\n')
  with pytest.raises(ValueError,match=reason):observe_session(s,p,'parent','codex-cli')


def test_child_hook_transcript_read_is_one_logical_invocation(tmp_path):
 s,p,m=setup(tmp_path,child=True)
 skill=tmp_path/'flow';skill.mkdir();text='---\nname: flow\ndescription: flow\n---\nActual bytes.\n';(skill/'SKILL.md').write_text(text);register(s,skill,'owner')
 track_hook_session(s,dict(event='SubagentStart',session_id='parent',agent_id='child',turn_id='t',transcript_path=str(p)))
 append(p,{'type':'function_call','call_id':'call','name':'exec_command','arguments':'cat '+str(skill/'SKILL.md')},'response_item')
 append(p,{'type':'function_call_output','call_id':'call','output':text},'response_item')
 spool(s,dict(hook_event_name='PreToolUse',session_id='parent',agent_id='child',turn_id='t',tool_use_id='call',cwd=str(tmp_path),tool_input='cat '+str(skill/'SKILL.md')))
 observe_session(s,p,'child','codex-subagent');ingest(s)
 assert len(s.list('runs'))==1 and len(s.list('capability_invocations'))==1
 assert 'verified_read' in s.list('capability_invocations')[0]['stages']


def test_archive_relocation_is_exact_prefix_atomic_and_consumes_appended_tail(tmp_path):
 s,p,m=setup(tmp_path)
 selected=track_hook_session(s,dict(event='SessionStart',session_id='parent',transcript_path=str(p)))
 moved=tmp_path/'archive.jsonl';p.rename(moved);append(moved,{'type':'task_complete','turn_id':'t'})
 replacement=relocate_archived_transcript(s,moved,old_path=p)
 assert s.get('selected_sessions',selected['id'])['closed']
 assert observe_session(s,moved,'parent','codex-desktop')['new_events']==1
 ingest(s);assert len(s.list('runs'))==1
 assert replacement['missing']==['ARCHIVE_RELOCATION_FUTURE_ONLY','BEFORE_ATTACHMENT_NOT_OBSERVED'] or set(replacement['missing'])=={'ARCHIVE_RELOCATION_FUTURE_ONLY','BEFORE_ATTACHMENT_NOT_OBSERVED'}
 with pytest.raises(ValueError,match='NOT_FOUND'):relocate_archived_transcript(s,moved,old_path=tmp_path/'unselected')


def test_aggregated_collector_error_backoff(tmp_path):
 from skill_observatory.runtime import collect
 s,p,m=setup(tmp_path);track_hook_session(s,dict(event='SessionStart',session_id='parent',transcript_path=str(p)));p.unlink()
 collect(s);collect(s)
 assert len(s.list('adapter_errors'))==1 and s.list('adapter_errors')[0]['count']==1
 assert s.list('selected_sessions')[0]['eligible_at']>0


def test_closed_session_drains_late_tail_once_and_attachment_prefix_is_exact(tmp_path):
 from skill_observatory.runtime import collect
 from skill_observatory.store import digest
 s,p,m=setup(tmp_path)
 # A large attachment with a partial trailing record stays bounded and hashes
 # precisely the complete prefix, including across chunk boundaries.
 with p.open('a') as f:f.write(' '*1100000+'\n'+ '{"type":"event_msg","payload":')
 initial=p.read_bytes();selected=track_hook_session(s,dict(event='SessionStart',session_id='parent',transcript_path=str(p)))
 cursor=s.list('cursors')[0];complete=initial[:initial.rfind(b'\n')+1]
 assert cursor['offset']==len(complete) and cursor['prefix_sha256']==digest(complete)
 # Complete the record after attachment, then close before collection resumes.
 with p.open('a') as f:f.write('{"type":"task_complete","turn_id":"t"}}\n')
 track_hook_session(s,dict(event='SessionEnd',session_id='parent',transcript_path=str(p)))
 assert s.get('selected_sessions',selected['id'])['closed']
 for _ in range(3):collect(s)
 assert len(s.list('runs'))==1 and len(s.jobs())==1
 assert s.list('cursors')[0]['offset']==p.stat().st_size
