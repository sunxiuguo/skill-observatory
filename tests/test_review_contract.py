import pytest
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
