import pytest
from skill_observatory.store import Store
from skill_observatory.capabilities import register_capability,record_usage,project_lifecycle,discover


def fixture(tmp_path):
    caller=tmp_path/'projects';caller.mkdir();package=tmp_path/'owner';package.mkdir()
    (package/'SKILL.md').write_text('---\nname: owner\ndescription: Audit receipts.\n---\nRules.\n')
    s=Store(tmp_path/'state');s.settings({'scopes':[str(caller)]})
    c=register_capability(s,package,'owner',scope=caller)
    h=s.artifact(b'actual output fixture')
    return s,caller,package,c,h


def test_immutable_identity_versions_origin_and_movement(tmp_path):
    s,p,path,c,h=fixture(tmp_path)
    assert c['born_at'] is None and c['origin'] is None
    assert register_capability(s,path,'owner',scope=p)==c
    (path/'SKILL.md').write_text((path/'SKILL.md').read_text()+'changed')
    newer=register_capability(s,path,'owner',scope=p)
    assert newer['first_seen_at']==c['first_seen_at'] and newer['version_id']!=c['version_id']
    assert len(s.list('capability_versions'))==2
    moved=tmp_path/'moved';path.rename(moved)
    assert register_capability(s,moved,'owner',scope=p,capability_id=c['id'])['id']==c['id']
    with pytest.raises(ValueError,match='OWNER_CONFLICT'):register_capability(s,moved,'other-owner',scope=p,capability_id=c['id'])


def test_logical_invocations_observation_dedup_attempts_and_stage_counts(tmp_path):
    s,p,path,c,h=fixture(tmp_path)
    r={'capability_id':c['id'],'version_id':c['version_id'],'cwd':str(p),'session_id':'s','turn_id':'t','invocation_id':'tool','source':'hook','event_id':'ev','stage':'mentioned'}
    first=record_usage(s,r);assert record_usage(s,r)==first
    read={**r,'source':'transcript','stage':'verified_read','evidence_sha256':h}
    record_usage(s,read)
    record_usage(s,{**r,'source':'cli','stage':'executed','attempt_id':'try1','status':'failed','evidence_sha256':h})
    record_usage(s,{**r,'source':'cli','event_id':'retry','stage':'executed','attempt_id':'try2','status':'completed','evidence_sha256':h})
    d=project_lifecycle(s);assert len(d['capability_invocations'])==1
    assert d['capability_catalog'][0]['usage_counts']['executed']==1
    assert d['capability_invocations'][0]['attempts']==['try1','try2']
    with pytest.raises(ValueError,match='EVENT_ID_CONFLICT'):record_usage(s,{**r,'stage':'selected'})
    with pytest.raises(ValueError,match='STAGE_EVIDENCE'):record_usage(s,{**r,'event_id':'accept','stage':'accepted'})
    found=discover(s,'receipts',p)
    assert len(found)==1 and not discover(s,'receipts',tmp_path/'other')
    assert found[0]['usage_counts']['executed']==1
    assert found[0]['invocation_count']==1


def test_version_and_actor_do_not_cross_attribute(tmp_path):
    s,p,path,c,h=fixture(tmp_path)
    r={'capability_id':c['id'],'version_id':c['version_id'],'cwd':str(p),'session_id':'s','turn_id':'t','invocation_id':'same','source':'hook','event_id':'ev','stage':'selected'}
    record_usage(s,r);record_usage(s,{**r,'agent_id':'child','event_id':'child'})
    assert len(s.list('capability_invocations'))==2
    with pytest.raises(ValueError,match='VERSION_CAPABILITY'):record_usage(s,{**r,'version_id':'missing'})
    with pytest.raises(ValueError,match='OUTSIDE_SCOPE'):register_capability(s,path,'owner',scope=tmp_path)
