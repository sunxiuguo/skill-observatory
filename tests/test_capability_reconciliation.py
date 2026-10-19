import copy

import pytest

from skill_observatory.capabilities import (
    discover, drift_actions, reconcile_capability, register_capability,
)
from skill_observatory.runtime import package_manifest
from skill_observatory.store import Store, canonical


def changed(tmp_path):
    store = Store(tmp_path / 'state')
    scope = tmp_path / 'project'; scope.mkdir()
    store.settings({'scopes': [str(scope)]})
    skill = tmp_path / 'flow'; skill.mkdir()
    (skill / 'SKILL.md').write_text('---\nname: flow\ndescription: Review CLI results\n---\nOld procedure\n')
    cap = register_capability(store, skill, 'existing owner', scope=str(scope))
    old = copy.deepcopy(store.get('capability_versions', cap['version_id']))
    (skill / 'SKILL.md').write_text('---\nname: flow\ndescription: Review CLI results\n---\nRead actual CLI help before selecting arguments\n')
    evidence = store.artifact(b'Root reviewed exact changed bytes and original owner receipt; engineering readback only.')
    spec = {'schema_version': 1, 'capability_id': cap['id'], 'owner': cap['owner'],
            'expected_version_id': cap['version_id'], 'package_sha256': package_manifest(skill)['package_sha256'],
            'evidence_sha256': evidence}
    return store, scope, skill, cap, old, spec


def test_explicit_reconciliation_preserves_history_and_does_not_certify_gain(tmp_path):
    s, scope, skill, cap, old, spec = changed(tmp_path)
    assert discover(s, 'flow', scope)[0]['eligible_for_reuse'] is False
    assert drift_actions(s)[0]['expected_version_id'] == cap['version_id']
    result = reconcile_capability(s, spec)
    current = s.get('capability_catalog', cap['id'])
    assert current['version_id'] != cap['version_id']
    assert current['status'] == 'registered'
    assert s.get('capability_versions', cap['version_id']) == old
    assert current['origin'] == cap['origin'] and current['born_at'] == cap['born_at']
    assert discover(s, 'flow', scope)[0]['freshness'] == 'verified_current'
    assert drift_actions(s) == []
    assert result['before_version_id'] == cap['version_id']
    assert result['claim'] == 'catalog_readback_only_not_activation_or_gain'
    assert not s.list('installations') and not s.list('task_receipts')
    assert reconcile_capability(s, spec) == result
    assert len(s.list('capability_reconciliations')) == 1


@pytest.mark.parametrize('change,reason', [
    ({'owner': 'another owner'}, 'CANONICAL_OWNER_CONFLICT'),
    ({'expected_version_id': 'ver_unknown'}, 'CAPABILITY_RECONCILIATION_CAS_MISMATCH'),
    ({'package_sha256': 'a' * 64}, 'CAPABILITY_READBACK_DRIFT'),
    ({'schema_version': True}, 'CAPABILITY_RECONCILIATION_INVALID'),
])
def test_wrong_identity_or_readback_never_advances_catalog(tmp_path, change, reason):
    s, _, _, cap, _, spec = changed(tmp_path)
    with pytest.raises(ValueError, match=reason):
        reconcile_capability(s, {**spec, **change})
    assert s.get('capability_catalog', cap['id']) == cap
    assert len(s.list('capability_versions')) == 1
    assert not s.list('capability_reconciliations')


def test_evidence_retirement_and_later_disk_drift_are_not_bypassed(tmp_path):
    s, _, skill, cap, _, spec = changed(tmp_path)
    with pytest.raises(ValueError, match='EVIDENCE_REQUIRED'):
        reconcile_capability(s, {**spec, 'evidence_sha256': s.artifact(b' ')})
    s.put('capability_catalog', {**cap, 'status': 'retired'})
    with pytest.raises(ValueError, match='SCOPE_HOLD'):
        reconcile_capability(s, spec)
    s.put('capability_catalog', cap)
    reconcile_capability(s, spec)
    (skill / 'SKILL.md').write_text('A third concurrent version')
    with pytest.raises(ValueError, match='READBACK_DRIFT'):
        reconcile_capability(s, spec)
    assert len(s.list('capability_versions')) == 2


