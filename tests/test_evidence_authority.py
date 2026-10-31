"""Current authorization and exact invocation identity are consumption gates."""
from contextlib import contextmanager
import json
import queue
import pytest

from test_evidence_recovery import fixture
from skill_observatory.evidence import (
    attach_evidence, build_capsule, build_selected_evidence, evidence_plan,
)
from skill_observatory.reviewer import CodexReviewer, reconcile_attempt
from skill_observatory.store import Store, canonical


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


@pytest.mark.parametrize('mismatch', ['agent_id', 'cwd', 'session_id', 'turn_id', 'evidence_ids', 'origin'])
def test_other_invocation_cannot_supply_observed_version_even_from_cached_plan(tmp_path, mismatch):
    s, run, facts = fixture(tmp_path)
    assert evidence_plan(s, run['id'])[0]['observed_version_ids'] == [facts['version_id']]
    invocation = s.list('capability_invocations')[0]
    changed = {'agent_id': 'other-child', 'cwd': str(tmp_path / 'other-project'),
               'session_id': 'other-session', 'turn_id': 'other-turn', 'evidence_ids': [], 'origin': 'activation_canary'}
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


def late_case(tmp_path, versioned=True):
    s, run, facts = fixture(tmp_path)
    (build_selected_evidence if versioned else attach_evidence)(s, facts)
    run = s.get('runs', run['id'])
    attempt = {'id': 'late', 'run_id': run['id'], 'admission_sha256': 'synthetic',
               'thread_id': 'thread', 'turn_id': 'turn', 'status': 'unknown_after_dispatch',
               'capsule_sha256': s.artifact(canonical(build_capsule(s, run))),
               'usage': None, 'money': None}
    review = {'schema_version': 1, 'review_id': 'rv_' + run['id'], 'run_id': run['id'],
              'skill_id': None, 'skill_package_sha256': None, 'attribution': 'unknown',
              'coverage': {'tools': 'partial', 'outcome': 'unverified'},
              'outcome': {'status': 'unverified', 'source': 'runtime_only'},
              'findings': [], 'decision': 'HOLD', 'missing': ['SYNTHETIC'],
              'evidence_manifest_sha256': s.artifact(canonical(run)), 'reviewer_version': 'codex-review-v2'}
    readback = {'thread_id': 'thread', 'turn_id': 'turn', 'terminal_status': 'completed',
                'usage': {'known': 123}, 'texts': [json.dumps(review)]}
    return s, run, attempt, readback


@pytest.mark.parametrize('versioned', [False, True])
def test_late_readback_rechecks_scope_and_restores_without_dispatch(tmp_path, versioned):
    s, run, attempt, readback = late_case(tmp_path, versioned)
    s.put('review_attempts', attempt)
    jobs = s.jobs(); attached = s.get('run_evidence', run['id'])
    s.settings({'scopes': []}); s = Store(s.root)
    with pytest.raises(ValueError, match='OUTSIDE_SCOPE'):
        reconcile_attempt(s, attempt['id'], readback)
    stored = s.get('review_attempts', attempt['id'])
    assert stored['status'] == 'terminal_readback' and stored['usage'] == readback['usage']
    assert stored['reason_code'] == 'OUTSIDE_SCOPE' and stored['money'] is None
    assert s.read_artifact(stored['output_sha256']) and s.jobs() == jobs
    assert not s.list('reviews') and s.get('run_evidence', run['id']) == attached
    s.settings({'scopes': [str(tmp_path)]})
    result = reconcile_attempt(Store(s.root), attempt['id'], readback)
    assert result['status'] == 'reviewed' and len(s.list('review_attempts')) == 1
    assert 'reason_code' not in s.get('review_attempts', attempt['id'])
    assert reconcile_attempt(s, attempt['id'], readback) == result


@pytest.mark.parametrize('drift,reason', [
    ('policy', 'EVIDENCE_SOURCE_BINDING_DRIFT'),
    ('actor', 'EVIDENCE_VERSION_NOT_OBSERVED'),
    ('frozen', 'REVIEW_CAPSULE_DRIFT'),
    ('missing', 'REVIEW_CAPSULE_BINDING_REQUIRED'),
    ('corrupt', 'ARTIFACT_CORRUPT'),
])
def test_late_readback_rejects_changed_or_unbound_frozen_input(tmp_path, drift, reason):
    s, run, attempt, readback = late_case(tmp_path)
    if drift == 'policy':s.settings({'diagnostic_scopes': [str(tmp_path)]})
    elif drift == 'actor':
        invocation = s.list('capability_invocations')[0]
        s.put('capability_invocations', {**invocation, 'agent_id': 'other'})
    elif drift == 'frozen':attempt['capsule_sha256'] = s.artifact(b'{}')
    elif drift == 'missing':attempt.pop('capsule_sha256')
    else:(s.root / 'artifacts' / attempt['capsule_sha256']).write_bytes(b'corrupt')
    s.put('review_attempts', attempt); jobs = s.jobs()
    with pytest.raises(ValueError, match=reason):reconcile_attempt(Store(s.root), attempt['id'], readback)
    assert s.jobs() == jobs and not s.list('reviews') and len(s.list('review_attempts')) == 1
    assert s.get('review_attempts', attempt['id'])['output_sha256']


@pytest.mark.parametrize('drift,reason', [('scope', 'OUTSIDE_SCOPE'), ('policy', 'EVIDENCE_SOURCE_BINDING_DRIFT')])
def test_completed_model_turn_rechecks_input_before_accepting(tmp_path, drift, reason):
    s, run, _, readback = late_case(tmp_path)
    class Client:
        def __init__(self):
            self.notifications = []; self.messages = queue.Queue()
            self.messages.put({'method': 'item/completed', 'params': {'item': {'type': 'agentMessage', 'text': readback['texts'][0]}}})
            self.messages.put({'method': 'turn/completed', 'params': {'turn': {'status': 'completed'}}})
        def request(self, method, params):
            return {'thread': {'id': 'thread'}, 'model': 'fixture'} if method == 'thread/start' else {'turn': {'id': 'turn'}}
        def __enter__(self):return self
        def __exit__(self, *args):
            s.settings({'scopes': []} if drift == 'scope' else {'diagnostic_scopes': [str(tmp_path)]})
    admission = lambda *args: {'ok': True, 'maximum_verified_effort': 'max', 'execution_mode': 'background_tool_free',
                              'tool_free_context_verified': True, 'redacted_evidence_allowed': True, 'evidence_capsule_versions': [2]}
    with pytest.raises(ValueError, match=reason):CodexReviewer(Client, admission, 'fixture', 'fixture', 'max', tmp_path).review(s, run)
    attempt = s.list('review_attempts')[0]
    assert attempt['status'] == 'failed_after_dispatch' and attempt['terminal_status'] == 'completed'
    assert attempt['reason_code'] == reason and attempt['output_sha256']
    assert not s.list('reviews') and s.jobs()[0]['status'] != 'completed'


def test_late_readback_rechecks_at_atomic_acceptance_boundary(tmp_path, monkeypatch):
    import skill_observatory.reviewer as reviewer
    s, run, attempt, readback = late_case(tmp_path)
    s.put('review_attempts', attempt); jobs = s.jobs()
    original = reviewer.accept_review
    def revoke_before_accept(*args, **kwargs):
        s.settings({'scopes': []})
        return original(*args, **kwargs)
    monkeypatch.setattr(reviewer, 'accept_review', revoke_before_accept)
    with pytest.raises(ValueError, match='OUTSIDE_SCOPE'):reconcile_attempt(s, attempt['id'], readback)
    assert not s.list('reviews') and s.jobs() == jobs
