import json
from pathlib import Path
import pytest
from skill_observatory.store import Store, canonical
from skill_observatory.capture import capture, replay, validate_capture, activate_capture


def setup(tmp_path):
    project=tmp_path/'private'/'a';project.mkdir(parents=True)
    store=Store(tmp_path/'state');store.settings({'scopes':[str(project.parent)]})
    source=project/'double';source.mkdir()
    (source/'run.py').write_text('import json, sys\nv=json.load(sys.stdin)\nassert type(v) is int\nprint(json.dumps(v*2))\n')
    (source/'command.json').write_text(json.dumps({'entrypoint':'run.py','inputs':'integer','result':'integer doubled','permissions':['pure_json'],'positive':[{'input':3,'expected':6}],'negative':[{'input':'bad'}]}))
    h=store.artifact(canonical({'case':'actually tested doubling','result':6}))
    spec={'name':'double','owner':'test-owner','purpose':'Reusable integer conversion','background':'Repeated validated fixture','successful':True,'reusable':True,'source_path':str(source),'origin':{'session_id':'root','turn_id':'turn','project':str(project),'scenario':'test transformation','evidence_sha256':h}}
    return store,project,source,spec


def test_capture_install_cross_project_replay_and_drift(tmp_path):
    s,p,source,spec=setup(tmp_path)
    r=capture(s,spec,auto=True)
    assert r['status']=='active' and r['validation']['positive_passed']==1
    sibling=p.parent/'b';sibling.mkdir()
    result=replay(s,r['capability_id'],4,sibling,'real-context','turn-2','canary: next project','invocation-1')
    assert result['result']==8 and result['acceptance']=='unverified'
    assert capture(s,spec,auto=True)==r
    cap=s.get('capability_catalog',r['capability_id']);(Path(cap['path'])/'run.py').write_text('print(1)')
    with pytest.raises(ValueError,match='DRIFT'):replay(s,cap['id'],4,sibling,'s','t','canary: drift','i2')
    with pytest.raises(ValueError,match='OUTSIDE_SCOPE'):replay(s,cap['id'],4,tmp_path/'outside','s','t','test','i')


def test_failure_nonreusable_and_owner_overlap(tmp_path):
    s,p,source,spec=setup(tmp_path)
    failed={**spec,'name':'failed','successful':False}
    assert capture(s,failed,auto=True)['reason_code']=='SUCCESS_EVIDENCE_REQUIRED'
    assert capture(s,{**spec,'name':'one-off','reusable':False},auto=True)['status']=='no_change'
    active=capture(s,spec,auto=True)
    overlap={**spec,'origin':{**spec['origin'],'turn_id':'next-turn'}}
    assert capture(s,overlap,auto=True)['capability_id']==active['capability_id']


def test_counterexample_and_private_source_guard(tmp_path):
    s,p,source,spec=setup(tmp_path)
    (source/'run.py').write_text('import json,sys\nprint(json.dumps(6))\n')
    r=capture(s,spec,auto=True)
    assert r['validation']['reason_code']=='COUNTEREXAMPLE_FAILED'
    with pytest.raises(ValueError,match='VALIDATION_REQUIRED'):activate_capture(s,r['id'])
    s2,p2,source2,spec2=setup(tmp_path/'other')
    spec2['background']='api_key=sk-do-not-store1234567'
    with pytest.raises(ValueError,match='SENSITIVE'):capture(s2,spec2)
    assert not s2.list('captures')


def test_effectful_code_and_missing_origin_cannot_be_auto_installed(tmp_path):
    s,p,source,spec=setup(tmp_path)
    (source/'run.py').write_text('import os\nprint(6)\n')
    r=capture(s,spec,auto=True)
    assert r['validation']['reason_code']=='PURE_JSON_IMPORT_REJECTED'
    with pytest.raises(ValueError,match='ORIGIN_FIELD_REQUIRED'):capture(s,{**spec,'origin':{'project':str(p)}})


