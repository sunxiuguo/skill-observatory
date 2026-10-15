import pytest
import json
import queue
from skill_observatory.store import Store,canonical
from skill_observatory.runtime import spool,ingest,process_one,accept_review,tick

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
