"""Versioned local facts: no synthetic goals, natural origin or invented success."""
import json
import pytest
from test_evidence_recovery import fixture as recovery_fixture
from skill_observatory.evidence import build_selected_evidence,evidence_plan,build_capsule


def fixture(tmp_path, owner='owner'):
    return recovery_fixture(tmp_path, owner=owner, versioned=True)


@pytest.mark.parametrize('identity', ['valid', 'foreign_run_identity', None])
def test_v2_readback_checks_fact_owner_even_when_internal_hashes_match(tmp_path, identity):
    from skill_observatory.reviewer import reconcile_attempt
    from skill_observatory.store import Store, canonical
    s, run, facts = fixture(tmp_path)
    selected = build_selected_evidence(s, facts)
    run = s.get('runs', run['id'])
    plan = evidence_plan(s, run['id'])[0]
    capsule = build_capsule(s, run)
    jobs = s.jobs()
    if identity != 'valid':
        # Simulate inconsistent historical internal state, including matching
        # ledger hashes. This is not a supported factual-ingress operation.
        payload = json.loads(s.read_artifact(selected['capsule_sha256']))
        payload['run_id'] = identity
        malformed = s.artifact(canonical(payload))
        s.put('run_evidence', {**selected, 'capsule_sha256': malformed})
        s.put('evidence_builds', {**plan, 'selection_sha256': malformed})
        capsule['facts']['run_id'] = identity
    attempt = {
        'id': 'readback', 'run_id': run['id'], 'admission_sha256': 'fixture',
        'thread_id': 'review_thread', 'turn_id': 'review_turn',
        'status': 'unknown_after_dispatch', 'capsule_sha256': s.artifact(canonical(capsule)),
        'usage': None, 'money': None,
    }
    s.put('review_attempts', attempt)
    review = {
        'schema_version': 1, 'review_id': 'rv_' + run['id'], 'run_id': run['id'],
        'skill_id': None, 'skill_package_sha256': None, 'attribution': 'unknown',
        'coverage': {'tools': 'partial', 'outcome': 'unverified'},
        'outcome': {'status': 'unverified', 'source': 'runtime_only'},
        'findings': [], 'decision': 'HOLD', 'missing': ['FIXTURE_READBACK'],
        'evidence_manifest_sha256': s.artifact(canonical(run)),
        'reviewer_version': 'codex-review-v2',
    }
    readback = {
        'thread_id': attempt['thread_id'], 'turn_id': attempt['turn_id'],
        'terminal_status': 'completed', 'usage': {'known': 1}, 'texts': [json.dumps(review)],
    }
    restarted = Store(s.root)
    current = build_capsule(restarted, run)
    if identity == 'valid':
        assert not current['missing'] and current['facts']['run_id'] == run['id']
        assert reconcile_attempt(restarted, attempt['id'], readback)['status'] == 'reviewed'
        assert len(s.list('reviews')) == 1
        return
    assert current['facts'] is None
    assert current['missing'] == ['EVIDENCE_SOURCE_BINDING_DRIFT', 'DIAGNOSTIC_FACTS_REQUIRED']
    with pytest.raises(ValueError, match='EVIDENCE_SOURCE_BINDING_DRIFT'):
        reconcile_attempt(restarted, attempt['id'], readback)
    held = s.get('review_attempts', attempt['id'])
    assert held['status'] == 'terminal_readback' and held['money'] is None
    assert held['capsule_sha256'] == attempt['capsule_sha256'] and held['usage'] == {'known': 1}
    assert not s.list('reviews') and s.jobs() == jobs
    # Restoring source facts cannot rewrite the already-dispatched snapshot.
    s.put('run_evidence', selected)
    s.put('evidence_builds', plan)
    assert not build_capsule(restarted, run)['missing']
    with pytest.raises(ValueError, match='REVIEW_CAPSULE_DRIFT'):
        reconcile_attempt(restarted, attempt['id'], readback)
    assert s.get('review_attempts', attempt['id'])['capsule_sha256'] == attempt['capsule_sha256']
    assert not s.list('reviews') and s.jobs() == jobs


@pytest.mark.parametrize('owner', ['Project skills owner', '团队 Skill owner'])
def test_registered_text_owner_can_supply_version_bound_facts(tmp_path, owner):
    s,run,facts=fixture(tmp_path, owner=owner)
    receipt=build_selected_evidence(s,facts)
    assert receipt['resumed_pre_dispatch_jobs']==1
    capsule=build_capsule(s,s.get('runs',run['id']))
    assert capsule['facts']['owner']==owner and not capsule['missing']
    assert build_selected_evidence(s,facts)==receipt
    assert not s.list('review_attempts')