def test_snapshot_refuses_content_changed_between_manifest_and_blob_read(tmp_path, monkeypatch):
    s, _, skill, cap, _, spec = changed(tmp_path)
    from skill_observatory import capabilities
    original = capabilities._manifest
    def racing_manifest(path, kind):
        value = original(path, kind)
        (skill / 'SKILL.md').write_text('Concurrent content')
        return value
    monkeypatch.setattr(capabilities, '_manifest', racing_manifest)
    with pytest.raises(ValueError, match='CHANGED_DURING_READ'):
        reconcile_capability(s, spec)
    assert s.get('capability_catalog', cap['id']) == cap
    assert len(s.list('capability_versions')) == 1


def test_drift_inspection_does_not_read_revoked_scope(tmp_path, monkeypatch):
    s, _, _, _, _, _ = changed(tmp_path)
    s.settings({'scopes': []})
    monkeypatch.setattr('skill_observatory.capabilities._manifest',
                        lambda *a: pytest.fail('Revoked capability read'))
    assert drift_actions(s) == []


def test_explicit_unbound_legacy_projection_migration_preserves_original(tmp_path):
    from skill_observatory.store import digest
    s, _, skill, cap, _, spec = changed(tmp_path)
    sid='sk_'+digest(str(skill.resolve()).encode())[:24]
    legacy=s.get('skills',sid)
    legacy={k:v for k,v in legacy.items() if k not in {'capability_id','version_id'}}
    legacy['owner']='old generic installer'
    s.put('skills',legacy)
    grant={'id':'retained','target':str(skill/'SKILL.md'),'owner':legacy['owner'],'status':'authorized'}
    s.put('authority_grants',grant)
    with pytest.raises(ValueError,match='CANONICAL_OWNER_CONFLICT'):
        reconcile_capability(s,spec)
    assert s.get('capability_catalog',cap['id'])==cap
    explicit={**spec,'legacy_projection_sha256':digest(canonical(legacy))}
    result=reconcile_capability(s,explicit)
    migration=s.list('legacy_projection_migrations')[0]
    assert json_value(s.read_artifact(migration['before_sha256']))==legacy
    assert s.get('skills',sid)['owner']==legacy['owner']
    assert s.get('skills',sid)['capability_owner']==cap['owner']
    assert s.get('authority_grants',grant['id'])==grant
    assert register_capability(s,skill,cap['owner'],scope=cap['scope'])['id']==cap['id']
    assert reconcile_capability(s,explicit)==result


def json_value(raw):
    import json
    return json.loads(raw)


@pytest.mark.parametrize('protected',['bound_version','authority','third_hash'])
def test_legacy_migration_cannot_override_bound_owner_or_authority(tmp_path,protected):
    from skill_observatory.store import digest
    s, _, skill, cap, _, spec=changed(tmp_path)
    sid='sk_'+digest(str(skill.resolve()).encode())[:24]
    legacy=s.get('skills',sid)
    legacy={k:v for k,v in legacy.items() if k not in {'capability_id','version_id'}}
    legacy['owner']='old generic installer'
    if protected=='bound_version':legacy['version_id']='immutable_version'
    s.put('skills',legacy)
    if protected=='authority':s.put('authority_grants',{'id':'protected','target':str(skill/'SKILL.md'),'owner':'unrelated owner'})
    spec={**spec,'legacy_projection_sha256':digest(canonical(legacy)) if protected!='third_hash' else 'a'*64}
    with pytest.raises(ValueError,match='LEGACY_PROJECTION'):
        reconcile_capability(s,spec)
    assert s.get('skills',sid)==legacy
    assert s.get('capability_catalog',cap['id'])==cap
    assert not s.list('legacy_projection_migrations')
