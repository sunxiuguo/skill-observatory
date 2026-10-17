import pytest
import json
import queue
from skill_observatory.store import Store,canonical
from skill_observatory.runtime import spool,ingest,process_one,accept_review,tick


def test_generation_schema_refuses_names_unobserved_and_cross_version_tuples(tmp_path):
 from jsonschema import validate,ValidationError
 from skill_observatory.reviewer import review_schema
 s=Store(tmp_path/'state');s.settings({'scopes':[str(tmp_path)]})
 spool(s,dict(hook_event_name='Stop',session_id='s',turn_id='t',cwd=str(tmp_path)));ingest(s)
 triage=process_one(s)
 receipt={k:v for k,v in triage.items() if k not in {'id','created_at','status','reason_code'}}
 a={'skill_id':'sk_first','package_sha256':'a'*64,'attribution':'verified_read'}
 b={'skill_id':'sk_second','package_sha256':'b'*64,'attribution':'explicit_loaded'}
 schema=review_schema({'attributions':[a,b]})
 validate(receipt,schema)
 exact={**receipt,'skill_id':a['skill_id'],'skill_package_sha256':a['package_sha256'],'attribution':a['attribution']}
 validate(exact,schema)
 for wrong in [{'skill_id':'skill-evolution-loop'}, {'skill_package_sha256':'b'*64}, {'attribution':'executed_script'}]:
  with pytest.raises(ValidationError):validate({**exact,**wrong},schema)
 with pytest.raises(ValidationError):validate(exact,review_schema({'attributions':[]}))

def test_review_cannot_claim_missing_independent_truth(tmp_path):
 s=Store(tmp_path/'s');s.settings({'scopes':[str(tmp_path)]})
 spool(s,{'hook_event_name':'Stop','session_id':'s','turn_id':'t','cwd':str(tmp_path)})
 ingest(s);r=process_one(s)
 data={k:v for k,v in r.items() if k not in {'id','status','reason_code','created_at'}}
 data['reviewer_version']='trusted-v1'
 data['evidence_manifest_sha256']=s.artifact(canonical(s.list('runs')[0]))
 data['outcome']={'source':'domain_oracle','status':'accepted'}
 with pytest.raises(ValueError,match='INDEPENDENT_OUTCOME'):accept_review(s,data,'trusted-v1')
 data['outcome']={'source':'runtime_only','status':'unverified'}
 assert accept_review(s,data,'trusted-v1')['status']=='reviewed'

def test_pause_automatic_review_retains_queue(tmp_path):
 s=Store(tmp_path/'s');s.settings({'scopes':[str(tmp_path)],'automatic_review':False})
 spool(s,{'hook_event_name':'Stop','session_id':'s','turn_id':'t','cwd':str(tmp_path)})
 tick(s)
 assert s.jobs()[0]['status']=='queued'
 assert not s.list('reviews')


@pytest.mark.parametrize('forged_truth',[False,True])
def test_provider_schema_mapping_keeps_local_truth_gate(tmp_path,monkeypatch,forged_truth):
 from skill_observatory.reviewer import CodexReviewer
 s=Store(tmp_path/'state');s.settings({'scopes':[str(tmp_path)]})
 spool(s,dict(hook_event_name='Stop',session_id='s',turn_id='t',cwd=str(tmp_path)));ingest(s)
 triage=process_one(s);run=s.list('runs')[0]
 receipt={k:v for k,v in triage.items() if k not in {'id','created_at','status','reason_code'}}
 receipt.update(reviewer_version='codex-review-v2',evidence_manifest_sha256=s.artifact(canonical(run)))
 if forged_truth:receipt['outcome']={'source':'domain_oracle','status':'accepted'}
 class Client:
  def __init__(self):
   self.notifications=[];self.messages=queue.Queue()
   self.messages.put({'method':'item/completed','params':{'threadId':'thread','turnId':'turn','item':{'type':'agentMessage','text':json.dumps(receipt)}}})
   self.messages.put({'method':'turn/completed','params':{'threadId':'thread','turnId':'turn','turn':{'status':'completed'}}})
  def request(self,method,params):
   if method=='thread/start':return {'thread':{'id':'thread'},'model':'synthetic'}
   assert 'outputSchema' not in params
   return {'turn':{'id':'turn'}}
  def __enter__(self):return self
  def __exit__(self,*args):pass
 monkeypatch.setattr('skill_observatory.reviewer.build_capsule',lambda *args:{'schema_version':1,'missing':[],'facts':{'synthetic':True}})
 admission=lambda *args:{'ok':True,'maximum_verified_effort':'max','execution_mode':'background_tool_free','tool_free_context_verified':True,'redacted_evidence_allowed':True,'evidence_capsule_versions':[1]}
 reviewer=CodexReviewer(Client,admission,'synthetic','synthetic','max',tmp_path,native_output_schema=False)
 if forged_truth:
  with pytest.raises(ValueError,match='INDEPENDENT_OUTCOME'):reviewer.review(s,run)
 else:assert reviewer.review(s,run)['status']=='reviewed'


