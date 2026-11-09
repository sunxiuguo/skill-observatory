"""Exact compressed review sources retain identity and bounded private reads."""
import json
import shutil
import subprocess

import pytest

from skill_observatory.proactive import plan
from test_proactive import setup, chat, STAMP


def compressed(path):
    if not shutil.which('zstd'):
        pytest.skip('optional compressed review requires zstd')
    target = path.with_suffix(path.suffix + '.zst')
    target.write_bytes(subprocess.run(['zstd', '-cq'], input=path.read_bytes(),
                                      capture_output=True, check=True).stdout)
    path.unlink()
    return target


@pytest.mark.parametrize('location', ['source', 'archive', 'indexed_archive'])
@pytest.mark.parametrize('fault', [None, 'identity', 'cwd', 'version', 'symlink', 'parent_symlink'])
def test_compressed_exact_source_keeps_identity_gates(tmp_path, location, fault):
    store, scope, index = setup(tmp_path)
    path = chat(scope, index, 'compressed')
    if fault in {'identity', 'cwd', 'version'}:
        value = json.loads(path.read_text())
        key, val = {'identity': ('id', 'wrong'), 'cwd': ('cwd', str(tmp_path/'outside')),
                    'version': ('cli_version', '99.0')}[fault]
        value['payload'][key] = val
        path.write_text(json.dumps(value) + '\n')
    if location != 'source':
        archive = index.parent/'archived_sessions'; archive.mkdir()
        target = archive/path.name; path.rename(target)
        if location == 'indexed_archive':
            import sqlite3
            with sqlite3.connect(index) as db:
                db.execute('UPDATE threads SET rollout_path=?', (str(target),))
        path = target
    target = compressed(path)
    before = target.read_bytes()
    if fault == 'symlink':
        actual = tmp_path/'actual.zst'; target.rename(actual); target.symlink_to(actual)
    if fault == 'parent_symlink':
        parent = target.parent; actual = parent.with_name(parent.name+'-actual')
        parent.rename(actual); parent.symlink_to(actual, target_is_directory=True)
    if fault == 'parent_symlink' and location == 'source':
        from skill_observatory.proactive import _source
        item = _source({'id': 'compressed', 'rollout_path': str(path),
                        'cwd': str(scope), 'updated_at': STAMP-100}, store, index.parent)
    else:
        item = next(x for x in plan(store, index, stamp=STAMP)['items'] if x['kind']=='chat')
    if fault is None:
        assert item['signal']['path'] == str(target)
        assert item['signal']['compression'] == 'zstd'
        assert 'reason_code' not in item['signal']
        assert target.read_bytes() == before and not path.exists()
    else:
        assert item['signal'].get('reason_code')


def test_compressed_body_integrity_limits_and_cleanup(tmp_path):
    from skill_observatory.review_sources import review_source
    path = tmp_path/'one.jsonl'; original = b'{}\n' + b'x'*10000
    path.write_bytes(original); target = compressed(path)
    with review_source(target) as view:
        assert view.read_bytes() == original
        temporary = view
    assert not temporary.exists() and not path.exists()
    with pytest.raises(ValueError, match='TRANSCRIPT_DECOMPRESSED_TOO_LARGE'):
        with review_source(target, max_bytes=32):
            pytest.fail('oversized body admitted')
    target.write_bytes(target.read_bytes()[:-3])
    with pytest.raises(ValueError, match='TRANSCRIPT_COMPRESSION_INVALID'):
        with review_source(target):
            pytest.fail('corrupt body admitted')


def test_compressed_header_missing_binary_and_timeout_are_visible(tmp_path, monkeypatch):
    import skill_observatory.review_sources as sources
    store, scope, index = setup(tmp_path)
    target = compressed(chat(scope, index, 'compressed'))
    with monkeypatch.context() as patch:
        patch.setattr(sources.shutil, 'which', lambda _: None)
        item = next(x for x in plan(store, index, stamp=STAMP)['items'] if x['kind']=='chat')
        assert item['signal']['reason_code'] == 'TRANSCRIPT_ZSTD_REQUIRED'
    monkeypatch.setattr(sources, 'READ_TIMEOUT_SECONDS', 0)
    with pytest.raises(ValueError, match='TRANSCRIPT_DECOMPRESSION_TIMEOUT'):
        with sources.review_source(target):
            pytest.fail('unbounded decompression admitted')


def test_compressed_source_drift_and_header_limit_refuse(tmp_path):
    from skill_observatory.review_sources import review_source
    path = tmp_path/'one.jsonl'; path.write_bytes(b'{}\n')
    target = compressed(path)
    with pytest.raises(ValueError, match='TRANSCRIPT_SOURCE_CHANGED'):
        with review_source(target) as view:
            temporary = view
            target.write_bytes(target.read_bytes() + b'changed')
    assert not temporary.exists()
    path.write_bytes(b'x'*65537 + b'\n')
    target = compressed(path)
    with pytest.raises(ValueError, match='TRANSCRIPT_META_TOO_LARGE'):
        with review_source(target, metadata_only=True):
            pytest.fail('oversized metadata admitted')
