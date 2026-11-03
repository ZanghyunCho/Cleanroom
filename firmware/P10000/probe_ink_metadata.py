"""V4 identity metadata consistency through original field and notification readers."""
from pathlib import Path
import struct,json
from native import *
from probe_ink_sensor_and_genuine import machine
ROOT=Path(__file__).resolve().parent

def run(module):
 rows=[]
 for region in range(1,5):
  m,original=machine();m.u.mem_write(0x43b00000,module);m.u.mem_write(0x7ff029b3,bytes([region]));buffer=0x430c0000;messages=[]
  def alloc(u,a,n,x):m.u.mem_write(buffer,bytes(1024));m.write32(u.reg_read(UC_ARM_REG_R1),buffer);m.return_value(0)
  def send(u,a,n,x):messages.append(bytes(u.mem_read(buffer,256)));m.return_value(0)
  for pc,fn in [(0x43b0e1fc,alloc),(0x43b0e214,send)]:m.u.hook_add(UC_HOOK_CODE,fn,begin=pc,end=pc)
  assert m.call(0x43b1ce48)==1
  for slot in range(10):
   p=0x43010000;expected=struct.unpack_from('<H',original,0x1927d2+60*(region-1)+40+slot*2)[0]
   assert m.call(0x43b2c0ec,slot,0x25,p)==0 and m.u.mem_read(p,2)==struct.pack('<H',expected)
   for element,value in [(0x17,26),(0x18,11),(0x19,4),(0x1a,26),(0x1b,11),(0x1c,4)]:
    assert m.call(0x43b2c0ec,slot,element,p)==0 and m.u.mem_read(p,2)==struct.pack('<H',value)
   m.u.mem_write(0x43e5d508,struct.pack('<H',1<<slot));m.call(0x43b1f10c,slot);msg=messages[-1]
   expected_type=0 if region==3 else 1
   assert struct.unpack_from('<I',msg,0x5c)[0]==expected_type
   assert struct.unpack_from('<H',msg,0x34)[0]==expected
   assert [struct.unpack_from('<H',msg,o)[0] for o in [0x28,0x2a,0x2c]]==[26,11,4]
   assert [struct.unpack_from('<H',msg,o)[0] for o in [0x2e,0x30,0x32]]==[26,11,4]
   rows.append({'region':region,'slot':slot,'native_type':expected_type,'native_Tcode':expected,'native_date_fields':[26,11,4],'virtual_serial':msg[0x60:0x6a].decode()})
 return {'cases':rows,'all_40_region_slot_metadata_cases_passed':True,'native_unknown_type_2_not_emitted':True,'raw_chip_and_native_notification_dates_match':True,'dates_are_synthetic_not_actual_product_expiration':True,'Windows_Status_Monitor_rendering_tested':False,'manufacturer_and_ink_type_name_mapping_not_independently_confirmed':True,'physical_printer_tested':False}
if __name__=='__main__':
 data=run((ROOT/'build/ink-metadata-v4-module.bin').read_bytes());(ROOT/'build/ink-metadata-v4-metadata-results.json').write_text(json.dumps(data,indent=2)+'\n');print('40 metadata cases passed')
