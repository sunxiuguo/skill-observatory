"""Read-only structural governance checks. Does not certify task gain or authority."""
from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import os
from pathlib import Path, PurePosixPath
import re
import tomllib


OBJECTIVES = {f'O{i}' for i in range(1, 8)}
# Minimum refusal routes: changing these is a contract change, not a green-CI fix.
GUARDRAILS = {
    'O1': ['tests/test_kernel.py::test_outside_scope_no_private_spool'],
    'O2': [
        'tests/test_pipeline.py::test_unsigned_verdict_refusal_does_not_reach_installer',
        'tests/test_pipeline.py::test_missing_exploration_cost_stays_hold',
        'tests/test_final_gate.py::test_unsupported_gain_cannot_be_promoted_by_receipt_flags',
        'tests/test_evaluation.py::test_final_set_consumption_survives_restart_and_new_protocol',
        'tests/test_pipeline.py::test_prepared_restart_requires_side_effect_readback',
        'tests/test_kernel.py::test_prepared_recovery_and_cas_rollback',
    ],
    'O3': [
        'tests/test_outcomes.py::test_task_result_requires_independent_signature_and_new_context',
        'tests/test_outcomes.py::test_context_created_during_owner_apply_is_not_fresh',
        'tests/test_outcomes.py::test_legacy_install_time_unknown_stays_hold',
        'tests/test_outcomes.py::test_live_verification_refuses_current_disk_drift',
        'tests/test_outcomes.py::test_later_user_run_records_as_of_readback_evidence',
    ],
    'O4': [
        'tests/test_capture.py::test_effectful_code_and_missing_origin_cannot_be_auto_installed',
        'tests/test_capture.py::test_skill_creation_requires_root_reviewed_forward_cases',
        'tests/test_capabilities.py::test_logical_invocations_observation_dedup_attempts_and_stage_counts',
    ],
    'O7': ['tests/test_evaluation.py::test_real_artifact_grading_and_synthetic_final_stays_hold'],
}
SKIP = {'.git', '.local', '.venv', '.codex', '.pytest_cache', '__pycache__',
        'node_modules', 'dist', 'static', '.impeccable', '.openai'}
FIELDS = {'schema_version', 'instruction_files', 'documents', 'objectives',
          'web_scripts', 'sdist_required'}
REQUIRED_SDIST = {'AGENTS.md', 'web/AGENTS.md', 'docs/PROJECT_CONTRACT.md',
                  'docs/project-contract.json', 'scripts/check_project_contract.py'}


