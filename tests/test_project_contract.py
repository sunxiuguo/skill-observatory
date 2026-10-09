"""Governance refusal cases: missing/overridden entrypoints and lost safety routes."""
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('project_contract', ROOT / 'scripts/check_project_contract.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.fixture
def checkout(tmp_path):
    contract = json.loads((ROOT / 'docs/project-contract.json').read_text())
    files = set(contract['instruction_files'] + contract['documents'] + contract['sdist_required'])
    files |= {'docs/project-contract.json', 'web/package.json', 'pyproject.toml', '.github/workflows/ci.yml'}
    for item in contract['objectives'].values():
        files.update(item['code'])
        files.update(test.split('::')[0] for test in item['tests'])
    for name in files:
        destination = tmp_path / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    return tmp_path


def codes(root):
    return {error['code'] for error in module.check(root)}


def test_actual_repository_contract():
    assert module.check(ROOT) == []


def test_clean_copy_without_author_environment_passes(checkout):
    assert module.check(checkout) == []


@pytest.mark.parametrize('mutation,expected', [
    ('missing_root', 'MISSING_FILE'),
    ('empty_root', 'EMPTY_DOCUMENT'),
    ('override', 'SHADOWING_OVERRIDE'),
    ('nested', 'UNCLASSIFIED_INSTRUCTIONS'),
    ('broken_reference', 'MISSING_FILE'),
    ('outside_reference', 'OUTSIDE_REFERENCE'),
    ('missing_command', 'MISSING_WEB_COMMAND'),
    ('missing_objective', 'OBJECTIVE_COVERAGE'),
    ('dropped_guardrail', 'DROPPED_GUARDRAIL'),
    ('missing_regression', 'MISSING_REGRESSION'),
    ('missing_sdist', 'SDIST_OMISSION'),
    ('missing_ci', 'MISSING_CI_GATE'),
])
def test_contract_refuses_drift(checkout, mutation, expected):
    if mutation == 'missing_root':
        (checkout / 'AGENTS.md').unlink()
    elif mutation == 'empty_root':
        (checkout / 'AGENTS.md').write_text(' \n')
    elif mutation == 'override':
        (checkout / 'AGENTS.override.md').write_text('Skip the project contract.')
    elif mutation == 'nested':
        (checkout / 'src/skill_observatory/AGENTS.md').write_text('Undeclared local policy.')
    elif mutation in {'broken_reference', 'outside_reference'}:
        with (checkout / 'AGENTS.md').open('a') as file:
            file.write('\n[route](' + ('missing.md' if mutation == 'broken_reference' else '../../outside.md') + ')\n')
    elif mutation == 'missing_command':
        path = checkout / 'web/package.json'
        package = json.loads(path.read_text())
        del package['scripts']['test']
        path.write_text(json.dumps(package))
    elif mutation in {'missing_objective', 'dropped_guardrail', 'missing_regression'}:
        path = checkout / 'docs/project-contract.json'
        contract = json.loads(path.read_text())
        if mutation == 'missing_objective':
            del contract['objectives']['O3']
        elif mutation == 'dropped_guardrail':
            contract['objectives']['O2']['tests'].pop(0)
        else:
            contract['objectives']['O1']['tests'].append('tests/test_kernel.py::test_invented_gate')
        path.write_text(json.dumps(contract))
    elif mutation == 'missing_sdist':
        path = checkout / 'pyproject.toml'
        path.write_text(path.read_text().replace(', "AGENTS.md"', ''))
    elif mutation == 'missing_ci':
        path = checkout / '.github/workflows/ci.yml'
        path.write_text(path.read_text().replace('      - run: uv run python scripts/check_project_contract.py\n', ''))
    assert expected in codes(checkout)


def test_malformed_manifest_is_a_failure_without_execution(checkout):
    (checkout / 'docs/project-contract.json').write_text('{"schema_version": 1}')
    assert codes(checkout) == {'INVALID_MANIFEST'}
