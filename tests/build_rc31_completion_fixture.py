"""Build disposable, keyless CI inputs; these are not delivery assets."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dsh_runtime.policy_artifact import compute_policy_hash
from scripts.build_api_reviewer_wheelhouse import build

assets = Path(sys.argv[1]).resolve()
assets.mkdir(parents=True, exist_ok=False)
manifest = json.loads((ROOT / 'tests/rc31-completion-fixture-manifest.json').read_text(encoding='utf-8'))
expected = {w['file']: w['sha256'].lower() for w in manifest['python_wheels']}
wheels = build(assets / 'wheels')
if {w['file']: w['sha256'].lower() for w in wheels} != expected:
    raise SystemExit('Downloaded fixture wheels differ from pinned fixture hashes')
commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
archive = assets / 'runtime-fixture.zip'
subprocess.run(['git', 'archive', '--format=zip', f'--output={archive}', commit], cwd=ROOT, check=True)
manifest['runtime'] = {'commit': commit, 'file': archive.name,
                       'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}
manifest['policy_hash'] = compute_policy_hash(json.loads(
    (ROOT / 'dsh_runtime/resources/selection_policy/selection-v2.json').read_text(encoding='utf-8')))
manifest['python_wheels'] = wheels
(assets / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
print(f'CI fixture only: {commit}; {archive}')
