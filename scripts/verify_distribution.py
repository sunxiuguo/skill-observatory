"""Check built archives against the reviewed Git source and generated web assets."""
from pathlib import Path, PurePosixPath
import json
import subprocess
import tarfile
import zipfile
import tomllib

root = Path(__file__).resolve().parents[1]
git_root = Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], cwd=root, text=True).strip())
if git_root != root:
    raise SystemExit('Distribution audit requires the source checkout')
source = set(subprocess.check_output(['git', 'ls-files'], cwd=root, text=True).splitlines())
static = {p.relative_to(root).as_posix() for p in (root/'src/skill_observatory/static').rglob('*') if p.is_file()}
version=tomllib.loads((root/'pyproject.toml').read_text())['project']['version']
records = []
required = set(json.loads((root/'docs/project-contract.json').read_text())['sdist_required'])
for archive in sorted((root/'dist').glob(f'skill_observatory-{version}.tar.gz')):
    included = set()
    with tarfile.open(archive) as file:
        for member in file:
            if member.isdir():
                continue
            if not member.isfile():
                raise SystemExit('Non-file archive member rejected: ' + member.name)
            parts = PurePosixPath(member.name).parts
            name = '/'.join(parts[1:])
            included.add(name)
            if len(parts) < 2 or '..' in parts or name not in source | static | {'PKG-INFO'}:
                raise SystemExit('Unreviewed sdist member: ' + member.name)
            if name != 'PKG-INFO' and file.extractfile(member).read() != (root/name).read_bytes():
                raise SystemExit('Source byte drift in sdist: ' + name)
    if missing := required - included:
        raise SystemExit('Missing sdist governance files: ' + ', '.join(sorted(missing)))
    records.append(archive.name)
package = {p.removeprefix('src/') for p in source | static if p.startswith('src/skill_observatory/')}
for archive in sorted((root/'dist').glob(f'skill_observatory-{version}-*.whl')):
    with zipfile.ZipFile(archive) as file:
        for name in file.namelist():
            parts = PurePosixPath(name).parts
            metadata = (len(parts) > 1 and parts[0] == f'skill_observatory-{version}.dist-info'
                        and '/'.join(parts[1:]) in {'METADATA', 'WHEEL', 'entry_points.txt',
                            'RECORD', 'licenses/LICENSE', 'licenses/NOTICE.md'})
            if '..' in parts or (name not in package and not metadata):
                raise SystemExit('Unreviewed wheel member: ' + name)
            if name in package and file.read(name) != (root/'src'/name).read_bytes():
                raise SystemExit('Source byte drift in wheel: ' + name)
    records.append(archive.name)
if len(records) != 2:
    raise SystemExit('Expected exactly one wheel and one source archive')
print(json.dumps({'status': 'passed', 'archives': records, 'tracked_source_count': len(source)}))
