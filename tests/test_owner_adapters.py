"""Receipt bridge mechanics; synthetic fixtures never establish task improvement."""
from pathlib import Path
import pytest
from skill_observatory.store import Store,digest,canonical
from skill_observatory.owner_adapters import OwnerReceiptPipeline,bind_proposal,bind_evaluation
from test_pipeline import add_case


class OriginalOwner:
    def __init__(self):self.proposals={};self.calls=[]
    def call(self,operation,id):
        self.calls.append((operation,id));assert operation=='show'
        return {'proposal':self.proposals[id]}


def prepared(tmp_path,store,owner,suffix):
    case=add_case(tmp_path,store,suffix);candidate=tmp_path/(suffix+'-candidate.txt');candidate.write_bytes(b'candidate fixture')
    owner.proposals[suffix]={'schema_version':2,'operation':'replace','target':str(case['target'].resolve()),
        'before_sha256':digest(case['target'].read_bytes()),'candidate':str(candidate),'candidate_sha256':digest(candidate.read_bytes())}
    return case,{'review_id':case['review']['id'],'owner_incident_id':suffix,'cost_attempt_ids':['actual-owner-cost-id-fixture']}


def test_waiting_owner_input_does_not_spend_attempts_or_block_other_review(tmp_path):
    s=Store(tmp_path/'state');owner=OriginalOwner();a,va=prepared(tmp_path,s,owner,'a');b,vb=prepared(tmp_path,s,owner,'b')
    p=OwnerReceiptPipeline(s,owner)
    assert p.tick()['state']=='experiment_ready'
    assert p.tick()['state']=='experiment_ready'
    assert p.tick() is None
    assert all(row['attempts']==0 for row in s.list('experiments'))
    first=bind_proposal(s,vb,owner);assert bind_proposal(s,vb,owner)==first
    assert p.tick()['state']=='candidate_ready'
    stages={x['review_id']:x for x in s.list('experiments')}
    assert stages[a['review']['id']]['attempts']==0 and stages[b['review']['id']]['attempts']==1
    # No measured evaluation / receipts: do not invoke an evaluator or spend a final set.
    assert p.tick() is None and not s.list('evaluation_attempts')


def test_owner_proposal_drift_and_unknown_side_effects_do_not_replay(tmp_path):
    s=Store(tmp_path/'state');owner=OriginalOwner();case,value=prepared(tmp_path,s,owner,'a');p=OwnerReceiptPipeline(s,owner)
    stage=p.tick();bind_proposal(s,value,owner)
    owner.proposals['a']['candidate_sha256']='0'*64
    assert p.tick()['state']=='held'
    attempts=s.list('experiments')[0]['attempts'];owner.proposals['a']['candidate_sha256']=digest(b'candidate fixture')
    assert bind_proposal(s,value,owner)
    assert p.tick() is None and s.list('experiments')[0]['attempts']==attempts
    assert case['target'].read_bytes()==b'parent fixture'


def test_evaluation_binding_refuses_wrong_arm_and_allows_only_missing_receipt_enrichment(tmp_path):
    s=Store(tmp_path/'state');owner=OriginalOwner();case,value=prepared(tmp_path,s,owner,'a');p=OwnerReceiptPipeline(s,owner)
    p.tick();bind_proposal(s,value,owner);p.tick();candidate=s.list('candidates')[0]
    s.put('protocols',{'id':'protocol','arm_files':{'parent':{'SKILL.md':candidate['parent_sha256']},'candidate':{'SKILL.md':'0'*64}}})
    s.put('evaluations',{'id':'evaluation','protocol_id':'protocol'})
    value={'candidate_id':candidate['id'],'evaluation_id':'evaluation'}
    with pytest.raises(ValueError,match='FINAL_CANDIDATE_HASH_MISMATCH'):bind_evaluation(s,value)
    protocol=s.get('protocols','protocol');protocol['arm_files']['candidate']['SKILL.md']=candidate['candidate_sha256'];s.put('protocols',protocol)
    first=bind_evaluation(s,value);assert first['domain_receipt'] is None and p.tick() is None
    value['domain_receipt']={'signature':'signed-by-domain-owner-fixture'}
    bind_evaluation(s,value)
    with pytest.raises(ValueError,match='OWNER_EVALUATION_INPUT_COLLISION'):
        bind_evaluation(s,{**value,'domain_receipt':{'signature':'changed'}})
    assert not s.list('evaluation_attempts')


def test_activation_waits_for_a_valid_accepted_receipt(tmp_path):
    s=Store(tmp_path/'state');p=OwnerReceiptPipeline(s)
    s.put('task_receipts',{'id':'forged','installation_id':'i','run_id':'r','status':'accepted','signature':'invalid'})
    assert p._accepted_run('i') is None
    s.put('installations',{'id':'i','candidate_id':'c'})
    with pytest.raises(ValueError,match='ACTIVATION_TASK_RECEIPT_REQUIRED'):p.activation_run('c','i')


def test_disabled_automatic_promotion_leaves_ready_installation_unclaimed(tmp_path):
    s=Store(tmp_path/'state');owner=OriginalOwner();case,value=prepared(tmp_path,s,owner,'a');p=OwnerReceiptPipeline(s,owner)
    s.put('experiments',{'id':'ready-install','review_id':case['review']['id'],'state':'promotion_ready','attempts':0})
    assert s.settings()['auto_promote'] is False
    assert p.tick() is None
    assert s.get('experiments','ready-install')['attempts']==0
    assert not owner.calls and not s.list('installations')
    assert case['target'].read_bytes()==b'parent fixture'
