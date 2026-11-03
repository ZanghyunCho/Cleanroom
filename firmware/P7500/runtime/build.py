"""Build identical C sources for host tests and the isolated ARM probe."""
from pathlib import Path
import os
import subprocess

ROOT=Path(__file__).resolve().parents[1]
(ROOT/'build').mkdir(exist_ok=True)
(ROOT/'analysis').mkdir(exist_ok=True)
subprocess.run(['gcc','-std=c11','-Wall','-Wextra','-Werror','-fPIC','-shared','-O2',
                'runtime/virtual_cartridge.c','runtime/native_adapter.c','runtime/native_nv.c','-o','build/libvirtual_cartridge.so'],cwd=ROOT,check=True)
env=os.environ.copy()
env['ZIG_GLOBAL_CACHE_DIR']=str(ROOT/'build/zig-global-cache')
env['ZIG_LOCAL_CACHE_DIR']=str(ROOT/'build/zig-local-cache')
subprocess.run([str(ROOT/'tools/ziglang/zig'),'cc','-target','arm-freestanding-eabi',
               # ARMv5TE integer code runs on Cortex-A9 without relying on the
               # firmware's VFP/NEON enablement or task context-save policy.
               '-mcpu=arm926ej_s','-mfloat-abi=soft','-marm','-Os','-g',
               '-fno-vectorize','-fno-slp-vectorize','-ffreestanding','-fno-builtin',
               '-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables',
               '-nostdlib','-rdynamic','-Wl,-T,runtime/arm.ld','-Wl,--entry=vr_init','-Wl,--build-id=none',
               'runtime/virtual_cartridge.c','runtime/native_adapter.c','runtime/native_nv.c','-o','build/virtual_cartridge.arm.elf'],cwd=ROOT,env=env,check=True)
