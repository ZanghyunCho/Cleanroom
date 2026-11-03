"""Assemble an experimental actual-address module; never use emulator addresses."""
from pathlib import Path
import hashlib,json,struct,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'runtime'))
from elftools.elf.elffile import ELFFile
from probe_compiled_bindings import HOOKS
BASE=0x433e0000;LOW=0x433f7af8;HIGH=0x433fd090
EXTRA={0x435f364c:'payload_layout',0x433f2f94:'payload_restore',0x435f3274:'vf_guard',0x435f1e58:'vf_worker_write',
 0x434039b0:'payload_capacity',0x43406c08:'vr_native_waste_read_words',0x43406b38:'vr_native_waste_flush_mirror',
 0x4340716c:'vr_native_waste_flush_mirror',0x43406d24:'vr_native_waste_mode_get',0x43406d98:'vr_native_waste_mode_set',
 0x43406f64:'vr_native_waste_check',0x43407264:'payload_waste_flush',0x434072e4:'payload_waste_control',
 0x43407340:'vr_native_zero',0x43407344:'vr_native_zero'}
def branch(source,target,condition=0xe,link=False):
 delta=target-source-8
 if delta%4 or not -(1<<25)<=delta<(1<<25):raise ValueError('ARM branch range/alignment')
 return struct.pack('<I',(condition<<28)|(0x0b000000 if link else 0x0a000000)|((delta//4)&0xffffff))
def assemble(mode):
 original=(ROOT/'decoded/crom-00070000-0.bin').read_bytes();module=bytearray(original)
 with open(ROOT/f'build/delivery/{mode}.elf','rb') as f:
  elf=ELFFile(f);symbols={s.name:s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols() if s.name}
  capsule=bytearray(struct.pack('<I',0xe7f000f0)*((HIGH-LOW)//4));end=LOW
  for section in elf.iter_sections():
   if not section['sh_flags']&2 or not section['sh_size']:continue
   a=section['sh_addr'];n=section['sh_size']
   if not LOW<=a or a+n>HIGH:raise ValueError(f'Allocated section outside retired region: {section.name}')
   capsule[a-LOW:a-LOW+n]=b'\0'*n if section['sh_type']=='SHT_NOBITS' else section.data();end=max(end,a+n)
 module[LOW-BASE:HIGH-BASE]=capsule
 fallback=symbols['vr_native_unsupported'];redirects=[]
 for off in range(0,len(original)-4,4):
  address=BASE+off;word=struct.unpack_from('<I',original,off)[0]
  if LOW<=address<HIGH:continue
  if (word>>24)&15 in (10,11) and word>>28!=15:
   delta=word&0xffffff;delta=delta-(1<<24) if delta&(1<<23) else delta;target=address+8+delta*4
   if LOW<=target<HIGH:
    module[off:off+4]=branch(address,fallback,word>>28,bool(word&(1<<24)))
    redirects.append({'source':hex(address),'retired_target':hex(target),'replacement':'unsupported'})
 table=0x4365c444
 for off in range(0,len(original)-4,4):
  a=BASE+off;v=struct.unpack_from('<I',original,off)[0]
  if LOW<=v<HIGH and not LOW<=a<HIGH and not table<=a<table+2*116:
   raise ValueError(f'Unclassified external literal pointer into retired code: {a:x}->{v:x}')
 for driver in (0,1):
  for method in range(29):
   symbol='vr_native_zero'
   if driver==0 and method==22:symbol='vr_native_waste_presence'
   if driver==1 and method in (11,12,13,14,15,16):symbol='vr_native_unsupported'
   struct.pack_into('<I',module,table-BASE+driver*116+method*4,symbols[symbol])
 hooks=dict(HOOKS);hooks.update(EXTRA)
 for entry,symbol in hooks.items():
  target=symbols[symbol]
  if not LOW<=target<HIGH:raise ValueError('Hook target not in verified capsule')
  module[entry-BASE:entry-BASE+4]=branch(entry,target)
 # Main-module direct calls into private retired chip code must not exist.
 app=(ROOT/'decoded/crom-002d6c00-0.bin').read_bytes()
 for off in range(0,len(app)-4,4):
  word=struct.unpack_from('<I',app,off)[0]
  if word>>24 in (0xea,0xeb):
   delta=word&0xffffff;delta=delta-(1<<24) if delta&(1<<23) else delta
   if LOW<=0x4409b000+off+8+delta*4<HIGH:raise ValueError('Main module calls retired chip code')
 report={'mode':mode,'scope':'EXPERIMENTAL SPI candidate, physical boot/power-cut not tested',
  'capsule_start':hex(LOW),'capsule_end':hex(HIGH),'allocated_payload_end':hex(end),
  'hooks':{hex(a):{'symbol':n,'target':hex(symbols[n])} for a,n in hooks.items()},
  'redirected_retired_calls':redirects,'original_module_sha256':hashlib.sha256(original).hexdigest(),
  'patched_module_sha256':hashlib.sha256(module).hexdigest(),'physical_printer_tested':False}
 return bytes(module),symbols,report
if __name__=='__main__':
 for mode in ('installer','runtime'):
  module,symbols,report=assemble(mode);out=ROOT/'build/delivery';(out/f'{mode}-module.bin').write_bytes(module)
  (out/f'{mode}-assembly.json').write_text(json.dumps(report,indent=2)+'\n');print(mode,'assembled',report['allocated_payload_end'])