@pytest.mark.parametrize('field,value,reason', [
    ('owner', 'Other project skills', 'EVIDENCE_OWNER_VERSION_MISMATCH'),
    ('owner', ' ', 'EVIDENCE_OWNER_VERSION_REQUIRED'),
    ('version_id', 'version with spaces', 'EVIDENCE_OWNER_VERSION_MISMATCH'),
])
def test_text_owner_does_not_relax_identity_checks(tmp_path, field, value, reason):
    s,run,facts=fixture(tmp_path, owner='Project skills owner')
    facts[field]=value
    with pytest.raises(ValueError,match=reason):build_selected_evidence(s,facts)
    assert s.get('run_evidence',run['id']) is None
    assert s.jobs()[0]['status']=='hold' and not s.list('review_attempts')


def test_selection_build_is_change_driven_private_and_version_bound(tmp_path):
    s,run,facts=fixture(tmp_path)
    first=evidence_plan(s,run['id'])[0];assert first['status']=='awaiting_native_selection'
    assert first['source_class']=='unknown' and first['actual_terminal']['truth']=='runtime_only_unverified'
    assert evidence_plan(s,run['id'])[0]==first
    before=len(s.list('review_attempts'))
    r=build_selected_evidence(s,facts);assert r['resumed_pre_dispatch_jobs']==1
    assert build_selected_evidence(s,facts)==r
    capsule=build_capsule(s,s.get('runs',run['id']))
    assert capsule['schema_version']==2 and not capsule['missing']
    assert 'local_refs' not in capsule['facts']
    assert capsule['facts']['package_digest']==s.get('capability_versions',facts['version_id'])['package_sha256']
    assert len(s.list('review_attempts'))==before
    changed={**facts,'goal':'Another unsupported rewrite'}
    with pytest.raises(ValueError,match='ALREADY_SELECTED'):build_selected_evidence(s,changed)


@pytest.mark.parametrize('failure',['secret','natural','environment','reference'])
def test_builder_rejects_sensitive_unbound_or_invented_inputs(tmp_path,failure):
    s,run,facts=fixture(tmp_path)
    if failure=='secret':facts['goal']='use password=not-for-transport'
    if failure=='natural':facts['source_class']='natural'
    if failure=='environment':facts['environment_binding']={'model':'made-up','effort':'max','harness':None,'runtime':None,'evidence_sha256':None,'missing':[]}
    if failure=='reference':facts['artifact_refs']=[{'kind':'output','sha256':'0'*64}]
    with pytest.raises((ValueError,FileNotFoundError)):build_selected_evidence(s,facts)


def test_v2_capsule_cannot_borrow_v1_transport_data_authority(tmp_path):
    from skill_observatory.reviewer import CodexReviewer
    s,run,facts=fixture(tmp_path);build_selected_evidence(s,facts)
    def forbidden_transport():raise AssertionError('unapproved v2 transport must not be created')
    admission=lambda *args:{'ok':True,'maximum_verified_effort':'max','execution_mode':'background_tool_free',
                            'tool_free_context_verified':True,'redacted_evidence_allowed':True,'evidence_capsule_versions':[1]}
    before=len(s.list('review_attempts'))
    with pytest.raises(ValueError,match='EVIDENCE_CAPSULE_DATA_AUTHORITY_REQUIRED'):
        CodexReviewer(forbidden_transport,admission,'fixture','fixture','max',tmp_path).review(s,s.get('runs',run['id']))
    assert len(s.list('review_attempts'))==before


def test_one_ineligible_historical_run_does_not_block_current_fact_work(tmp_path):
    s,run,facts=fixture(tmp_path)
    outside={**run,'id':'outside','cwd':'/outside/authorized/scope','updated_at':'2099-01-01T00:00:00+00:00'}
    s.put('runs',{**outside,'terminal':True});s.put('runs',{**run,'terminal':True})
    rows=evidence_plan(s,limit=2)
    assert any(r['run_id']=='outside' and r['status']=='blocked' and r['missing']==['OUTSIDE_SCOPE'] for r in rows)
    assert any(r['run_id']==run['id'] and r['status']=='awaiting_native_selection' for r in rows)
    with pytest.raises(ValueError,match='OUTSIDE_SCOPE'):evidence_plan(s,'outside')