def check(root: Path) -> list[dict[str, str]]:
    root = root.resolve()
    errors = []

    def fail(code, path):
        errors.append({'code': code, 'path': str(path)})

    def read(name):
        if not isinstance(name, str) or not name or '\\' in name:
            fail('INVALID_PATH', name)
            return None
        relative = PurePosixPath(name)
        path = root / name
        if relative.is_absolute() or '..' in relative.parts or not path.resolve().is_relative_to(root):
            fail('OUTSIDE_REPOSITORY', name)
            return None
        if path.is_symlink() or not path.is_file():
            fail('MISSING_FILE', name)
            return None
        try:
            return path.read_text(encoding='utf-8')
        except (OSError, UnicodeError):
            fail('UNREADABLE_FILE', name)
            return None

    raw = read('docs/project-contract.json')
    try:
        contract = json.loads(raw or '')
    except ValueError:
        fail('INVALID_MANIFEST', 'docs/project-contract.json')
        return errors
    if (not isinstance(contract, dict) or set(contract) != FIELDS
            or type(contract['schema_version']) is not int or contract['schema_version'] != 1
            or not isinstance(contract['objectives'], dict)):
        fail('INVALID_MANIFEST', 'docs/project-contract.json')
        return errors
    for field in FIELDS - {'schema_version', 'objectives'}:
        value = contract[field]
        if (not isinstance(value, list) or not value
                or any(not isinstance(item, str) or not item for item in value)
                or len(set(value)) != len(value)):
            fail('INVALID_MANIFEST_FIELD', field)
    if errors:
        return errors

    instructions = set(contract['instruction_files'])
    if not {'AGENTS.md', 'web/AGENTS.md'} <= instructions:
        fail('MISSING_INSTRUCTION_ENTRY', 'instruction_files')
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if d not in SKIP and not (Path(directory) / d).is_symlink()]
        for filename in {'AGENTS.md', 'AGENTS.override.md'} & set(files):
            name = (Path(directory) / filename).relative_to(root).as_posix()
            if filename == 'AGENTS.override.md':
                fail('SHADOWING_OVERRIDE', name)
            elif name not in instructions:
                fail('UNCLASSIFIED_INSTRUCTIONS', name)
    for name in instructions:
        if PurePosixPath(name).name != 'AGENTS.md':
            fail('INVALID_INSTRUCTION_ENTRY', name)

    texts = {}
    for name in instructions | set(contract['documents']):
        value = read(name)
        if value is not None:
            texts[name] = value
            if not value.strip():
                fail('EMPTY_DOCUMENT', name)
            if name in instructions and len(value.encode()) > 8192:
                fail('INSTRUCTION_SIZE', name)
    for name in instructions | {'docs/PROJECT_CONTRACT.md'}:
        for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)', texts.get(name, '')):
            target = target.split('#', 1)[0]
            if not target or re.match(r'^https?://', target):
                continue
            path = (root / name).parent / target
            if not path.resolve().is_relative_to(root):
                fail('OUTSIDE_REFERENCE', name)
            else:
                read(path.resolve().relative_to(root).as_posix())
    # Mandatory routing is link-based rather than requiring exact prose.
    routes = {
        'AGENTS.md': ['docs/PROJECT_CONTRACT.md', 'docs/STATUS.md', 'web/AGENTS.md'],
        'web/AGENTS.md': ['../AGENTS.md', '../docs/PROJECT_CONTRACT.md'],
    }
    for name, links in routes.items():
        for link in links:
            if f']({link})' not in texts.get(name, ''):
                fail('MISSING_ROUTE', name + ':' + link)

    if set(contract['objectives']) != OBJECTIVES:
        fail('OBJECTIVE_COVERAGE', 'objectives')
    for objective, item in contract['objectives'].items():
        if (not isinstance(item, dict) or set(item) != {'code', 'tests'}
                or any(not isinstance(item[k], list) or not item[k]
                       or any(not isinstance(p, str) for p in item[k]) for k in ('code', 'tests'))):
            fail('INVALID_OBJECTIVE', objective)
            continue
        if not re.search(r'^### ' + re.escape(objective) + r'\s', texts.get('docs/PROJECT_CONTRACT.md', ''), re.M):
            fail('MISSING_OBJECTIVE_TEXT', objective)
        for test in GUARDRAILS.get(objective, []):
            if test not in item['tests']:
                fail('DROPPED_GUARDRAIL', test)
        for name in item['code']:
            read(name)
        for selector in item['tests']:
            name, _, function = selector.partition('::')
            value = read(name)
            if value is None:
                continue
            if function:
                try:
                    tree = ast.parse(value)
                    names = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
                except SyntaxError:
                    names = set()
                if function not in names or not function.startswith('test_'):
                    fail('MISSING_REGRESSION', selector)

    try:
        package = json.loads(read('web/package.json') or '')
        for name in contract['web_scripts']:
            if not package.get('scripts', {}).get(name):
                fail('MISSING_WEB_COMMAND', name)
        project = tomllib.loads(read('pyproject.toml') or '')
        includes = project['tool']['hatch']['build']['targets']['sdist']['include']
        required = set(contract['sdist_required'])
        if not REQUIRED_SDIST <= required:
            fail('DROPPED_DISTRIBUTION_CONTRACT', 'sdist_required')
        for name in required:
            read(name)
            if not any(fnmatch.fnmatchcase(name, pattern) for pattern in includes):
                fail('SDIST_OMISSION', name)
    except (ValueError, KeyError, TypeError):
        fail('INVALID_BUILD_CONFIGURATION', 'web/package.json or pyproject.toml')
    ci = read('.github/workflows/ci.yml') or ''
    if not re.search(r'^\s*- run: uv run python scripts/check_project_contract\.py\s*$', ci, re.M):
        fail('MISSING_CI_GATE', '.github/workflows/ci.yml')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    errors = check(args.root)
    print(json.dumps({'status': 'failed' if errors else 'passed',
                      'scope': 'structure_only', 'errors': errors}, ensure_ascii=False))
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
