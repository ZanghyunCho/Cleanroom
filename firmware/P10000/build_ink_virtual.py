"""V3 in-place integration over V2, state in replaced cover-handler image space."""
from pathlib import Path
import struct,os,subprocess,json,hashlib
from build_region_maintenance import patched_module as v2_module
ROOT=Path(__file__).resolve().parent
ADDRESSES={'.ink_check':0x19424,'.ink_refresh':0x199a8,'.ink_state':0x1a100,'.ink_detect':0x1ab7c,'.ink_presence':0x1b328,'.ink_rw':0x1b450,'.ink_power':0x1ce48,'.chip_read':0x1cf00,'.chip_write':0x1d000,'.chip_reset':0x1d100,'.ink_info':0x1d300,'.ink_status':0x1d600,'.ink_ensure':0x1d900,'.ink_flush':0x1e274,'.ink_info_entry':0x1fef4,'.ink_status_entry':0x20014,'.ink_read_entry':0x2aa4c,'.ink_write_entry':0x2d3c4,'.ink_ils':0x3f3a4}
DEAD=[(0x19424,0x197b4),(0x199a8,0x1a8f8),(0x1ab7c,0x1aed8),(0x1b328,0x1b3cc),(0x1b450,0x1b978),(0x1ce48,0x1ddf0),(0x1e274,0x1e2c0),(0x1fef4,0x1ffe4),(0x20014,0x200b0),(0x2aa4c,0x2ab80),(0x2d3c4,0x2d4c0),(0x3f3a4,0x3f448)]
ENTRIES={0x19424,0x199a8,0x1ab7c,0x1b328,0x1b450,0x1ce48,0x1e274,0x1fef4,0x20014,0x2aa4c,0x2d3c4,0x3f3a4}
def compile_sections(metadata_fix=False):
 env=os.environ.copy();env['ZIG_GLOBAL_CACHE_DIR']=str(ROOT/'build/zig-global-cache');env['ZIG_LOCAL_CACHE_DIR']=str(ROOT/'build/zig-local-cache')
 args=[str(ROOT.parent/'P7500/tools/ziglang/zig'),'cc','-target','arm-freestanding-eabi','-mcpu=arm926ej_s','-mfloat-abi=soft','-marm','-Os','-fno-vectorize','-fno-slp-vectorize','-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-DCHIP_PRODUCTION=1','-DCHIP_STATE_ADDRESS=0x43b1a100','-nostdlib','-Wl,-T,patches/ink_virtual.ld','-Wl,--entry=ink_refresh','-Wl,--no-gc-sections','-Wl,--build-id=none','patches/ink_virtual.c','prototypes/ink_chip_model.c','-o','build/ink-virtual.elf']
 if metadata_fix:args.insert(2,'-DINK_METADATA_FIX=1')
 subprocess.run(args,cwd=ROOT,env=env,check=True);b=(ROOT/'build/ink-virtual.elf').read_bytes();shoff=struct.unpack_from('<I',b,32)[0];size,n,st=struct.unpack_from('<HHH',b,46);hdr=[struct.unpack_from('<10I',b,shoff+i*size) for i in range(n)];s=hdr[st];names=b[s[4]:s[4]+s[5]];out={}
 for h in hdr:
  name=names[h[0]:names.find(b'\0',h[0])].decode()
  if h[2]&2 and h[5]:
   assert name in ADDRESSES and h[3]==0x43b00000+ADDRESSES[name],name
   out[name]=(ADDRESSES[name],bytes(h[5]) if h[1]==8 else b[h[4]:h[4]+h[5]])
 assert set(out)==set(ADDRESSES)
 assert out['.ink_state'][1]==bytes(1684)
 ranges=sorted((o,o+len(d)) for o,d in out.values())
 for (a,b),(c,d) in zip(ranges,ranges[1:]):assert b<=c
 return out

def patched_module(metadata_fix=False):
 base,v2=v2_module();original=(ROOT/'inputs/main-block-3.bin').read_bytes();out=bytearray(base);sections=compile_sections(metadata_fix);changes=[]
 # No surviving direct branch may enter replaced bodies except their public entries.
 branch_hits=[]
 for off in range(0,len(original)-4,4):
  if any(lo<=off<hi for lo,hi in DEAD):continue
  w=struct.unpack_from('<I',original,off)[0]
  if w&0x0e000000!=0x0a000000 or w>>28==15:continue
  disp=w&0xffffff;disp=disp-0x1000000 if disp&0x800000 else disp;target=off+8+disp*4
  if any(lo<=target<hi for lo,hi in DEAD) and target not in ENTRIES:branch_hits.append([hex(off),hex(target)])
 assert not branch_hits,branch_hits
 # State range must not have direct literal references outside the removed bodies.
 refs=[]
 for off in range(0,len(original)-4,4):
  if any(lo<=off<hi for lo,hi in DEAD):continue
  value=struct.unpack_from('<I',original,off)[0]
  if 0x43b1a100<=value<0x43b1a794:refs.append(hex(off))
 assert not refs,refs
 for name,(off,data) in sections.items():
  assert not any(off<r_end and r_start<off+len(data) for r_start,r_end in [(int(r['offset'],16),int(r['offset'],16)+r['bytes']) for r in v2['ranges']])
  out[off:off+len(data)]=data;changes.append({'section':name,'offset':hex(off),'bytes':len(data),'replacement_sha256':hashlib.sha256(data).hexdigest()})
 # Data MPU permissions are RW for the RAM region containing the reclaimed image space.
 assert struct.unpack_from('<I',original,0xdfb0)[0]==0xfffc
 assert ((0xfffc>>(4*2))&3)==3
 last=0
 for lo,hi in sorted((o,o+len(d)) for o,d in sections.values()):assert out[last:lo]==base[last:lo];last=hi
 assert out[last:]==base[last:] and len(out)==len(base)
 report={'metadata_fix':metadata_fix,'base_V2_patch_report':v2,'new_ranges':changes,'state_address':'0x43b1a100','state_bytes':1684,'state_in_replaced_cover_handler':True,'surviving_interior_direct_branch_hits':branch_hits,'external_literal_references_to_state':refs,'MPU_data_access_region4_RW_from_original_setup':True,'original_module_size_preserved':True,'decoded_sha256':hashlib.sha256(out).hexdigest(),'factory_authentication_not_reproduced':True,'identity_metadata_is_synthetic':True,'state_not_persistent_across_reboot':True,'physical_printer_tested':False}
 (ROOT/('build/ink-metadata-v4-module.bin' if metadata_fix else 'build/ink-virtual-module.bin')).write_bytes(out);(ROOT/('build/ink-metadata-v4-patches.json' if metadata_fix else 'build/ink-virtual-patches.json')).write_text(json.dumps(report,indent=2)+'\n');return bytes(out),report
if __name__=='__main__':print(json.dumps(patched_module()[1],indent=2))