def test_changed_policy_retires_old_pending_work_without_losing_evidence(tmp_path):
    from skill_observatory.proactive import evidence_actions
    from skill_observatory.store import Store
    s,run,facts=fixture(tmp_path)
    old=evidence_plan(s,run['id'])[0]
    s.settings({'diagnostic_scopes':[str(tmp_path)]})
    with pytest.raises(ValueError,match='EVIDENCE_SELECTION_SOURCE_DRIFT'):
        build_selected_evidence(s,facts)
    facts={**facts,'source_fingerprint':evidence_plan(s,run['id'])[0]['source_fingerprint']}
    built=build_selected_evidence(s,facts)
    current=evidence_plan(s,run['id'])[0]
    assert current['id']!=old['id'] and current['status']=='built'
    retired=s.get('evidence_builds',old['id'])
    assert retired['status']=='superseded' and retired['superseded_by']==current['id']
    assert retired['source_fingerprint']==old['source_fingerprint']
    assert not evidence_actions(Store(s.root))
    assert s.get('run_evidence',run['id'])==built and not s.list('review_attempts')


def test_new_source_stays_pending_and_old_built_receipt_is_preserved(tmp_path):
    from skill_observatory.proactive import evidence_actions
    from skill_observatory.runtime import spool,ingest
    s,run,facts=fixture(tmp_path)
    built=build_selected_evidence(s,facts)
    old=evidence_plan(s,run['id'])[0]
    spool(s,dict(hook_event_name='Stop',session_id='s',turn_id='t',cwd=str(tmp_path),tool_use_id='new-source'))
    ingest(s)
    current=evidence_plan(s,run['id'])[0]
    assert current['id']!=old['id'] and current['status']=='awaiting_native_selection'
    assert [r['id'] for r in evidence_actions(s)]==[current['id']]
    assert s.get('evidence_builds',old['id'])==old
    assert s.get('run_evidence',run['id'])==built
    assert 'EVIDENCE_CAPSULE_RUN_DRIFT' in build_capsule(s,s.get('runs',run['id']))['missing']
    assert not s.list('review_attempts')


def test_policy_return_reactivates_exact_pending_work(tmp_path):
    from skill_observatory.proactive import evidence_actions
    s,run,facts=fixture(tmp_path)
    old=evidence_plan(s,run['id'])[0]
    s.settings({'diagnostic_scopes':[str(tmp_path)]})
    other=evidence_plan(s,run['id'])[0]
    s.settings({'diagnostic_scopes':[]})
    active=evidence_plan(s,run['id'])[0]
    assert active['id']==old['id'] and active['status']=='awaiting_native_selection'
    assert s.get('evidence_builds',other['id'])['status']=='superseded'
    assert [r['id'] for r in evidence_actions(s)]==[old['id']]
    assert not s.list('review_attempts')


def test_returned_pending_policy_is_visible_ahead_of_historical_build(tmp_path):
    from skill_observatory.semantic_progress import project
    s,run,facts=fixture(tmp_path)
    old=evidence_plan(s,run['id'])[0]
    s.settings({'diagnostic_scopes':[str(tmp_path)]})
    facts={**facts,'source_fingerprint':evidence_plan(s,run['id'])[0]['source_fingerprint']}
    build_selected_evidence(s,facts)
    s.settings({'diagnostic_scopes':[]})
    evidence_plan(s,run['id'])
    with s.connect() as db:db.execute('DELETE FROM jobs')
    progress=project(s)
    assert progress['first_blocker']=='DIAGNOSTIC_FACTS_REQUIRED'
    assert progress['blocking_item']['id']==old['id']


def test_supersession_failure_rolls_back_new_and_retired_work(tmp_path,monkeypatch):
    s,run,facts=fixture(tmp_path)
    old=evidence_plan(s,run['id'])[0]
    before=s.list('evidence_builds')
    s.settings({'diagnostic_scopes':[str(tmp_path)]})
    put=s.put
    def fail_retirement(kind,value,db=None):
        if kind=='evidence_builds' and value.get('status')=='superseded':
            raise OSError('interrupted retirement')
        return put(kind,value,db)
    monkeypatch.setattr(s,'put',fail_retirement)
    with pytest.raises(OSError,match='interrupted retirement'):evidence_plan(s,run['id'])
    assert s.list('evidence_builds')==before
    assert s.get('evidence_builds',old['id'])==old and not s.list('review_attempts')


