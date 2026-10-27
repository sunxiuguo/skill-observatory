"""Current authorization and exact invocation identity are consumption gates."""
from contextlib import contextmanager
import pytest

from test_evidence_recovery import fixture
from skill_observatory.evidence import (
    attach_evidence, build_capsule, build_selected_evidence, evidence_plan,
)
from skill_observatory.reviewer import CodexReviewer
from skill_observatory.store import Store


@pytest.mark.parametrize('versioned', [False, True])
def test_revoked_scope_blocks_built_facts_before_admission_and_preserves_history(tmp_path, versioned):
    s, run, facts = fixture(tmp_path)
    build = build_selected_evidence if versioned else attach_evidence
    receipt = build(s, facts)
    current = s.get('runs', run['id'])
    jobs = s.jobs()
    attempts = s.list('review_attempts')
    artifact = s.read_artifact(receipt['capsule_sha256'])
    s.settings({'scopes': []})
    restarted = Store(s.root)

    def forbidden(*args):
        raise AssertionError('revoked facts must not reach admission or transport')

    reviewer = CodexReviewer(forbidden, forbidden, 'fixture', 'fixture', 'max', tmp_path)
    with pytest.raises(ValueError, match='OUTSIDE_SCOPE'):
        reviewer.review(restarted, current)
    with pytest.raises(ValueError, match='OUTSIDE_SCOPE'):
        build(restarted, facts)
    assert restarted.get('run_evidence', run['id']) == receipt
    assert restarted.read_artifact(receipt['capsule_sha256']) == artifact
    assert restarted.jobs() == jobs and restarted.list('review_attempts') == attempts
    restarted.settings({'scopes': [str(tmp_path)]})
    assert build(restarted, facts) == receipt
    assert not build_capsule(restarted, current)['missing']


def test_current_policy_drift_withholds_built_v2_facts_without_rewriting_receipt(tmp_path):
    s, run, facts = fixture(tmp_path)
    receipt = build_selected_evidence(s, facts)
    s.settings({'diagnostic_scopes': [str(tmp_path)]})
    capsule = build_capsule(Store(s.root), s.get('runs', run['id']))
    assert capsule['facts'] is None and 'EVIDENCE_SOURCE_BINDING_DRIFT' in capsule['missing']
    assert s.get('run_evidence', run['id']) == receipt
    s.settings({'diagnostic_scopes': []})
    assert not build_capsule(s, s.get('runs', run['id']))['missing']


@pytest.mark.parametrize('mismatch', ['agent_id', 'cwd', 'session_id', 'turn_id', 'evidence_ids'])
def test_other_invocation_cannot_supply_observed_version_even_from_cached_plan(tmp_path, mismatch):
    s, run, facts = fixture(tmp_path)
    assert evidence_plan(s, run['id'])[0]['observed_version_ids'] == [facts['version_id']]
    invocation = s.list('capability_invocations')[0]
    changed = {'agent_id': 'other-child', 'cwd': str(tmp_path / 'other-project'),
               'session_id': 'other-session', 'turn_id': 'other-turn', 'evidence_ids': []}
    s.put('capability_invocations', {**invocation, mismatch: changed[mismatch]})
    s = Store(s.root)
    plan = evidence_plan(s, run['id'])[0]
    assert plan['observed_version_ids'] == []
    assert 'OBSERVED_CAPABILITY_VERSION_REQUIRED' in plan['missing']
    with pytest.raises(ValueError, match='EVIDENCE_VERSION_NOT_OBSERVED'):
        build_selected_evidence(s, facts)
    assert s.get('run_evidence', run['id']) is None
    assert s.jobs()[0]['status'] == 'hold' and not s.list('review_attempts')
    s.put('capability_invocations', invocation)
    assert evidence_plan(s, run['id'])[0]['observed_version_ids'] == [facts['version_id']]
    receipt = build_selected_evidence(s, facts)
    assert receipt['resumed_pre_dispatch_jobs'] == 1
    assert not build_capsule(s, s.get('runs', run['id']))['missing']


@pytest.mark.parametrize('versioned', [False, True])
def test_legacy_built_cross_actor_facts_are_withheld_at_consume(tmp_path, versioned):
    s, run, facts = fixture(tmp_path)
    receipt = (build_selected_evidence if versioned else attach_evidence)(s, facts)
    invocation = s.list('capability_invocations')[0]
    s.put('capability_invocations', {**invocation, 'agent_id': 'other-child'})
    capsule = build_capsule(Store(s.root), s.get('runs', run['id']))
    assert capsule['facts'] is None and 'EVIDENCE_VERSION_NOT_OBSERVED' in capsule['missing']
    assert s.get('run_evidence', run['id']) == receipt
    assert not s.list('review_attempts')


@pytest.mark.parametrize('revoke_at', ['admission', 'thread_start'])
def test_scope_revoked_during_setup_never_reaches_model_turn(tmp_path, revoke_at):
    s, run, facts = fixture(tmp_path)
    build_selected_evidence(s, facts)
    calls = []

    def admission(*args):
        if revoke_at == 'admission':s.settings({'scopes': []})
        return {'ok': True, 'maximum_verified_effort': 'max',
                'execution_mode': 'background_tool_free', 'tool_free_context_verified': True,
                'redacted_evidence_allowed': True, 'evidence_capsule_versions': [2]}

    @contextmanager
    def client():
        calls.append('client')
        class Client:
            def request(self, method, params):
                calls.append(method)
                assert method == 'thread/start', 'revoked facts reached a model turn'
                s.settings({'scopes': []})
                return {'thread': {'id': 'synthetic-thread'}, 'model': 'fixture'}
        yield Client()

    with pytest.raises(ValueError, match='OUTSIDE_SCOPE'):
        CodexReviewer(client, admission, 'fixture', 'fixture', 'max', tmp_path).review(s, s.get('runs', run['id']))
    assert calls == ([] if revoke_at == 'admission' else ['client', 'thread/start'])
    attempts = s.list('review_attempts')
    assert not attempts if revoke_at == 'admission' else (
        len(attempts) == 1 and not attempts[0].get('turn_id') and attempts[0]['reason_code'] == 'OUTSIDE_SCOPE')
