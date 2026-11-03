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
               'probe_dispatch_boundary.py','probe_virtual_ink_jobs.py','test_native_nv.py',
               'probe_native_nv.py','probe_virtual_ink_data.py','test_metadata_store.py','probe_full_nv.py'):
    subprocess.run([sys.executable,str(ROOT/'runtime'/script)],cwd=ROOT,check=True)
for script in ('build.py','assemble.py','probe_bootstrap.py','package.py'):
    subprocess.run([sys.executable,str(ROOT/'delivery'/script)],cwd=ROOT,check=True)
names=['virtual-runtime-host-results.json','virtual-runtime-arm-results.json','compiled-native-binding-results.json',
       'native-dispatch-boundary-results.json','virtual-ink-job-results.json',
       'native-nv-host-results.json','native-nv-arm-results.json','virtual-ink-data-results.json',
       'full-metadata-host-results.json','full-native-nv-results.json','delivery-bootstrap-results.json','spi-package-results.json']
reports={}
for name in names:
    path=ROOT/'analysis'/name
    if path.stat().st_mtime<started:
        raise RuntimeError(f'Stale validation result: {name}')
    reports[name]=json.loads(path.read_text())
sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
         for directory in ('runtime','delivery') for p in sorted((ROOT/directory).iterdir()) if p.suffix in ('.py','.c','.h','.ld')}
summary={
    'source_sha256':sources,
    'arm_elf_sha256':hashlib.sha256((ROOT/'build/virtual_cartridge.arm.elf').read_bytes()).hexdigest(),
    'original_merged_sha256':hashlib.sha256((ROOT/'original/merged.bin').read_bytes()).hexdigest(),
    'reports':reports,
    'physical_printer_or_flash_tested':False,
    'flash_image_generated':True,
    'image_classification':'EXPERIMENTAL SPI installer plus state-preserving runtime promotion',
    'physical_boot_and_power_cut_validation_assigned_to_user':True,
}
(ROOT/'analysis/runtime-verification.json').write_text(json.dumps(summary,indent=2))
print('All runtime validations passed; current-run aggregate saved.')
