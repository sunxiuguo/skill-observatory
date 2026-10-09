"""Bounded IPC for container tasks; authentication remains with the model owner.

This is an execution mechanism, not an oracle or model-isolation certificate.
Only frozen read-only snapshots and an admitted model adapter are exposed.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
import multiprocessing
import signal
from pathlib import Path
import selectors
import subprocess
import time

from .evaluation import DockerSandbox, Environment, EvaluationHold
from .store import canonical, digest, now


def _model_worker(connection, owner, prompt, policy, limits):
    # New process group bounds a trusted transport and its child app-server.
    os.setsid()
    try:
        result = canonical(owner.generate(prompt, policy, **limits))
        if len(result) > policy.message_bytes * 2:
            result = canonical({'error': 'MODEL_RESPONSE_TOO_LARGE', 'sha256': digest(result)})
        connection.send_bytes(result)
    finally:
        connection.close()


def _bounded_generate(owner, prompt, policy, limits):
    context = multiprocessing.get_context('spawn')
    read, write = context.Pipe(duplex=False)
    worker = context.Process(target=_model_worker, args=(write, owner, prompt, policy, limits))
    deadline = time.monotonic() + limits['timeout']
    try:
        worker.start()
        write.close()
        if not read.poll(max(0., deadline-time.monotonic())):
            raise EvaluationHold('MODEL_DEADLINE_ATTEMPT_CONSUMED')
        return json.loads(read.recv_bytes(policy.message_bytes * 2))
    finally:
        read.close()
        write.close()
        if worker.pid:
            try:
                if os.getpgid(worker.pid) == worker.pid:
                    os.killpg(worker.pid, signal.SIGKILL)
                elif worker.is_alive():
                    worker.kill()
            except ProcessLookupError:
                pass
            worker.join(timeout=3)


@dataclass(frozen=True)
class BrokerPolicy:
    provider: str
    model: str
    effort: str
    max_calls: int
    max_tokens: int
    max_money: float
    wall_seconds: int = 60
    message_bytes: int = 65536

    def validate(self):
        if not all(type(x) is str and x for x in (self.provider, self.model, self.effort)):
            raise EvaluationHold('EXACT_MODEL_EFFORT_REQUIRED')
        for value, maximum in ((self.max_calls, 20), (self.max_tokens, 1000000),
                               (self.wall_seconds, 300), (self.message_bytes, 1048576)):
            if type(value) is not int or not 1 <= value <= maximum:
                raise EvaluationHold('BROKER_LIMIT_INVALID')
        if type(self.max_money) not in (int, float) or not math.isfinite(self.max_money) or self.max_money < 0:
            raise EvaluationHold('BROKER_LIMIT_INVALID')


class TaskBroker:
    """Host-owned adapter, never passed to candidate code.

    owner.admit(policy) supplies current admission and tool-free-context proof.
    owner.generate(prompt, policy, timeout, max_tokens, max_money) must enforce
    those limits in its existing model transport and return a fresh context,
    actual usage and output. The broker cannot certify a dishonest adapter.
    """
    def __init__(self, store, policy: BrokerPolicy, owner, snapshots=None):
        policy.validate()
        self.store, self.policy, self.owner = store, policy, owner
        self.snapshots = dict(snapshots or {})
        if (len(self.snapshots) > 64 or any(type(k) is not str or type(v) is not bytes
                or len(v) > policy.message_bytes // 2 for k, v in self.snapshots.items())):
            raise EvaluationHold('SNAPSHOT_LIMIT_INVALID')

    def run(self, attempt_id, files, entrypoint, environment: Environment):
        p = Path(entrypoint)
        if p.is_absolute() or '..' in p.parts or p.suffix != '.py' or entrypoint not in files:
            raise EvaluationHold('ENTRYPOINT_NOT_AUTHORIZED')
        policy = self.policy
        admission = self.owner.admit(policy)
        if not (admission.get('ok') is True and admission.get('provider') == policy.provider
                and admission.get('model') == policy.model
                and admission.get('maximum_verified_effort') == policy.effort
                and admission.get('redacted_evidence_allowed') is True
                and admission.get('tool_free_context_verified') is True):
            raise EvaluationHold('MODEL_OWNER_ADMISSION_HOLD')
        binding = {'files': {k: digest(v) for k, v in files.items()},
                   'entrypoint': entrypoint, 'environment': environment.__dict__,
                   'policy': policy.__dict__,
                   'snapshots': {k: digest(v) for k, v in self.snapshots.items()}}
        receipt = {'id': attempt_id, 'binding_sha256': digest(canonical(binding)),
                   'created_at': now(), 'status': 'prepared', 'calls': [],
                   'tokens': 0, 'money': 0, 'missing': []}
        # Consume before starting a process or sending any model request.
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if self.store.get('broker_attempts', attempt_id, db):
                raise EvaluationHold('ATTEMPT_ALREADY_CONSUMED_READBACK_REQUIRED')
            self.store.put('broker_attempts', receipt, db)
        sandbox = DockerSandbox(environment)
        proc = None
        start = time.monotonic()
        deadline = start + min(policy.wall_seconds, environment.timeout)
        try:
            receipt['container'] = sandbox.prepare(files)
            receipt['status'] = 'running'
            self.store.put('broker_attempts', receipt)
            proc = subprocess.Popen(['docker', 'exec', '-i', sandbox.id, 'python', '-I', '-B',
                                     '/work/' + entrypoint], stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
            selector = selectors.DefaultSelector()
            selector.register(proc.stdout, selectors.EVENT_READ)
            buffer = b''
            request_count = 0
            contexts = set()
            try:
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise EvaluationHold('BROKER_DEADLINE_ATTEMPT_CONSUMED')
                    if not selector.select(remaining):
                        raise EvaluationHold('BROKER_DEADLINE_ATTEMPT_CONSUMED')
                    chunk = proc.stdout.read(4096)
                    if not chunk:
                        if buffer:
                            raise EvaluationHold('BROKER_PARTIAL_MESSAGE')
                        break
                    buffer += chunk
                    if len(buffer) > policy.message_bytes:
                        raise EvaluationHold('BROKER_MESSAGE_TOO_LARGE')
                    while b'\n' in buffer:
                        line, buffer = buffer.split(b'\n', 1)
                        request_count += 1
                        if request_count > 64:
                            raise EvaluationHold('BROKER_REQUEST_LIMIT')
                        try:
                            request = json.loads(line)
                        except (ValueError, UnicodeError) as e:
                            raise EvaluationHold('BROKER_INVALID_MESSAGE') from e
                        if type(request) is not dict:
                            raise EvaluationHold('BROKER_INVALID_MESSAGE')
                        if request.get('op') == 'snapshot' and set(request) == {'op', 'name'}:
                            name = request['name']
                            if type(name) is not str or name not in self.snapshots:
                                raise EvaluationHold('READ_ONLY_SNAPSHOT_NOT_AUTHORIZED')
                            response = {'text': self.snapshots[name].decode('utf-8')}
                        elif request.get('op') == 'model' and set(request) == {'op', 'prompt'}:
                            if type(request['prompt']) is not str:
                                raise EvaluationHold('BROKER_INVALID_MESSAGE')
                            if (len(receipt['calls']) >= policy.max_calls or
                                receipt['tokens'] >= policy.max_tokens or
                                receipt['money'] > policy.max_money):
                                raise EvaluationHold('BROKER_BUDGET_EXHAUSTED')
                            call = {'id': len(receipt['calls']), 'status': 'prepared',
                                    'prompt_sha256': digest(request['prompt'].encode()),
                                    'money': None, 'tokens': None}
                            receipt['calls'].append(call)
                            self.store.put('broker_attempts', receipt)
                            result = _bounded_generate(self.owner, request['prompt'], policy, {
                                'timeout': max(0., deadline-time.monotonic()),
                                'max_tokens': policy.max_tokens-receipt['tokens'],
                                'max_money': policy.max_money-receipt['money']})
                            # Preserve a returned response before interpreting it. A bad
                            # response consumes the call; it never authorizes replay.
                            call['result_artifact'] = self.store.artifact(canonical(result))
                            self.store.put('broker_attempts', receipt)
                            if not isinstance(result, dict):
                                raise EvaluationHold('MODEL_RECEIPT_INVALID')
                            tokens, money = result.get('tokens'), result.get('money')
                            context = result.get('context_id')
                            if (result.get('provider') != policy.provider or result.get('model') != policy.model
                                or result.get('effort') != policy.effort or result.get('fresh_context') is not True
                                or type(context) is not str or not context or context in contexts
                                or type(tokens) is not int or tokens < 0
                                or type(money) not in (int, float) or not math.isfinite(money) or money < 0
                                or type(result.get('text')) is not str):
                                raise EvaluationHold('MODEL_IDENTITY_OR_COST_TRUTH_MISSING')
                            contexts.add(context)
                            call.update(status='completed', tokens=tokens, money=money, context_id=context)
                            receipt['tokens'] += tokens
                            receipt['money'] += money
                            self.store.put('broker_attempts', receipt)
                            if (receipt['tokens'] > policy.max_tokens or receipt['money'] > policy.max_money
                                    or time.monotonic() >= deadline):
                                raise EvaluationHold('MODEL_OWNER_LIMIT_VIOLATION')
                            response = {'text': result['text']}
                        else:
                            raise EvaluationHold('BROKER_OPERATION_NOT_AUTHORIZED')
                        encoded = canonical(response) + b'\n'
                        if len(encoded) > policy.message_bytes:
                            raise EvaluationHold('BROKER_RESPONSE_TOO_LARGE')
                        # A task can stop reading after requesting a response. Never
                        # block the daemon on its stdin pipe.
                        os.set_blocking(proc.stdin.fileno(), False)
                        writer = selectors.DefaultSelector()
                        try:
                            writer.register(proc.stdin, selectors.EVENT_WRITE)
                            while encoded:
                                left = deadline-time.monotonic()
                                if left <= 0 or not writer.select(left):
                                    raise EvaluationHold('BROKER_DEADLINE_ATTEMPT_CONSUMED')
                                try:
                                    count = os.write(proc.stdin.fileno(), encoded)
                                    encoded = encoded[count:]
                                except BlockingIOError:
                                    continue
                        finally:
                            writer.close()
            finally:
                selector.close()
            exit_code = proc.wait(timeout=max(.01, deadline-time.monotonic()))
            artifacts = sandbox.collect()
            receipt.update(status='completed', exit_code=exit_code,
                artifacts={k: self.store.artifact(v) for k, v in artifacts.items()})
        except Exception as e:
            receipt.update(status='hold', reason_code=str(e) if isinstance(e, EvaluationHold)
                           else 'BROKER_INTERRUPTED_READBACK_REQUIRED')
        finally:
            if proc is not None:
                proc.kill() if proc.poll() is None else None
                proc.wait(timeout=3)
                proc.stdin.close()
                proc.stdout.close()
            try:
                sandbox.destroy()
            finally:
                receipt['wall_seconds'] = time.monotonic()-start
                if any(c['status'] != 'completed' for c in receipt['calls']):
                    receipt.update(tokens=None, money=None)
                    receipt['missing'].append('FAILED_OR_UNKNOWN_MODEL_COST_REQUIRED')
                self.store.put('broker_attempts', receipt)
        return receipt