def test_historical_build_cannot_return_another_policy_capsule(tmp_path):
    s,run,facts=fixture(tmp_path)
    first=build_selected_evidence(s,facts)
    s.settings({'diagnostic_scopes':[str(tmp_path)]})
    second_facts={**facts,'source_fingerprint':evidence_plan(s,run['id'])[0]['source_fingerprint']}
    second=build_selected_evidence(s,second_facts)
    assert first['capsule_sha256']!=second['capsule_sha256']
    s.settings({'diagnostic_scopes':[]})
    with pytest.raises(ValueError,match='EVIDENCE_BUILD_READBACK_REQUIRED'):
        build_selected_evidence(s,facts)
    assert s.get('run_evidence',run['id'])==second
    assert not s.list('review_attempts')


def test_unrecognized_work_status_is_not_hidden_as_superseded(tmp_path):
    from skill_observatory.proactive import evidence_actions
    s,run,facts=fixture(tmp_path)
    item=evidence_plan(s,run['id'])[0]
    s.put('evidence_builds',{**item,'status':'readback_required'})
    assert evidence_actions(s)[0]['status']=='readback_required'


def test_self_review_surfaces_version_bound_work_behind_unresolved_history(tmp_path):
    from skill_observatory.proactive import evidence_actions
    from skill_observatory.store import Store
    s=Store(tmp_path/'state')
    for lane,versions in [('gap',[]),('bound',['version'])]:
        for i in range(6):
            s.put('evidence_builds',{'id':f'{lane}_{i}','run_id':f'run_{lane}_{i}',
                'source_fingerprint':f'source_{lane}_{i}','status':'awaiting_native_selection',
                'missing':['TASK_GOAL_REQUIRED']+([] if versions else ['OBSERVED_CAPABILITY_VERSION_REQUIRED']),
                'observed_version_ids':versions,'created_at':f'2026-10-{10 if lane=="gap" else 11:02}T00:00:0{i}+00:00'})
    for status in ('built','superseded'):
        s.put('evidence_builds',{'id':status,'status':status,'created_at':'2000'})
    before=s.list('evidence_builds')
    first=evidence_actions(s)
    assert [r['id'] for r in first]==['gap_0','bound_0','gap_1','bound_1']
    assert evidence_actions(Store(s.root))==first
    assert s.list('evidence_builds')==before
    assert not s.list('review_attempts') and not s.list('installations')
    for id_ in ('bound_0','bound_1'):
        s.put('evidence_builds',{**s.get('evidence_builds',id_),'status':'built'})
    assert [r['id'] for r in evidence_actions(s)]==['gap_0','bound_2','gap_1','bound_3']


@pytest.mark.parametrize('versions',[[],['version']])
def test_self_review_fills_action_limit_from_the_available_lane(tmp_path,versions):
    from skill_observatory.proactive import evidence_actions
    from skill_observatory.store import Store
    s=Store(tmp_path/'state')
    for i in range(5):
        s.put('evidence_builds',{'id':str(i),'run_id':str(i),'source_fingerprint':str(i),
            'status':'awaiting_native_selection','missing':['TASK_GOAL_REQUIRED'],
            'observed_version_ids':versions,'created_at':'2026-10-10'})
    assert [r['id'] for r in evidence_actions(s)]==['0','1','2','3']


