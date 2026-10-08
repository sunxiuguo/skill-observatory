"""Build the first-party web client into the wheel."""
from pathlib import Path
import shutil,subprocess
root=Path(__file__).resolve().parents[1]
subprocess.run(['npm','ci','--registry=https://registry.npmjs.org'],cwd=root/'web',check=True)
subprocess.run(['npm','run','build'],cwd=root/'web',check=True)
static=root/'src/skill_observatory/static'
if static.exists():shutil.rmtree(static)
shutil.copytree(root/'web/dist/client',static)
subprocess.run(['uv','build'],cwd=root,check=True)
