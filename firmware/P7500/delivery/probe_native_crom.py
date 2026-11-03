"""Run the original ARM CROM frame walker and copy loop. Huffman ASIC is a fixture."""
from pathlib import Path
import hashlib,json,struct,sys,zipfile,time
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tools'),str(ROOT/'delivery')]
from crom import decode_frame
from prepare import merge
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm_const import *

def sha(b):return hashlib.sha256(b).hexdigest()
def check(label,rom):
 rom=bytes(rom)
 frames=[];p=0x70004
 while rom[p:p+2]==b'\xff\xd8':
  out,end,tokens,info=decode_frame(rom,p)
  frames.append({'start':p,'end':end,'output':out,'tokens':tokens,'literal_offset':end-info['literal_bytes']-p,'token_count':info['token_count']});p=end
 assert len(frames)==2
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_A9)
 for a,n in [(0,0x8000000),(0x433e0000,0x400000),(0xb9dc7000,0x10000),(0x44099000,0x1000),(0x42000000,0x100000),(0x43000000,0x10000),(0x46000000,0x800000),(0x48000000,0x1000)]:u.mem_map(a,n)
 u.mem_write(0,rom);u.mem_write(0x44099000,rom[0x2b7010:0x2b7010+0xae8])
 dests=[0x433e0000,0xb9dc7000];u.mem_write(0x43000000,struct.pack('<3I',*dests,0xffffffff))
 def call(pc,*args,count=400000000):
  u.reg_write(UC_ARM_REG_CPSR,0x13);u.reg_write(UC_ARM_REG_SP,0x420ff000);u.reg_write(UC_ARM_REG_LR,0x48000000)
  for reg,v in zip([UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3],args):u.reg_write(reg,v)
  u.emu_start(pc,0x48000000,count=count);assert u.reg_read(UC_ARM_REG_PC)==0x48000000,hex(u.reg_read(UC_ARM_REG_PC))
  return u.reg_read(UC_ARM_REG_R0)
 count=call(0x440998f8,0x70000,0x43000000,0x43001000);assert count==2
 table=struct.unpack('<4I',u.mem_read(0x43001000,16));assert table==(frames[0]['start'],dests[0],frames[1]['start'],dests[1])
 initialized=set();fixture_calls=0
 def helper(uc,address,size,user):
  nonlocal fixture_calls
  if address!=0x44099664:return
  fixture_calls+=1;ctx=uc.reg_read(UC_ARM_REG_R0)
  if ctx not in initialized:
   initialized.add(ctx);uc.mem_write(ctx,bytes([2,2]))
   for i,f in enumerate(frames):
    token_addr=0x46000000+i*0x400000;uc.mem_write(token_addr,f['tokens'])
    metadata=struct.unpack('<I',uc.mem_read(ctx+0xc,4))[0]
    uc.mem_write(ctx+0x3c+4*i,struct.pack('<I',token_addr));uc.mem_write(metadata+0x10+28*i,struct.pack('<II',f['token_count'],f['literal_offset']))
  uc.reg_write(UC_ARM_REG_R0,1);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
 u.hook_add(UC_HOOK_CODE,helper,begin=0x44099664,end=0x44099664)
 result=call(0x4409997c,0x43001000,2);rows=[]
 for f,dest in zip(frames,dests):
  actual=bytes(u.mem_read(dest,len(f['output'])));bad=next((i for i,(a,b) in enumerate(zip(actual,f['output'])) if a!=b),None)
  rows.append({'frame_start':hex(f['start']),'destination':hex(dest),'bytes':len(actual),'all_bytes_equal_python_decoder':actual==f['output'],'first_mismatch':None if bad is None else hex(bad),'native_output_sha256':sha(actual),'python_output_sha256':sha(f['output'])})
 return {'variant':label,'native_parser_returned_frames':count,'native_decode_return':result,'huffman_fixture_calls':fixture_calls,'frames':rows}
def main():
 start=time.time();original=(ROOT/'original/merged.bin').read_bytes()
 with zipfile.ZipFile(ROOT/'build/P7500-EXPERIMENTAL-SPI.zip') as z:
  installer=merge(z.read('EXPERIMENTAL_INSTALLER_IC13.BIN'),z.read('EXPERIMENTAL_INSTALLER_IC14.BIN'))
 rows=[]
 for label,rom in [('original',original),('delivered_installer',installer)]:
  row=check(label,rom);rows.append(row);print(json.dumps(row),flush=True)
  assert row['native_decode_return']==1 and all(f['all_bytes_equal_python_decoder'] for f in row['frames']), 'Native copy fixture/model mismatch; cannot treat as firmware evidence'
 report={'scope':'Actual original ARM frame parser and LZ/literal copy execution; Huffman ASIC tokens supplied by Python fixture','variants':rows,'physical_printer_tested':False,'full_boot_tested':False,'elapsed_seconds':round(time.time()-start,3)}
 (ROOT/'analysis/boot-failure/native-crom-results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
