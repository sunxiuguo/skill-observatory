"""Read exactly selected review sources; temporary decoded bytes are removed on exit.

This is root-review input, not a collector cursor or a claim of task execution.
Callers must apply observation/diagnostic scope before opening source bodies.
"""
from contextlib import contextmanager
from pathlib import Path
import selectors
import shutil
import subprocess
import tempfile
import time

from .transcripts import _regular_path

READ_TIMEOUT_SECONDS = 15
MAX_SOURCE_BYTES = 64 * 1024 * 1024


def review_path(path, index_parent=None):
    """Only the indexed basename and its exact compressed/archive counterparts."""
    path = Path(path)
    candidates = [path]
    if path.suffix == '.jsonl':
        candidates.append(path.with_suffix('.jsonl.zst'))
    if index_parent is not None:
        archive = Path(index_parent) / 'archived_sessions' / path.name
        candidates.append(archive)
        if path.suffix == '.jsonl':
            candidates.append(archive.with_suffix('.jsonl.zst'))
    for candidate in candidates:
        if candidate.exists() or candidate.is_symlink():
            return _regular_path(candidate)
    return path


def _stamp(path):
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns, stat.st_ino


@contextmanager
def review_source(path, *, metadata_only=False, max_bytes=MAX_SOURCE_BYTES):
    """Bound zstd memory, decoded bytes and wall time; retain original archives."""
    path = _regular_path(path)
    if not path.name.endswith('.jsonl.zst'):
        yield path
        return
    binary = shutil.which('zstd')
    if not binary:
        raise ValueError('TRANSCRIPT_ZSTD_REQUIRED')
    before = _stamp(path)
    if before[0] > MAX_SOURCE_BYTES:
        raise ValueError('TRANSCRIPT_COMPRESSED_TOO_LARGE')
    limit = 65536 if metadata_only else min(max_bytes, MAX_SOURCE_BYTES)
    deadline = time.monotonic() + READ_TIMEOUT_SECONDS
    with tempfile.TemporaryDirectory(prefix='skillobs-review-') as directory:
        view = Path(directory).resolve() / 'selected.jsonl'
        with path.open('rb') as source, view.open('xb') as output:
            view.chmod(0o600)
            process = subprocess.Popen([binary, '-dcq', '-M64MB', '--'], stdin=source,
                                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            try:
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ)
                    size = 0
                    while True:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0 or not selector.select(remaining):
                            raise ValueError('TRANSCRIPT_DECOMPRESSION_TIMEOUT')
                        block = process.stdout.read1(min(65536, limit - size + 1))
                        if not block:
                            try:
                                status = process.wait(timeout=max(0, deadline - time.monotonic()))
                            except subprocess.TimeoutExpired as error:
                                raise ValueError('TRANSCRIPT_DECOMPRESSION_TIMEOUT') from error
                            if status:
                                raise ValueError('TRANSCRIPT_COMPRESSION_INVALID')
                            break
                        if metadata_only and b'\n' in block:
                            block = block.split(b'\n', 1)[0] + b'\n'
                        size += len(block)
                        if size > limit:
                            raise ValueError('TRANSCRIPT_META_TOO_LARGE' if metadata_only
                                             else 'TRANSCRIPT_DECOMPRESSED_TOO_LARGE')
                        output.write(block)
                        if metadata_only and block.endswith(b'\n'):
                            break
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait()
                process.stdout.close()
        if _regular_path(path) != path or _stamp(path) != before:
            raise ValueError('TRANSCRIPT_SOURCE_CHANGED')
        yield view
        if _regular_path(path) != path or _stamp(path) != before:
            raise ValueError('TRANSCRIPT_SOURCE_CHANGED')
