import json
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from skill_observatory.store import Store,canonical,digest
from skill_observatory.runtime import spool,ingest,process_one,collect
from skill_observatory.reviewer import CodexReviewer,ReviewDeferred
from skill_observatory.api import create_app


def seeded(tmp_path):
 s=Store(tmp_path/'state');s.settings({'scopes':[str(tmp_path)]})
 spool(s,dict(hook_event_name='Stop',session_id='s',turn_id='t',cwd=str(tmp_path)))
 ingest(s);return s,s.list('runs')[0]


def test_review_block_does_not_block_api_collector(tmp_path):
 s,r=seeded(tmp_path);entered=threading.Event();release=threading.Event()
 class Slow:
  def review(self,*args):entered.set();release.wait(4)
 try:
  with TestClient(create_app(s,reviewer=Slow()),base_url='http://127.0.0.1') as c:
   assert entered.wait(2)
   spool(s,dict(hook_event_name='PreToolUse',session_id='other',turn_id='new',cwd=str(tmp_path)))
   deadline=time.monotonic()+3
   while time.monotonic()<deadline and len(s.list('runs'))<2:time.sleep(.02)
   assert len(s.list('runs'))==2
   runtime=s.get('runtime','daemon')
   assert runtime['build_sha256'] and time.time()-runtime['heartbeat']<2
   assert s.get('runtime','review_worker')['phase']=='review'
   release.set()
 finally:release.set()


def test_budget_deferral_recovers_once_without_failed_attempt(tmp_path):
 s,r=seeded(tmp_path)
 reviewer=CodexReviewer(None,None,'synthetic','synthetic','max',tmp_path,daily_attempt_limit=0)
 assert process_one(s,reviewer) is None
 assert s.jobs()[0]['status']=='deferred' and not s.list('review_attempts')
 assert s.lease() is None
 with s.connect() as db:db.execute('UPDATE jobs SET eligible_at=0')
 with ThreadPoolExecutor(2) as ex:
  claims=list(ex.map(lambda _:s.lease(),range(2)))
 assert sum(x is not None for x in claims)==1


def test_legacy_budget_hold_with_consumed_attempt_never_recovers(tmp_path):
 s,r=seeded(tmp_path)
 with s.connect() as db:db.execute("UPDATE jobs SET status='hold',reason_code='DAILY_REVIEW_ATTEMPT_BUDGET_HOLD'")
 s.put('review_attempts',{'id':'consumed','run_id':r['id'],'admission_sha256':'a'*64,'status':'prepared'})
 assert s.lease() is None and s.jobs()[0]['status']=='hold'


def test_session_end_uses_source_time_and_no_time_stays_envelope(tmp_path):
 s=Store(tmp_path/'state');s.settings({'scopes':[str(tmp_path)]})
 def put(event,turn,stamp):
  spool(s,dict(hook_event_name=event,session_id='s',turn_id=turn,cwd=str(tmp_path),timestamp=stamp))
 put('UserPromptSubmit','new','2026-10-13T02:02:00Z')
 put('UserPromptSubmit','old','2026-10-13T02:01:00Z')
 put('SessionEnd',None,'2026-10-13T02:03:00Z');ingest(s)
 runs={r['turn_id']:r for r in s.list('runs')}
 assert runs['new']['last_event']=='SessionEnd'
 assert runs['old']['last_event']=='UserPromptSubmit'
 assert len(runs)==2 and s.list('session_envelopes')[0]['run_id']==runs['new']['id']
 # An older delayed event cannot erase a terminal status, including restart.
 put('PreToolUse','new','2026-10-13T02:02:30Z');ingest(Store(s.root))
 assert next(r for r in s.list('runs') if r['turn_id']=='new')['last_event']=='SessionEnd'
 spool(s,dict(hook_event_name='SessionEnd',session_id='s',cwd=str(tmp_path)));ingest(s)
 assert any(e['status']=='terminal_turn_unknown' for e in s.list('session_envelopes'))
 assert not s.jobs() # session envelope alone never dispatches a review


def test_parent_child_channels_share_execution_and_usage(tmp_path):
 from skill_observatory.runtime import register
 s=Store(tmp_path/'s');s.settings({'scopes':[str(tmp_path)]});p=tmp_path/'flow';p.mkdir();(p/'SKILL.md').write_text('flow')
 register(s,p,'owner')
 base=dict(hook_event_name='PreToolUse',turn_id='t',cwd=str(tmp_path),agent_id='child',tool_use_id='call',tool_input=str(p/'SKILL.md'))
 spool(s,{**base,'session_id':'parent'},'codex-hook')
 spool(s,{**base,'session_id':'child','parent_session_id':'parent'},'codex-subagent');ingest(s)
 assert len(s.list('runs'))==1 and len(s.list('capability_invocations'))==1
 assert s.list('runs')[0]['execution_session_id']=='child'
 assert s.list('runs')[0]['parent_session_id']=='parent'


def test_review_preflight_never_dispatches_index_only_run(tmp_path):
 s,r=seeded(tmp_path);calls=[]
 reviewer=CodexReviewer(None,lambda *a:calls.append(a),'s','s','max',tmp_path)
 process_one(s,reviewer)
 assert calls==[] and not s.list('review_attempts')
 assert s.jobs()[0]['reason_code']=='DIAGNOSTIC_FACTS_REQUIRED'


