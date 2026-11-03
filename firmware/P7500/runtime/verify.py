"""Build and run the host, ARM core and compiled native-adapter checks."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
started=time.time()
for script in ('build.py','test_runtime.py','probe_arm_integration.py','probe_compiled_bindings.py',
               'probe_dispatch_boundary.py','probe_virtual_ink_jobs.py'):
    subprocess.run([sys.executable,str(ROOT/'runtime'/script)],cwd=ROOT,check=True)
names=['virtual-runtime-host-results.json','virtual-runtime-arm-results.json','compiled-native-binding-results.json',
       'native-dispatch-boundary-results.json','virtual-ink-job-results.json']
reports={}
for name in names:
    path=ROOT/'analysis'/name
    if path.stat().st_mtime<started:
        raise RuntimeError(f'Stale validation result: {name}')
    reports[name]=json.loads(path.read_text())
sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
         for p in sorted((ROOT/'runtime').iterdir()) if p.suffix in ('.py','.c','.h','.ld')}
summary={
    'source_sha256':sources,
    'arm_elf_sha256':hashlib.sha256((ROOT/'build/virtual_cartridge.arm.elf').read_bytes()).hexdigest(),
    'original_merged_sha256':hashlib.sha256((ROOT/'original/merged.bin').read_bytes()).hexdigest(),
    'reports':reports,
    'physical_printer_or_flash_tested':False,
    'flash_image_generated':False,
}
(ROOT/'analysis/runtime-verification.json').write_text(json.dumps(summary,indent=2))
print('All runtime validations passed; current-run aggregate saved.')
