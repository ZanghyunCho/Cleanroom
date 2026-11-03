"""Exercise compiled patches and original callers; OS/chip substitutions explicit."""
from pathlib import Path
import json,struct
from native import *
from probe_cartridge_regions import TABLES
ROOT=Path(__file__).resolve().parent

def machine(module):
 m=Boot((ROOT/'inputs/nand-dump/merged-IC2-low-IC3-high.bin').read_bytes());m.u.mem_write(0x43b00000,module);m.u.mem_map(0x43e00000,0x200000);m.u.mem_map(0x7ff00000,0x10000)
 m.u.hook_add(UC_HOOK_CODE,lambda u,a,n,x:m.return_value(0),begin=0x43ba8ad4,end=0x43ba8ad4)
 return m

def run(module):
 m=machine(module);original=(ROOT/'inputs/main-block-3.bin').read_bytes();chip={};calls=[]
 def read(u,a,n,x):
  assert u.reg_read(UC_ARM_REG_R0)==chip['slot'] and u.reg_read(UC_ARM_REG_R1)==0x25
  u.mem_write(u.reg_read(UC_ARM_REG_R2),struct.pack('<H',chip['code']));m.return_value(chip.get('error',0))
 m.u.hook_add(UC_HOOK_CODE,read,begin=0x43b2c0ec,end=0x43b2c0ec)
 tests=0
 for source,off in TABLES.items():
  for kind in range(3):
   for slot,code in enumerate(struct.unpack_from('<10H',original,off+kind*20)):
    for target in TABLES:
     chip.update(slot=slot,code=code,error=0);p=0x43010000;m.u.mem_write(p,struct.pack('<IBBBBII',slot,1,target,0,0,0,0))
     assert m.call(0x43b2c794,p)==1 and m.u.mem_read(p+6,1)[0]==kind
     assert struct.unpack('<II',m.u.mem_read(p+8,8))==[(100,130),(340,390),(680,770)][kind]
     m.u.mem_write(0x7ff029b3,bytes([target]));assert m.call(0x43b278cc,slot)==0
     tests+=2
 # Same-slot checks remain intact across every region; arbitrary identifiers rejected.
 for slot in range(10):
  valid={struct.unpack_from('<H',original,off+k*20+slot*2)[0] for off in TABLES.values() for k in range(3)}
  for code in [0xffff,1234,0]+[struct.unpack_from('<H',original,off+k*20+other*2)[0] for off in TABLES.values() for k in range(3) for other in range(10) if other!=slot]:
   if code in valid:continue
   chip.update(slot=slot,code=code);p=0x43010000;m.u.mem_write(p,struct.pack('<IBBBBII',slot,1,4,0,0,0,0));assert m.call(0x43b2c794,p)==0;tests+=1
 # Maintenance operations must not invoke chip transport or power operations.
 def forbidden(u,a,n,x):raise AssertionError('Physical maintenance transport entered '+hex(a))
 for pc in [0x43b17a80,0x43b1836c,0x43b18358,0x43b1844c,0x43b181e4]:m.u.hook_add(UC_HOOK_CODE,forbidden,begin=pc,end=pc)
 # Preserve unrelated ink cache through all virtual maintenance operations.
 ink_before=bytes((i*29+7)&255 for i in range(120+160));m.u.mem_write(0x43e5d514,ink_before)
 # This combined span includes intervening fields; use the exact disjoint ink arrays.
 ink_status=bytes(m.u.mem_read(0x43e5d514,120));ink_info=bytes(m.u.mem_read(0x43e5d58c,160))
 for slot in [0,1,0,1]:
  assert m.call(0x43b1c230,slot)==1
  assert m.call(0x43b1c948,slot)==1
  assert m.call(0x43b1ddf0,slot)==0
  assert m.call(0x43b16eb0,slot)==0 and m.call(0x43b16edc,slot)==0
 assert m.call(0x43b1bdf8,0x43010000)==0
 assert bytes(m.u.mem_read(0x43e5d514,120))==ink_status
 assert bytes(m.u.mem_read(0x43e5d58c,160))==ink_info
 for state in [0,1,2,3,4,7,9,11,12,255]:
  p=0x43010000;m.u.mem_write(p,bytes([state])*24);m.call(0x43b20654,p)
  for slot in range(2):
   rec=bytes(m.u.mem_read(0x43e5d62c+slot*12,12));assert rec[0]==0 and rec[1]==100 and struct.unpack_from('<I',rec,4)[0]==688000000 and rec[8:10]==b'\0\0'
  assert m.call(0x43b1eb98)==0
 # Check actual maintenance state and metadata read interfaces.
 p=0x43010000;m.u.mem_write(p,bytes([0xa5])*128);m.call(0x43b1eb08,p)
 for slot in range(2):assert m.u.mem_read(p+12*slot,2)==b'\0\x64'
 assert m.u.mem_read(p+24,8)==bytes([0xa5])*8
 m.call(0x43b1e860,p);assert m.u.mem_read(p+1,1)==b'\x02' and m.u.mem_read(p+57,1)==b'\x02'
 # Preserve native request completion, including both original check message handlers.
 completions=[]
 def complete(u,a,n,x):
  pointer=u.reg_read(UC_ARM_REG_R0);completions.append(m.read32(pointer+0x1c));m.return_value(0)
 m.u.hook_add(UC_HOOK_CODE,complete,begin=0x43ba50c0,end=0x43ba50c0)
 for pc in [0x43b15dac,0x43b15e38]:
  p=0x43010000;m.u.mem_write(p,bytes(64));m.u.mem_write(p+0x20,struct.pack('<2H',1,1));m.call(pc,p);assert completions[-1]==1
 # Execute the native maintenance notification formatter and full initialization caller.
 messages=[];buffer=0x430c0000
 def allocate(u,a,n,x):
  pointer=u.reg_read(UC_ARM_REG_R1);u.mem_write(buffer,bytes(1024));m.write32(pointer,buffer);m.return_value(0)
 def send(u,a,n,x):
  messages.append({'channel':u.reg_read(UC_ARM_REG_R0),'bytes':bytes(u.mem_read(buffer,256)).hex()});m.return_value(0)
 m.u.hook_add(UC_HOOK_CODE,allocate,begin=0x43b0e1fc,end=0x43b0e1fc)
 m.u.hook_add(UC_HOOK_CODE,send,begin=0x43b0e214,end=0x43b0e214)
 m.call(0x43b1f8c4);assert messages
 state_message=bytes.fromhex(messages[-1]['bytes'])
 assert struct.unpack_from('<2I',state_message,0x1c)==(0,0)
 assert state_message[0x24:0x26]==b'\x64\x64'
 assert struct.unpack_from('<2I',state_message,0x28)==(688000000,688000000)
 assert m.call(0x43b1c048)==1
 return {'regional_lookup_and_original_caller_cases_passed':tests,'all_4_region_tables_accepted_for_correct_slot':True,'wrong_slot_and_invalid_codes_rejected':True,'maintenance_power_check_rw_and_write_entries_passed':True,'maintenance_physical_transport_not_entered':True,'ink_cached_state_unchanged_by_maintenance_operations':True,'missing_error_full_states_normalized':True,'two_native_request_completions_passed':True,'native_status_notification_reports_both_present_full':True,'native_full_maintenance_initialization_returns_success':True,'maintenance_read_output_bounds_preserved':True,'physical_printer_tested':False,'fixtures':['T-code element 0x25 supplied by synthetic chip-read hook','RAM cache and settings explicitly mapped','Logging and message completion supplied by hooks; maintenance transport hooks fail if entered'],'IES_and_ink_presence_genuine_virtualization_tested':False}
if __name__=='__main__':
 report=run((ROOT/'build/region-maintenance-module.bin').read_bytes());(ROOT/'build/region-maintenance-runtime-results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