@pytest.mark.parametrize('transport_failure',['eof','failed_turn','terminal_only'])
def test_reviewer_persists_transport_failure_without_waiting_for_generic_timeout(tmp_path,monkeypatch,transport_failure):
 from skill_observatory.reviewer import CodexReviewer
 s=Store(tmp_path/'state');s.settings({'scopes':[str(tmp_path)]})
 spool(s,dict(hook_event_name='Stop',session_id='s',turn_id='t',cwd=str(tmp_path)));ingest(s);run=s.list('runs')[0]
 class Client:
  def __init__(self):
   self.notifications=[];self.messages=queue.Queue();self.wire_receipts=[{'phase':'awaiting_headers','forwarded':True,'secret':'never store'}]
   if transport_failure=='eof':self.messages.put({'_transport':'APP_SERVER_EOF'})
   elif transport_failure=='failed_turn':
    self.messages.put({'method':'error','params':{'threadId':'thread','turnId':'turn','error':{'codexErrorInfo':'HttpConnectionFailed','message':'private details'},'willRetry':False}})
    self.messages.put({'method':'turn/completed','params':{'threadId':'thread','turnId':'turn','turn':{'status':'failed'}}})
   else:self.messages.put({'method':'turn/completed','params':{'threadId':'thread','turnId':'turn','turn':{'status':'failed','error':{'message':'Stream closed before response.completed; secret=private'}}}})
  def request(self,method,params):return {'thread':{'id':'thread'},'model':'synthetic'} if method=='thread/start' else {'turn':{'id':'turn'}}
  def __enter__(self):return self
  def __exit__(self,*args):pass
 monkeypatch.setattr('skill_observatory.reviewer.build_capsule',lambda *args:{'schema_version':1,'missing':[],'facts':{'synthetic':True}})
 admission=lambda *args:{'ok':True,'maximum_verified_effort':'max','execution_mode':'background_tool_free','tool_free_context_verified':True,'redacted_evidence_allowed':True,'evidence_capsule_versions':[1]}
 reviewer=CodexReviewer(Client,admission,'synthetic','synthetic','max',tmp_path)
 with pytest.raises(ValueError,match='APP_SERVER_EXITED_BEFORE_TERMINAL|REVIEW_TURN_FAILED'):reviewer.review(s,run)
 attempt=s.list('review_attempts')[0]
 assert attempt['transport']==[{'phase':'awaiting_headers','forwarded':True}]
 assert attempt['wall_seconds']<10
 if transport_failure=='failed_turn':assert attempt['last_error_code']=='HttpConnectionFailed' and attempt['server_will_retry'] is False
 if transport_failure=='terminal_only':assert attempt['failure_diagnostics']['category']=='stream_incomplete'
 assert 'private' not in json.dumps(attempt) and 'secret' not in json.dumps(attempt)


@pytest.mark.parametrize('message,category',[
 ('Rate limit reached: private bearer token', 'rate_limit'),
 ('Maximum context length exceeded at /private/path', 'context_limit'),
 ('Failed to deserialize upstream response with secret details', 'response_parse'),
 ('Unclassified provider detail private', 'unclassified'),
])
def test_failure_projection_keeps_identity_without_sensitive_prose(message,category):
 from skill_observatory.reviewer import failure_diagnostics
 from skill_observatory.store import digest
 value={'message':message,'codexErrorInfo':'other'}
 result=failure_diagnostics(value)
 assert result=={'category':category,'error_sha256':digest(canonical(value))}
 assert 'private' not in json.dumps(result) and 'secret' not in json.dumps(result)
