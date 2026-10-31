"""Canary/evaluation origins cannot lend their reads to another execution."""
import json
import pytest

from test_evidence_recovery import fixture
from skill_observatory.capabilities import record_usage
from skill_observatory.evidence import build_capsule, build_selected_evidence, evidence_plan
from skill_observatory.runtime import ingest, spool
from skill_observatory.store import Store


@pytest.mark.parametrize('versioned', [False, True])
def test_legacy_merged_read_requires_same_origin_observation(tmp_path, versioned):
    from skill_observatory.evidence import attach_evidence
    s, run, facts = fixture(tmp_path)
    receipt = (build_selected_evidence if versioned else attach_evidence)(s, facts)
    observation = s.list('capability_observations')[0]
    # Reproduce historical merging: the aggregate still says user_run while
    # its only verified-read observation came from a canary.
    s.put('capability_observations', {**observation, 'origin': 'activation_canary'})
    restarted = Store(s.root)
    legacy = {k: v for k, v in observation.items() if k not in {'id', 'invocation_record_id'}}
    with pytest.raises(ValueError, match='INVOCATION_ORIGIN_CONFLICT'):
        record_usage(restarted, {**legacy, 'origin': 'activation_canary'})
    capsule = build_capsule(restarted, restarted.get('runs', run['id']))
    assert capsule['facts'] is None and 'EVIDENCE_VERSION_NOT_OBSERVED' in capsule['missing']
    with pytest.raises(ValueError, match='EVIDENCE_VERSION_NOT_OBSERVED'):
        (build_selected_evidence if versioned else attach_evidence)(restarted, facts)
    assert restarted.get('run_evidence', run['id']) == receipt
    assert not restarted.list('review_attempts')
    s.put('capability_observations', observation)
    assert not build_capsule(s, s.get('runs', run['id']))['missing']


@pytest.mark.parametrize('run_origin,use_origin', [
    ('user_run', 'activation_canary'), ('activation_canary', 'user_run'),
    ('review', 'user_run'), ('user_run', 'review'),
    ('user_run', 'user_run'), ('activation_canary', 'activation_canary'),
])
def test_factual_build_and_attribution_require_matching_origins(tmp_path, run_origin, use_origin):
    s, _, facts = fixture(tmp_path)
    cap = s.list('capability_catalog')[0]
    spool(s, dict(hook_event_name='Stop', session_id='other', turn_id='t', cwd=str(tmp_path), origin=run_origin))
    ingest(s)
    run = next(r for r in s.list('runs') if r['session_id'] == 'other')
    record_usage(s, dict(capability_id=cap['id'], version_id=cap['version_id'], cwd=str(tmp_path),
                        session_id='other', turn_id='t', invocation_id='read', stage='verified_read',
                        source='fixture', event_id='other-read', evidence_sha256=facts['receipt_sha256'], origin=use_origin))
    selected = {**facts, 'run_id': run['id'], 'steps': [{'event_id': run['event_ids'][0], 'fact': 'Terminal observed.'}]}
    observed = evidence_plan(s, run['id'])[0]['observed_version_ids']
    if run_origin == use_origin:
        assert observed == [facts['version_id']]
        build_selected_evidence(s, selected)
        assert not build_capsule(s, s.get('runs', run['id']))['missing']
    else:
        assert observed == [] and s.get('runs', run['id'])['attributions'] == []
        with pytest.raises(ValueError, match='EVIDENCE_VERSION_NOT_OBSERVED'):
            build_selected_evidence(s, selected)
        assert s.get('run_evidence', run['id']) is None and not s.list('review_attempts')


def test_usage_origin_cannot_change_across_channels_or_stages(tmp_path):
    s, run, facts = fixture(tmp_path)
    existing = s.list('capability_observations')[0]
    use = {k: v for k, v in existing.items() if k not in {'id', 'invocation_record_id'}}
    before = s.list('capability_invocations')
    with pytest.raises(ValueError, match='INVOCATION_ORIGIN_CONFLICT'):
        record_usage(s, {**use, 'origin': 'activation_canary', 'source': 'other-channel', 'event_id': 'canary'})
    assert s.list('capability_invocations') == before
    assert s.list('capability_observations') == [existing]
    # Matching origins may still deduplicate observations across channels.
    accepted = {**use, 'origin': 'user_run', 'source': 'other-channel', 'event_id': 'user'}
    record_usage(s, accepted)
    assert record_usage(s, accepted) == s.list('capability_invocations')[0]
    assert len(s.list('capability_invocations')) == 1
    assert evidence_plan(s, run['id'])[0]['observed_version_ids'] == [facts['version_id']]


@pytest.mark.parametrize('origin', ['', None, []])
def test_invalid_usage_origin_does_not_create_observation(tmp_path, origin):
    s, _, _ = fixture(tmp_path)
    existing = s.list('capability_observations')[0]
    use = {k: v for k, v in existing.items() if k not in {'id', 'invocation_record_id'}}
    with pytest.raises(ValueError, match='INVALID_ORIGIN'):
        record_usage(s, {**use, 'origin': origin, 'event_id': 'invalid'})
    assert s.list('capability_observations') == [existing]


def test_synthetic_usage_metadata_is_retained_without_user_run_attribution(tmp_path):
    s, run, _ = fixture(tmp_path)
    existing = s.list('capability_observations')[0]
    use = {k: v for k, v in existing.items() if k not in {'id', 'invocation_record_id'}}
    record = record_usage(s, {**use, 'origin': 'synthetic', 'invocation_id': 'synthetic', 'event_id': 'synthetic'})
    assert record['origin'] == 'synthetic'
    # Only the original ordinary read may supply this user run's version.
    s.put('capability_observations', {**existing, 'origin': 'synthetic'})
    assert evidence_plan(s, run['id'])[0]['observed_version_ids'] == []


def test_ingest_quarantines_mixed_origin_without_changing_run_or_usage(tmp_path):
    s, run, facts = fixture(tmp_path)
    cap = s.list('capability_catalog')[0]
    before = s.get('runs', run['id'])
    invocations = s.list('capability_invocations')
    event = dict(hook_event_name='PostToolUse', session_id='s', turn_id='t', cwd=str(tmp_path),
                 origin='activation_canary', tool_use_id='canary',
                 capability_observations=[dict(capability_id=cap['id'], version_id=cap['version_id'], stage='verified_read')])
    spooled = spool(s, event, source='codex-desktop')
    raw = (s.root / 'spool' / (spooled['id'] + '.json')).read_bytes()
    assert ingest(s) == 0
    assert s.get('runs', run['id']) == before
    assert s.list('capability_invocations') == invocations
    assert (s.root / 'quarantine' / ('raw-' + spooled['id'] + '.json')).read_bytes() == raw
    refusal = json.loads((s.root / 'quarantine' / (spooled['id'] + '.json')).read_text())
    assert refusal['reason_code'] == 'RUN_ORIGIN_CONFLICT'
    # A later ordinary observation proceeds without replaying the canary.
    spool(s, {**event, 'origin': 'user_run', 'tool_use_id': 'ordinary'}, source='codex-desktop')
    assert ingest(s) == 1
    assert s.get('runs', run['id'])['origin'] == 'user_run'
    assert evidence_plan(s, run['id'])[0]['observed_version_ids'] == [facts['version_id']]
