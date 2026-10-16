"""Public package ingress mechanics. Real owner transactions run separately."""
import shutil
import pytest
from skill_observatory.store import Store
from skill_observatory.packages import snapshot_package
from skill_observatory.installations import grant_package_owner
from skill_observatory.owner_installers import prepare_package_change
from skill_observatory.owner_adapters import OwnerReceiptPipeline,bind_proposal
from test_pipeline import add_case


class ProposalOwner:
    def __init__(self,proposal):self.proposal=proposal
    def package_available(self):return True
    def call(self,operation,id_):
        assert operation=='show'
        return {'package_proposal':self.proposal}


def setup_package(tmp_path):
    s=Store(tmp_path/'state')
    case=add_case(tmp_path,s,'package',files={'refs/guide.txt':b'old reference','script.py':b'print(1)'})
    root=case['target'].parent;tree=tmp_path/'candidate';shutil.copytree(root,tree);(tree/'refs/guide.txt').write_bytes(b'corrected reference')
    before=snapshot_package(s,root);after=snapshot_package(s,tree)
    g=grant_package_owner(s,root,'package-grant',s.artifact(b'isolated synthetic human-grant fixture'),before,after,['refs/guide.txt'])
    owner=ProposalOwner({'operation':'package_replace','target_root':str(root),'candidate_tree':str(tree),'before_manifest':before,'after_manifest':after,'changed_files':['refs/guide.txt']})
    request=prepare_package_change(s,{'id':'request','owner':'skill-evolution-loop','target_root':str(root),'parent_package':before,'candidate_package':after,'changed_files':['refs/guide.txt'],'authority_id':g['id']},owner)
    value={'review_id':case['review']['id'],'owner_incident_id':'package-fixture','package_request_id':request['id']}
    return s,case,owner,request,value


def test_reference_only_change_uses_same_pipeline_and_waits_without_auto_install(tmp_path):
    s,case,owner,request,value=setup_package(tmp_path)
    assert request['status']=='prepared'
    bind_proposal(s,value,owner);pipeline=OwnerReceiptPipeline(s,owner)
    assert pipeline.tick()['state']=='experiment_ready'
    result=pipeline.tick();assert result['state']=='candidate_ready'
    candidate=s.get('candidates',result['candidate_id'])
    assert candidate['parent_sha256']==candidate['candidate_sha256']
    assert candidate['parent_package']!=candidate['candidate_package'] and candidate['package_request_id']=='request'
    assert pipeline.tick() is None and not s.list('installations') and s.settings()['auto_promote'] is False
    assert case['target'].read_bytes()==b'parent fixture'


def test_unknown_owner_capability_and_candidate_tree_drift_refuse(tmp_path):
    s,case,owner,request,value=setup_package(tmp_path)
    owner.package_available=lambda:False
    with pytest.raises(ValueError,match='TRANSACTION_UNAVAILABLE'):bind_proposal(s,value,owner)
    owner.package_available=lambda:True
    from pathlib import Path
    (Path(owner.proposal['candidate_tree'])/'refs/guide.txt').write_bytes(b'unapproved change')
    with pytest.raises(ValueError,match='PROPOSAL_DRIFT'):bind_proposal(s,value,owner)
    assert not s.list('candidates') and not s.list('owner_proposals')
