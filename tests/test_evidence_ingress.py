"""All factual ingress preserves a reviewed selection and legacy recovery."""
import json
import pytest
from test_evidence_recovery import fixture
from skill_observatory import evidence
from skill_observatory.store import Store, canonical


def legacy(facts):
    return {k: v for k, v in facts.items() if k != 'source_fingerprint'}


@pytest.mark.parametrize('legacy_first', [False, True])
def test_legacy_import_cannot_replace_a_completed_selection(tmp_path, legacy_first):
    s, run, facts = fixture(tmp_path, versioned=True)
    other = {**legacy(facts), 'goal': 'A different locally selected goal'}
    if legacy_first:
        imported = evidence.attach_evidence(s, other)
    selected = evidence.build_selected_evidence(s, facts)
    before = evidence.evidence_plan(s, run['id'])[0]
    jobs = s.jobs()
    with pytest.raises(ValueError, match='EVIDENCE_BUILD_ALREADY_SELECTED'):
        evidence.attach_evidence(Store(s.root), other)
    assert s.get('run_evidence', run['id']) == selected
    assert evidence.evidence_plan(s, run['id'])[0] == before
    assert s.jobs() == jobs and not s.list('review_attempts')
    capsule = evidence.build_capsule(s, s.get('runs', run['id']))
    assert not capsule['missing'] and capsule['facts']['goal'] == facts['goal']
    assert evidence.build_selected_evidence(Store(s.root), facts) == selected
    exact = json.loads(s.read_artifact(selected['capsule_sha256']))
    assert evidence.attach_evidence(Store(s.root), exact) == selected
    if legacy_first:
        assert s.read_artifact(imported['capsule_sha256'])


def test_concurrent_legacy_import_cannot_overwrite_builder_commit(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    s, run, facts = fixture(tmp_path, versioned=True)
    barrier = threading.Barrier(2)
    attach = evidence.attach_evidence

    def concurrent_attach(*args, **kwargs):
        # The builder owns the write transaction here; legacy arrives before
        # that commit and must recheck the winner after acquiring its lock.
        barrier.wait(timeout=10)
        return attach(*args, **kwargs)

    def import_legacy():
        try:
            return evidence.attach_evidence(Store(s.root), {**legacy(facts), 'goal': 'Concurrent legacy goal'})
        except ValueError as error:
            return str(error)

    monkeypatch.setattr(evidence, 'attach_evidence', concurrent_attach)
    with ThreadPoolExecutor(max_workers=2) as pool:
        built = pool.submit(evidence.build_selected_evidence, Store(s.root), facts)
        imported = pool.submit(import_legacy)
        selected, refused = built.result(timeout=15), imported.result(timeout=15)
    assert refused == 'EVIDENCE_BUILD_ALREADY_SELECTED'
    current = Store(s.root)
    plan = evidence.evidence_plan(current, run['id'])[0]
    assert plan['selection_sha256'] == selected['capsule_sha256']
    assert current.get('run_evidence', run['id']) == selected
    assert current.jobs()[0]['status'] == 'queued' and not current.list('review_attempts')


def test_preexisting_receipt_drift_refuses_consumption_and_exact_restore_recovers(tmp_path):
    s, run, facts = fixture(tmp_path, versioned=True)
    selected = evidence.build_selected_evidence(s, facts)
    plan = evidence.evidence_plan(s, run['id'])[0]
    jobs = s.jobs()
    # Preserve a historically reachable mixed-ingress state, without using
    # the repaired write API to manufacture a fresh invalid overwrite.
    other_hash = s.artifact(canonical({**legacy(facts), 'goal': 'Historical mismatched receipt'}))
    s.put('run_evidence', {**selected, 'capsule_sha256': other_hash})
    capsule = evidence.build_capsule(s, s.get('runs', run['id']))
    assert capsule['facts'] is None
    assert 'EVIDENCE_BUILD_READBACK_REQUIRED' in capsule['missing']
    with pytest.raises(ValueError, match='EVIDENCE_BUILD_READBACK_REQUIRED'):
        evidence.build_selected_evidence(s, facts)
    exact = json.loads(s.read_artifact(selected['capsule_sha256']))
    restored = evidence.attach_evidence(Store(s.root), exact)
    assert restored['capsule_sha256'] == selected['capsule_sha256']
    assert restored['run_manifest_sha256'] == selected['run_manifest_sha256']
    assert restored['resumed_pre_dispatch_jobs'] == 0
    assert evidence.build_selected_evidence(Store(s.root), facts) == restored
    assert evidence.evidence_plan(s, run['id'])[0] == plan
    assert not evidence.build_capsule(s, s.get('runs', run['id']))['missing']
    assert s.read_artifact(other_hash) and s.jobs() == jobs and not s.list('review_attempts')


@pytest.mark.parametrize('drift', ['source', 'policy'])
def test_old_selection_does_not_claim_a_new_source_or_policy(tmp_path, drift):
    from skill_observatory.runtime import spool, ingest
    s, run, facts = fixture(tmp_path, versioned=True)
    selected = evidence.build_selected_evidence(s, facts)
    if drift == 'source':
        spool(s, dict(hook_event_name='Interrupt', session_id='s', turn_id='t', cwd=str(tmp_path)))
        ingest(s)
    else:
        s.settings({'diagnostic_scopes': [str(tmp_path)]})
    plan = evidence.evidence_plan(s, run['id'])[0]
    assert plan['source_fingerprint'] != facts['source_fingerprint']
    imported = evidence.attach_evidence(s, {**legacy(facts), 'goal': 'Facts reviewed for the new source or policy'})
    assert imported['capsule_sha256'] != selected['capsule_sha256']
    assert not evidence.build_capsule(s, s.get('runs', run['id']))['missing']
    assert evidence.evidence_plan(s, run['id'])[0] == plan
    assert s.read_artifact(selected['capsule_sha256']) and not s.list('review_attempts')
