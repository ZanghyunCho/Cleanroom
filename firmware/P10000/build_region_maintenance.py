"""Compile bounded in-place ARM patches; extract only explicitly placed code sections."""
from pathlib import Path
import os,subprocess,struct,json,hashlib
ROOT=Path(__file__).resolve().parent
LIMITS={'.p_mt_write0':(0x16eb0,0x2c),'.p_mt_write1':(0x16edc,0x17c),'.p_mt_check':(0x1bdf8,0x158),'.p_mt_power':(0x1c230,0x3d0),'.p_mt_rw':(0x1c948,0x198),'.p_mt_check2':(0x1ddf0,0x78),'.p_mt_status':(0x1c600,0x23c),'.p_mt_status_entry':(0x20654,4),'.p_region':(0x2c794,0x2f0)}
def compile_sections():
 env=os.environ.copy();env['ZIG_GLOBAL_CACHE_DIR']=str(ROOT/'build/zig-global-cache');env['ZIG_LOCAL_CACHE_DIR']=str(ROOT/'build/zig-local-cache')
 cmd=[str(ROOT.parent/'P7500/tools/ziglang/zig'),'cc','-target','arm-freestanding-eabi','-mcpu=arm926ej_s','-mfloat-abi=soft','-marm','-Os','-fno-vectorize','-fno-slp-vectorize','-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-nostdlib','-Wl,-T,patches/region_maintenance.ld','-Wl,--entry=any_region','-Wl,--no-gc-sections','-Wl,--build-id=none','patches/region_maintenance.c','-o','build/region_maintenance.elf']
 subprocess.run(cmd,cwd=ROOT,env=env,check=True)
 b=(ROOT/'build/region_maintenance.elf').read_bytes();assert b[:7]==b'\x7fELF\x01\x01\x01'
 shoff=struct.unpack_from('<I',b,32)[0];entry,n,strings=struct.unpack_from('<HHH',b,46);headers=[struct.unpack_from('<10I',b,shoff+i*entry) for i in range(n)];st=headers[strings];names=b[st[4]:st[4]+st[5]];sections={}
 for h in headers:
  name=names[h[0]:names.find(b'\0',h[0])].decode()
  if name in LIMITS:
   off,limit=LIMITS[name];assert h[3]==0x43b00000+off and 0<h[5]<=limit,(name,h[5],limit)
   sections[name]=(off,b[h[4]:h[4]+h[5]])
  elif h[2]&2 and h[5]:raise AssertionError(('Unexpected allocated section',name))
 assert set(sections)==set(LIMITS)
 return sections

def patched_module():
 original=(ROOT/'inputs/main-block-3.bin').read_bytes();assert hashlib.sha256(original).hexdigest()=='5abd9825c9842eb606a04af6ab8bf236c7d385ca788e1d5bd26657dd7d36b26f'
 sections=compile_sections();out=bytearray(original);ranges=[]
 for name,(off,code) in sections.items():out[off:off+len(code)]=code;ranges.append({'name':name,'offset':hex(off),'bytes':len(code),'original_sha256':hashlib.sha256(original[off:off+len(code)]).hexdigest(),'replacement_sha256':hashlib.sha256(code).hexdigest()})
 def write(off,old,new,name):
  assert original[off:off+len(old)]==old
  out[off:off+len(new)]=new;ranges.append({'name':name,'offset':hex(off),'bytes':len(new)})
 write(0x13954,bytes.fromhex('18109fe5000050e3'),bytes.fromhex('0000a0e31eff2fe1'),'maintenance_usage_zero')
 # Ensure callers cannot temporarily observe missing state before the first virtual power-on.
 write(0x1eb24,bytes.fromhex('0121d0e7'),bytes.fromhex('0020a0e3'),'maintenance_status_read_normal')
 write(0x1eb98,bytes.fromhex('04009fe50000d0e5'),bytes.fromhex('0000a0e31eff2fe1'),'maintenance_unavailable_mask_zero')
 allowed=sorted((int(r['offset'],16),int(r['offset'],16)+r['bytes']) for r in ranges);last=0
 for lo,hi in allowed:assert original[last:lo]==out[last:lo];last=hi
 assert original[last:]==out[last:] and len(original)==len(out)
 (ROOT/'build/region-maintenance-module.bin').write_bytes(out)
 report={'decoded_size_unchanged':True,'decoded_bytes':len(out),'patched_sha256':hashlib.sha256(out).hexdigest(),'ranges':ranges,'ink_absence_genuine_IES_virtualization_included':False}
 (ROOT/'build/region-maintenance-patches.json').write_text(json.dumps(report,indent=2)+'\n')
 return bytes(out),report
if __name__=='__main__':print(json.dumps(patched_module()[1],indent=2))