@pytest.mark.parametrize('drift', ['source', 'policy'])
@pytest.mark.parametrize('already_built', [False, True])
def test_selected_facts_cannot_rebind_to_changed_source_after_restart(tmp_path, drift, already_built):
    from skill_observatory.runtime import spool, ingest
    from skill_observatory.store import Store
    s, run, facts = fixture(tmp_path)
    old_plan = evidence_plan(s, run['id'])[0]
    original = build_selected_evidence(s, facts) if already_built else None
    if drift == 'source':
        spool(s, dict(hook_event_name='Interrupt', session_id='s', turn_id='t', cwd=str(tmp_path)))
        ingest(s)
    else:
        s.settings({'diagnostic_scopes': [str(tmp_path)]})
    s = Store(s.root)
    jobs, attempts = s.jobs(), s.list('review_attempts')
    with pytest.raises(ValueError, match='EVIDENCE_SELECTION_SOURCE_DRIFT'):
        build_selected_evidence(s, facts)
    current = evidence_plan(s, run['id'])[0]
    assert current['source_fingerprint'] != facts['source_fingerprint']
    assert current['status'] == 'awaiting_native_selection' and not current.get('selection_sha256')
    assert s.get('run_evidence', run['id']) == original
    if already_built:
        assert s.get('evidence_builds', old_plan['id'])['selection_sha256']
        assert build_capsule(s, s.get('runs', run['id']))['facts'] is None
    assert s.jobs() == jobs and s.list('review_attempts') == attempts
    if drift == 'source':
        assert current['actual_terminal']['event'] == 'Interrupt'
        # A newly reviewed selection may describe the new terminal, retaining
        # the previous receipt and attempts rather than replaying either.
        fresh = {**facts, 'source_fingerprint': current['source_fingerprint'],
                 'result': {'status': 'interrupted'},
                 'steps': [{'event_id': current['actual_terminal']['event_id'],
                            'fact': 'The source records an interrupted turn.'}]}
        accepted = build_selected_evidence(s, fresh)
        capsule = build_capsule(s, s.get('runs', run['id']))
        assert not capsule['missing'] and capsule['facts']['result']['status'] == 'interrupted'
        assert build_selected_evidence(Store(s.root), fresh) == accepted
        if original:assert s.read_artifact(original['capsule_sha256'])
        assert s.list('review_attempts') == attempts


def test_builder_requires_explicit_reviewed_source_fingerprint(tmp_path):
    s, run, facts = fixture(tmp_path)
    facts.pop('source_fingerprint')
    with pytest.raises(ValueError, match='EVIDENCE_SELECTION_INVALID'):
        build_selected_evidence(s, facts)
    assert s.get('run_evidence', run['id']) is None
    assert s.jobs()[0]['status'] == 'hold' and not s.list('review_attempts')


@pytest.mark.parametrize('same_selection', [False, True])
def test_concurrent_selections_commit_one_consistent_receipt(tmp_path, monkeypatch, same_selection):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    from skill_observatory import evidence
    from skill_observatory.store import Store
    s, run, facts = fixture(tmp_path)
    barrier = threading.Barrier(2)
    original_plan = evidence.evidence_plan

    def concurrent_plan(*args, **kwargs):
        planned = original_plan(*args, **kwargs)
        barrier.wait(timeout=10)
        return planned

    monkeypatch.setattr(evidence, 'evidence_plan', concurrent_plan)
    choices = [facts, facts if same_selection else {**facts, 'goal': 'A different reviewed goal'}]

    def submit(choice):
        try:return build_selected_evidence(Store(s.root), choice)
        except ValueError as error:return str(error)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, choices))
    accepted = [r for r in results if isinstance(r, dict)]
    refused = [r for r in results if isinstance(r, str)]
    assert len(accepted) == (2 if same_selection else 1)
    assert refused == ([] if same_selection else ['EVIDENCE_BUILD_ALREADY_SELECTED'])
    current = Store(s.root)
    plan = original_plan(current, run['id'])[0]
    receipt = current.get('run_evidence', run['id'])
    assert plan['status'] == 'built' and plan['selection_sha256'] == receipt['capsule_sha256']
    assert all(r == receipt for r in accepted)
    capsule = build_capsule(current, current.get('runs', run['id']))
    assert not capsule['missing'] and capsule['facts']['goal'] in [c['goal'] for c in choices]
    assert current.jobs()[0]['status'] == 'queued' and not current.list('review_attempts')


def test_build_commit_failure_does_not_attach_or_resume_jobs(tmp_path, monkeypatch):
    from skill_observatory.store import Store
    s, run, facts = fixture(tmp_path)
    before, jobs = evidence_plan(s, run['id'])[0], s.jobs()
    original_put = Store.put

    def fail_build(store, kind, value, db=None):
        if kind == 'evidence_builds' and value.get('status') == 'built':
            raise OSError('injected build commit failure')
        return original_put(store, kind, value, db)

    with monkeypatch.context() as patch:
        patch.setattr(Store, 'put', fail_build)
        with pytest.raises(OSError, match='injected build commit failure'):
            build_selected_evidence(s, facts)
    current = Store(s.root)
    assert current.get('run_evidence', run['id']) is None
    assert evidence_plan(current, run['id'])[0] == before and current.jobs() == jobs
    assert not current.list('review_attempts')
    receipt = build_selected_evidence(current, facts)
    assert receipt['resumed_pre_dispatch_jobs'] == 1
    assert build_selected_evidence(Store(s.root), facts) == receipt