class FailedStream:
 def __init__(self):
  self.notifications=[];self.messages=queue.Queue()
  self.messages.put({'method':'thread/tokenUsage/updated','params':{'threadId':'thread','tokenUsage':{'total':{'totalTokens':1234}}}})
  self.messages.put({'method':'turn/completed','params':{'threadId':'thread','turn':{'id':'turn','status':'failed'}}})
 def request(self,method,params):
  if method=='thread/start':return {'thread':{'id':'thread'},'model':'synthetic'}
  return {'turn':{'id':'turn'}}
 def __enter__(self):return self
 def __exit__(self,*args):pass


def admission(*a):
 return {'ok':True,'maximum_verified_effort':'max','execution_mode':'background_tool_free',
  'tool_free_context_verified':True,'redacted_evidence_allowed':True,'evidence_capsule_versions':[1]}


def test_partial_usage_identity_and_failure_single_attempt(tmp_path,monkeypatch):
 s,r=seeded(tmp_path)
 monkeypatch.setattr('skill_observatory.reviewer.build_capsule',lambda *a:{'schema_version':1,'facts':{'status':'fixture'},'missing':[]})
 reviewer=CodexReviewer(FailedStream,admission,'synthetic','fixture','max',tmp_path)
 process_one(s,reviewer)
 attempts=s.list('review_attempts');assert len(attempts)==1
 a=attempts[0];assert a['thread_id']=='thread' and a['turn_id']=='turn'
 assert a['usage']['total']['totalTokens']==1234 and a['money'] is None
 assert a['status']=='failed_after_dispatch' and s.jobs()[0]['status']=='hold'
 assert s.lease() is None
 assert Store(s.root).list('review_attempts')==attempts


def test_background_requires_own_contract_and_data_permission(tmp_path,monkeypatch):
 s,r=seeded(tmp_path)
 monkeypatch.setattr('skill_observatory.reviewer.build_capsule',lambda *a:{'schema_version':1,'missing':[]})
 reviewer=CodexReviewer(None,lambda *a:{'ok':True,'maximum_verified_effort':'max'},'synthetic','fixture','max',tmp_path)
 with pytest.raises(ValueError,match='BACKGROUND_REVIEW_ADMISSION_CONTRACT_REQUIRED'):reviewer.review(s,r)
 assert not s.list('review_attempts')


def test_real_configured_reviewer_process_deadline_is_consumed(tmp_path):
 from skill_observatory.review_worker import IsolatedReviewer
 s,r=seeded(tmp_path);owner=tmp_path/'owner.py'
 owner.write_text("from time import sleep\nclass Reviewer:\n max_seconds=0.1\n def review(self,store,run):\n  store.put('review_attempts',{'id':'blocked','run_id':run['id'],'status':'prepared','admission_sha256':'synthetic','usage':None,'money':None})\n  sleep(30)\ndef make_reviewer():return Reviewer()\n")
 config=s.root/'reviewer.json';config.write_bytes(canonical({'owner_module':str(owner),'owner_sha256':digest(owner.read_bytes())}));config.chmod(0o600)
 started=time.monotonic()
 with pytest.raises(ValueError,match='PROCESS_DEADLINE_READBACK_REQUIRED'):IsolatedReviewer(.1,grace_seconds=2).review(s,r)
 assert time.monotonic()-started<5
 attempt=s.get('review_attempts','blocked');assert attempt['status']=='unknown_after_dispatch'
 assert attempt['usage'] is None and attempt['money'] is None


def test_late_readback_keeps_same_attempt_identity_and_usage(tmp_path):
 from skill_observatory.reviewer import reconcile_attempt
 s,r=seeded(tmp_path)
 s.put('review_attempts',{'id':'a','run_id':r['id'],'admission_sha256':'synthetic','thread_id':'thread','turn_id':'turn','status':'unknown_after_dispatch','usage':{'known':1234},'money':None})
 with pytest.raises(ValueError,match='IDENTITY_MISMATCH'):reconcile_attempt(s,'a',{'thread_id':'other','turn_id':'turn','terminal_status':'failed'})
 result=reconcile_attempt(s,'a',{'thread_id':'thread','turn_id':'turn','terminal_status':'failed','usage':{'known':2000}})
 assert result['usage']=={'known':2000} and result['money'] is None
 assert len(s.list('review_attempts'))==1 and s.lease() # readback does not dispatch the model


def test_late_newer_turn_rebinds_session_end_without_false_old_terminal(tmp_path):
 s=Store(tmp_path/'state');s.settings({'scopes':[str(tmp_path)]})
 def add(event,turn,time):spool(s,dict(hook_event_name=event,session_id='s',turn_id=turn,cwd=str(tmp_path),timestamp=time))
 add('UserPromptSubmit','old','2026-10-13T02:00:00Z');add('SessionEnd',None,'2026-10-13T02:03:00Z');ingest(s)
 add('UserPromptSubmit','new','2026-10-13T10:02:00+08:00');ingest(s)
 runs={r['turn_id']:r for r in s.list('runs')}
 assert runs['new']['last_event']=='SessionEnd' and runs['new']['terminal']
 assert runs['old']['status']=='evidence_pending' and not runs['old']['terminal']