def test_skill_creation_requires_root_reviewed_forward_cases(tmp_path):
    from skill_observatory.capture import accept_skill_forward,retire_capability
    s,p,source,spec=setup(tmp_path)
    (source/'command.json').unlink();(source/'run.py').unlink()
    (source/'SKILL.md').write_text('---\nname: flow\ndescription: Select the appropriate metadata check.\n---\nCheck required fields, retain unknown gaps.\n')
    r=capture(s,spec,auto=True)
    assert r['status']=='hold' and r['validation']['reason_code']=='INDEPENDENT_FORWARD_SKILL_TEST_REQUIRED'
    forward={'package_sha256':r['manifest']['package_sha256'],'reviewed_by_root':'root','owner':spec['owner'],'trusted_source':'user-owned','scope':str(p.parent),'permissions':['read_only'],
             'positive':{'session_id':'independent','turn_id':'forward1','status':'passed','input_sha256':s.artifact(b'fixture positive input'),'result_sha256':s.artifact(b'fixture actual output')},
             'negative':{'session_id':'independent','turn_id':'forward2','status':'passed','input_sha256':s.artifact(b'fixture counterexample'),'result_sha256':s.artifact(b'fixture correctly refused')}}
    bad={**forward,'reviewed_by_root':'worker'}
    with pytest.raises(ValueError,match='ROOT_REVIEW'):accept_skill_forward(s,r['id'],bad)
    assert accept_skill_forward(s,r['id'],forward)['status']=='validated'
    activated=activate_capture(s,r['id']);cap=s.get('capability_catalog',activated['capability_id'])
    assert cap['kind']=='skill' and cap['permissions']==['read_only']
    retire_capability(s,cap['id'],'superseded owner procedure')
    from skill_observatory.capabilities import discover
    assert cap['id'] not in [x['id'] for x in discover(s,'double',p)]


def test_update_keeps_birth_and_owner_but_revalidates_new_version(tmp_path):
    s,p,source,spec=setup(tmp_path)
    initial=capture(s,spec,auto=True);old=s.get('capability_catalog',initial['capability_id'])
    (source/'run.py').write_text('import json, sys\nv=json.load(sys.stdin)\nassert type(v) is int\nprint(json.dumps(v*3))\n')
    cmd=json.loads((source/'command.json').read_text());cmd['positive'][0]['expected']=9;(source/'command.json').write_text(json.dumps(cmd))
    update={**spec,'update_capability_id':old['id'],'origin':{**spec['origin'],'turn_id':'update-turn'}}
    newer=capture(s,update,auto=True);cap=s.get('capability_catalog',newer['capability_id'])
    assert cap['id']==old['id'] and cap['version_id']!=old['version_id']
    assert cap['born_at']==old['born_at'] and cap['origin']==old['origin']
    assert replay(s,cap['id'],4,p,'s2','t2','canary: updated version','i')['result']==12
    assert len(s.list('capability_versions'))==2


def test_historical_backfill_binds_frozen_version_without_reverting_owner(tmp_path):
    s,p,source,spec=setup(tmp_path)
    initial=capture(s,spec,auto=True)
    (source/'run.py').write_text('import json, sys\nv=json.load(sys.stdin)\nassert type(v) is int\nprint(json.dumps(v*3))\n')
    cmd=json.loads((source/'command.json').read_text());cmd['positive'][0]['expected']=9
    (source/'command.json').write_text(json.dumps(cmd))
    update={**spec,'update_capability_id':initial['capability_id'],'origin':{**spec['origin'],'turn_id':'update-turn'}}
    newer=capture(s,update,auto=True)
    before=s.get('capability_catalog',newer['capability_id'])
    versions=s.list('capability_versions')
    backfill={**spec,'existing_capability_id':initial['capability_id'],'existing_version_id':initial['version_id'],
              'origin':{**spec['origin'],'turn_id':'backfill-turn'}}
    r=capture(s,backfill)
    assert r['version_id']==initial['version_id'] and r['status']=='existing'
    assert s.get('capability_catalog',before['id'])==before
    assert s.list('capability_versions')==versions
    assert capture(s,backfill)==r
    with pytest.raises(ValueError,match='VERSION_CAPABILITY_MISMATCH'):
        capture(s,{**backfill,'existing_version_id':'missing','origin':{**spec['origin'],'turn_id':'bad-version'}})
    with pytest.raises(ValueError,match='REQUIRES_EXISTING_OWNER'):
        capture(s,{**spec,'existing_version_id':initial['version_id']})
    outside={**backfill,'historical_backfill':True,'origin':{**spec['origin'],'turn_id':'scratch-history','project':str(tmp_path/'scratch')}}
    scoped_receipt=capture(s,outside)
    assert scoped_receipt['origin']['project']==str(tmp_path/'scratch')
    assert scoped_receipt['scope']==str(p.parent)
    assert s.settings()['scopes']==[str(p.parent)]
    assert s.get('capability_catalog',before['id'])==before
    from skill_observatory.capabilities import discover
    assert not discover(s,'double',tmp_path/'scratch')
    with pytest.raises(ValueError,match='OUTSIDE_SCOPE'):
        capture(s,{**outside,'historical_backfill':False})
    with pytest.raises(ValueError,match='METADATA_ONLY'):
        capture(s,outside,auto=True)
    with pytest.raises(ValueError,match='OWNER_VERSION_MISMATCH'):
        capture(s,{**outside,'owner':'other-owner'})
