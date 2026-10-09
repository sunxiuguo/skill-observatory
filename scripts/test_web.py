"""Run Web contract tests against an actual, isolated loopback API and fixture ledger."""
from pathlib import Path
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from http.cookiejar import CookieJar
from urllib.request import build_opener, HTTPCookieProcessor

from skill_observatory.capabilities import register_capability, record_usage
from skill_observatory.store import Store


def seed(work: Path):
    project = work / 'project'
    package = project / 'fixture-receipt-check'
    package.mkdir(parents=True)
    (package / 'SKILL.md').write_text('---\nname: fixture-receipt-check\ndescription: Synthetic UI contract fixture.\n---\nRead receipts.\n')
    state = work / 'state'
    store = Store(state)
    store.settings({'scopes': [str(project)]})
    capability = register_capability(store, package, 'ui-test-fixture', scope=project)
    evidence = store.artifact(b'Synthetic execution receipt for UI transport tests, not real task gain.')
    record_usage(store, {'capability_id': capability['id'], 'version_id': capability['version_id'],
                        'cwd': str(project), 'session_id': 'ui-fixture', 'turn_id': 'fixture-turn',
                        'invocation_id': 'fixture-call', 'stage': 'executed', 'source': 'cli',
                        'event_id': 'fixture-executed', 'attempt_id': 'fixture-attempt',
                        'scenario': 'fixture: metadata import', 'status': 'completed',
                        'origin': 'synthetic', 'evidence_sha256': evidence})
    return state


def main():
    root = Path(__file__).resolve().parents[1]
    npm = shutil.which('npm')
    if not npm:
        raise SystemExit('npm is required for Web contract tests')
    with tempfile.TemporaryDirectory(prefix='skillobs-web-test-') as directory:
        work = Path(directory)
        state = seed(work)
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        origin = f'http://127.0.0.1:{port}'
        client = build_opener(HTTPCookieProcessor(CookieJar()))
        with (work / 'server.log').open('w+') as log:
            server = subprocess.Popen([sys.executable, '-m', 'skill_observatory.cli',
                                       '--state', str(state), 'serve', '--port', str(port)],
                                      cwd=root, stdout=log, stderr=log)
            try:
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline and server.poll() is None:
                    try:
                        with client.open(origin + '/api/session', timeout=1) as response:
                            json.load(response)
                        with client.open(origin + '/api/state', timeout=1) as response:
                            actual = json.load(response)
                        if actual['settings']['scopes'] != [str(work / 'project')]:
                            raise RuntimeError('API identity does not match the isolated test state')
                        break
                    except OSError:
                        time.sleep(0.1)
                else:
                    log.seek(0)
                    raise RuntimeError('Isolated API did not start: ' + log.read()[-2000:])
                result = subprocess.run([npm, '--prefix', 'web', 'test'], cwd=root,
                                        env={**os.environ, 'SKILLOBS_TEST_ORIGIN': origin})
                return result.returncode
            finally:
                if server.poll() is None:
                    server.terminate()
                    try:
                        server.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        server.kill()
                        server.wait(timeout=5)


if __name__ == '__main__':
    raise SystemExit(main())
