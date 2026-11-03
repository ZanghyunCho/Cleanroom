"""Execute original T-code lookup with synthetic chip reads; no hardware emulation claim."""
from pathlib import Path
import struct,json
from native import *
ROOT=Path(__file__).resolve().parent
TABLES={1:0x1927d2,2:0x19280e,3:0x19284a,4:0x192886}
def main():
 data=(ROOT/'inputs/main-block-3.bin').read_bytes();image=(ROOT/'inputs/nand-dump/merged-IC2-low-IC3-high.bin').read_bytes();m=Boot(image);m.u.mem_write(0x43b00000,data)
 m.u.hook_add(UC_HOOK_CODE,lambda u,a,n,x:m.return_value(0),begin=0x43ba8ad4,end=0x43ba8ad4)
 state={};calls=[]
 def read(u,a,n,x):
  slot=u.reg_read(UC_ARM_REG_R0);element=u.reg_read(UC_ARM_REG_R1);dest=u.reg_read(UC_ARM_REG_R2)
  assert slot==state['slot'] and element==0x25
  u.mem_write(dest,struct.pack('<H',state['tcode']));m.return_value(0)
 m.u.hook_add(UC_HOOK_CODE,read,begin=0x43b2c0ec,end=0x43b2c0ec)
 def run(slot,region,tcode):
  state.update(slot=slot,tcode=tcode);p=0x43010000;m.u.mem_write(p,struct.pack('<IBBBBII',slot,1,region,0,0,0,0));result=m.call(0x43b2c794,p)
  return result,bytes(m.u.mem_read(p,16))
 cases=0;rows=[]
 for region,off in TABLES.items():
  classes=[]
  for kind in range(3):
   codes=struct.unpack_from('<10H',data,off+20*kind);quantities=set()
   for slot,code in enumerate(codes):
    result,out=run(slot,region,code);assert result==1 and out[6]==kind
    quantities.add(struct.unpack_from('<II',out,8));cases+=1
   classes.append({'class':kind,'slot_tcodes':['T'+str(code) for code in codes],'raw_capacity_pairs':[list(q) for q in sorted(quantities)]})
  rows.append({'internal_region_id':region,'country_mapping':'UNVERIFIED; do not infer country solely from internal ID','table_offset':hex(off),'classes':classes})
 # A T8026 cartridge is valid for slot zero in internal region four only.
 cross=[]
 for region in TABLES:
  result,_=run(0,region,8026);assert result==(1 if region==4 else 0)
  cross.append({'tcode':'T8026','slot':0,'region':region,'lookup_return':result});cases+=1
 for slot in range(10):
  for region in TABLES:
   result,_=run(slot,region,0xffff);assert result==0;cases+=1
 report={'scope':'Original FM001PA T-code lookup; chip element 0x25 supplied by explicit synthetic read hook','entry':'0x43b2c794','cases_passed':cases,'regions':rows,'T8026_cross_region_control':cross,'invalid_ffff_rejected':True,'country_names_officially_verified':False,'physical_chip_communications_tested':False}
 (ROOT/'build/cartridge-region-results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
