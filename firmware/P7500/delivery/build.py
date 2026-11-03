"""Build actual-address experimental payloads, verifying every original trampoline."""
from pathlib import Path
import os,struct,subprocess,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from capstone import Cs,CS_ARCH_ARM,CS_MODE_ARM
TRAMPOLINES={'original_get40':0x433f57c0,'original_set40':0x433f5934,'original_add40':0x433f5b4c,
 'original_cover':0x43403f68,'original_mirror':0x434027b0,'original_presence':0x43408d30,
 'original_waste_info':0x433f2f04,'original_capacity':0x434039b0,'original_layout':0x435f364c,
 'original_restore':0x433f2f94,'original_validate':0x435f3274,'original_write':0x435f1e58}
def main():
 b=(ROOT/'decoded/crom-00070000-0.bin').read_bytes();md=Cs(CS_ARCH_ARM,CS_MODE_ARM)
 lines=['.syntax unified','.arm','.section .text.trampolines,"ax",%progbits']
 for name,entry in TRAMPOLINES.items():
  raw=b[entry-0x433e0000:entry-0x433e0000+8];ins=list(md.disasm(raw,entry))
  words=list(struct.unpack('<2I',raw));literal=None
  if len(ins)==2 and ins[0].mnemonic=='ldr' and '[pc,' in ins[0].op_str and 'pc' not in ins[1].op_str:
   first=words[0]
   if (first&0x0f7f0000)!=0x051f0000:raise RuntimeError('Unsupported literal-load encoding')
   address=entry+8+(1 if first&(1<<23) else -1)*(first&0xfff)
   literal=struct.unpack_from('<I',b,address-0x433e0000)[0]
   words[0]=(first&0xf000f000)|0x059f0008
  elif len(ins)!=2 or any('pc' in x.op_str or x.mnemonic.startswith(('b','ldm')) for x in ins):
   raise RuntimeError(f'{name}: unsupported prologue relocation')
  lines+=['.balign 4',f'.global {name}',f'.type {name},%function',f'{name}:',
          *[f'.word 0x{x:08x}' for x in words],'.word 0xe51ff004',f'.word 0x{entry+8:08x}']
  if literal is not None:lines.append(f'.word 0x{literal:08x}')
 build=ROOT/'build/delivery';build.mkdir(parents=True,exist_ok=True)
 (build/'trampolines.S').write_text('\n'.join(lines)+'\n')
 env=os.environ.copy();env['ZIG_GLOBAL_CACHE_DIR']=str(ROOT/'build/zig-global-cache');env['ZIG_LOCAL_CACHE_DIR']=str(ROOT/'build/zig-local-cache')
 for installer in (0,1):
  name='installer' if installer else 'runtime'
  args=[str(ROOT/'tools/ziglang/zig'),'cc','-target','arm-freestanding-eabi','-mcpu=arm926ej_s',
   '-mfloat-abi=soft','-marm','-Oz','-g','-flto','-ffunction-sections','-fdata-sections','-fno-vectorize',
   '-fno-slp-vectorize','-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-unwind-tables',
   '-fno-asynchronous-unwind-tables','-nostdlib','-Iruntime','-DP7500_DELIVERY=1',f'-DINSTALLER={installer}',
   '-Wl,-T,delivery/payload.ld','-Wl,--entry=payload_layout','-Wl,--gc-sections','-Wl,--build-id=none',
   'runtime/virtual_cartridge.c','runtime/native_adapter.c','runtime/metadata_store.c','runtime/full_nv.c',
   'delivery/bootstrap.c',str(build/'trampolines.S'),'-o',str(build/f'{name}.elf')]
  subprocess.run(args,cwd=ROOT,env=env,check=True)
  print(name,'payload built')
if __name__=='__main__':main()
