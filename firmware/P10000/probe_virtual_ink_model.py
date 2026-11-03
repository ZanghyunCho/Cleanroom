"""Compiled word backend + ORIGINAL 77-field decoder; emulator-only ABI mapping."""
from pathlib import Path
import struct,json,os,subprocess
from native import *
from probe_ink_sensor_and_genuine import machine
ROOT=Path(__file__).resolve().parent

def compile_backend():
 env=os.environ.copy();env['ZIG_GLOBAL_CACHE_DIR']=str(ROOT/'build/zig-global-cache');env['ZIG_LOCAL_CACHE_DIR']=str(ROOT/'build/zig-local-cache')
 args=[str(ROOT.parent/'P7500/tools/ziglang/zig'),'cc','-target','arm-freestanding-eabi','-mcpu=arm926ej_s','-mfloat-abi=soft','-marm','-Os','-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-unwind-tables','-nostdlib','-Wl,-T,prototypes/ink_chip_model.ld','-Wl,--entry=chip_read','-Wl,--no-gc-sections','-Wl,--build-id=none','prototypes/ink_chip_model.c','-o','build/ink-chip-model.elf']
 subprocess.run(args,cwd=ROOT,env=env,check=True);b=(ROOT/'build/ink-chip-model.elf').read_bytes();shoff=struct.unpack_from('<I',b,32)[0];size,n,st=struct.unpack_from('<HHH',b,46);hdr=[struct.unpack_from('<10I',b,shoff+i*size) for i in range(n)];s=hdr[st];names=b[s[4]:s[4]+s[5]];out={}
 for h in hdr:
  name=names[h[0]:names.find(b'\0',h[0])].decode()
  if h[2]&2 and h[5]:
   assert name in ['.chip_read','.chip_write','.chip_reset'];out[name]=(h[3],b[h[4]:h[4]+h[5]])
 return out

def main():
 m,module=machine();sections=compile_backend();m.u.mem_map(0x47000000,0x1000)
 for name,(address,data) in sections.items():m.u.mem_write(address,data)
 # Redirect the native word-read boundary to actual compiled ARM code, not a return-value oracle.
 def redirect(u,a,n,x):u.reg_write(UC_ARM_REG_PC,sections['.chip_read'][0])
 m.u.hook_add(UC_HOOK_CODE,redirect,begin=0x43b2aa4c,end=0x43b2aa4c)
 m.u.hook_add(UC_HOOK_CODE,lambda u,a,n,x:u.reg_write(UC_ARM_REG_PC,sections['.chip_write'][0]),begin=0x43b2d3c4,end=0x43b2d3c4)
 table=struct.unpack_from('<I',module,0x2cbcc)[0]-0x43b00000;schema=[]
 for i in range(100):
  element,address,mask=struct.unpack_from('<BBH',module,table+4*i)
  if element==0x4e:break
  schema.append({'element':element,'word_address':address,'mask':mask})
 valid=[row for row in schema if row['mask']];reserved=[row for row in schema if not row['mask']];assert len(valid)==77 and [r['element'] for r in reserved]==[0x4d]
 p=0x43010000;count=0;reset_cases=[]
 for region in range(1,5):
  assert m.call(sections['.chip_reset'][0],region)==0
  for slot in range(10):
   m.u.mem_write(p,bytes([0xa5])*8);assert m.call(0x43b2c0ec,slot,0x25,p)==0
   expected=struct.unpack_from('<H',module,0x1927d2+(region-1)*60+40+slot*2)[0]
   assert struct.unpack('<H',m.u.mem_read(p,2))[0]==expected
   assert m.u.mem_read(p+2,6)==bytes([0xa5])*6
   assert m.call(0x43b2c0ec,slot,0x24,p)==0 and struct.unpack('<H',m.u.mem_read(p,2))[0]==3400
   reset_cases.append({'region':region,'slot':slot,'tcode':expected,'capacity_raw':3400});count+=2
 for pattern in [0,0xffff,0xa55a]:
  for slot in range(10):
   for address in range(84):assert m.call(sections['.chip_write'][0],slot,address,pattern)==0
   for row in valid:
    m.u.mem_write(p,bytes([0xa5])*8);assert m.call(0x43b2c0ec,slot,row['element'],p)==0
    shift=(row['mask']&-row['mask']).bit_length()-1;expected=(pattern&row['mask'])>>shift
    assert struct.unpack('<H',m.u.mem_read(p,2))[0]==expected
    assert m.u.mem_read(p+2,6)==bytes([0xa5])*6;count+=1
 write_cases=0
 for slot in range(10):
  for row in valid:
   shift=(row['mask']&-row['mask']).bit_length()-1;maximum=row['mask']>>shift
   # Non-contiguous masks (if present) require values whose shifted bits belong to the mask.
   for value in [0,maximum,maximum&0x55]:
    old=0xa55a;address=row['word_address'];assert m.call(sections['.chip_write'][0],slot,address,old)==0
    assert m.call(0x43b2e65c,slot,row['element'],value)==0
    actual=struct.unpack('<H',m.u.mem_read(0x43080000+2*(slot*84+address),2))[0]
    expected=(old&~row['mask'])|(value<<shift)|0x8000
    assert actual==expected,(slot,row,value,hex(actual),hex(expected))
    assert m.call(0x43b2c0ec,slot,row['element'],p)==0
    assert struct.unpack('<H',m.u.mem_read(p,2))[0]==value
    write_cases+=1
 state_before=bytes(m.u.mem_read(0x43080000,1680))
 for slot,address,value in [(10,0,1),(0,84,1),(0,0,65536),(0xffffffff,0,0)]:assert m.call(sections['.chip_write'][0],slot,address,value)==1
 assert state_before==bytes(m.u.mem_read(0x43080000,1680))
 assert m.call(sections['.chip_read'][0],10,0,p)==1
 assert m.call(sections['.chip_reset'][0],0)==1 and m.call(sections['.chip_reset'][0],5)==1
 report={'scope':'Compiled ARM word backend and original firmware element decoder in emulator; not installed printer code','native_decoder':'0x43b2c0ec','native_word_read_boundary':'0x43b2aa4c','context_bytes':1680,'context_address_is_test_workspace_not_validated_printer_reservation':True,'valid_element_count':77,'reserved_zero_mask_elements':[r['element'] for r in reserved],'native_field_and_identity_cases_passed':count,'native_field_write_readback_cases_passed':write_cases,'original_field_write_entry':'0x43b2e65c','word_write_dirty_marker':'0x8000','non_target_word_bits_preserved':True,'invalid_bounds_rejected_without_mutation':True,'output_bounds_preserved':True,'reset_identity_cases':reset_cases,'element_schema':schema,'all_chip_metadata_semantics_validated':False,'genuine_crypto_implemented':False,'persistent_storage_implemented':False,'this_probe_generates_installable_EFU':False}
 (ROOT/'build/virtual-ink-model-results.json').write_text(json.dumps(report,indent=2)+'\n');print('Compiled backend + original decoder:',count,'read/identity cases;',write_cases,'native write/readback cases; 77 fields')
if __name__=='__main__':main()
