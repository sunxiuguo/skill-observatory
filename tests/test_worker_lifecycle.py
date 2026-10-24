"""Actual lifespan recovery when diagnostics are temporarily unavailable."""
import asyncio
import time

from skill_observatory import api, health
from skill_observatory.store import Store


def test_worker_recovers_after_primary_and_failure_receipt_write_fail(tmp_path, monkeypatch, caplog):
    store = Store(tmp_path / 'state')
    store._maintenance_checked_at = time.time()
    calls = {'daemon': 0, 'review': 0, 'evolution': 0}
    writes = []
    real_write = health.write_lane
    real_sleep = asyncio.sleep

    def transient_write(store, lane, **changes):
        if lane == 'daemon' and len(writes) < 2:
            writes.append(changes)
            raise OSError('private-diagnostic-sentinel')
        return real_write(store, lane, **changes)

    def callback(lane):
        calls[lane] += 1

    class Pipeline:
        def tick(self):
            callback('evolution')

    async def fast_sleep(delay):
        await real_sleep(min(delay, .01))

    monkeypatch.setattr(health, 'write_lane', transient_write)
    monkeypatch.setattr(api, 'collect', lambda _: callback('daemon'))
    monkeypatch.setattr(api, 'process_one', lambda *_: callback('review'))
    monkeypatch.setattr(asyncio, 'sleep', fast_sleep)

    async def exercise():
        app = api.create_app(store, pipeline=Pipeline())
        async with app.router.lifespan_context(app):
            for _ in range(100):
                if all(value >= 2 for value in calls.values()):
                    break
                await real_sleep(.01)
            assert all(value >= 2 for value in calls.values()), calls
        stopped = dict(calls)
        await real_sleep(.03)
        assert calls == stopped  # Shutdown must not restart or replay a lane.

    asyncio.run(exercise())
    assert len(writes) == 2
    assert 'WORKER_FAILURE_RECEIPT_UNAVAILABLE' in caplog.text
    assert 'private-diagnostic-sentinel' not in caplog.text


def test_watch_continues_other_lanes_after_bad_receipt_and_report_failure(tmp_path, monkeypatch, caplog):
    store = Store(tmp_path / 'state')
    store._maintenance_checked_at = time.time()
    real_read = health.read_lane
    real_sleep = asyncio.sleep
    reports = []

    def malformed_receipt(root, lane):
        if lane in ('review_worker', 'evolution_worker'):
            return {'phase': 'review', 'status': 'running',
                    'phase_started_at': 'invalid' if lane == 'review_worker' else time.time() - 1000}
        return real_read(root, lane)

    def unavailable_report(store, lane, reason):
        reports.append((lane, reason))
        if lane == 'review_worker':
            raise OSError('private-report-sentinel')
        return 1

    class Pipeline:
        def tick(self):
            pass

    async def fast_sleep(delay):
        await real_sleep(min(delay, .01))

    monkeypatch.setattr(health, 'read_lane', malformed_receipt)
    monkeypatch.setattr(health, 'failure', unavailable_report)
    monkeypatch.setattr(api, 'collect', lambda _: None)
    monkeypatch.setattr(api, 'process_one', lambda *_: None)
    monkeypatch.setattr(asyncio, 'sleep', fast_sleep)

    async def exercise():
        app = api.create_app(store, pipeline=Pipeline())
        async with app.router.lifespan_context(app):
            for _ in range(100):
                if reports.count(('evolution_worker', 'WORKER_DEADLINE_READBACK_REQUIRED')) >= 2:
                    break
                await real_sleep(.01)
            assert reports.count(('evolution_worker', 'WORKER_DEADLINE_READBACK_REQUIRED')) >= 2
        stopped = len(reports)
        await real_sleep(.03)
        assert len(reports) == stopped

    asyncio.run(exercise())
    assert ('review_worker', 'TypeError') in reports
    assert 'WORKER_FAILURE_RECEIPT_UNAVAILABLE' in caplog.text
    assert 'private-report-sentinel' not in caplog.text
