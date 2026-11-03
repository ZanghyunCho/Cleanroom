"""Original ARM sensor/end and genuine-report paths, with explicit OS/RAM fixtures."""
from pathlib import Path
import struct,json
from native import *
ROOT=Path(__file__).resolve().parent

def machine():
 module=(ROOT/'inputs/main-block-3.bin').read_bytes();m=Boot((ROOT/'inputs/nand-dump/merged-IC2-low-IC3-high.bin').read_bytes());m.u.mem_write(0x43b00000,module);m.u.mem_map(0x43e00000,0x200000);m.u.mem_map(0x7ff00000,0x10000)
 m.u.hook_add(UC_HOOK_CODE,lambda u,a,n,x:m.return_value(0),begin=0x43ba8ad4,end=0x43ba8ad4)
 return m,module

def sensor_cases():
 m,module=machine();addresses=[0x43e00184+i*28 for i in range(12)]
 # Last two cross the descriptor array boundary; exact addresses follow native loads.
 assert addresses==[0x43e000ac+0xd8,0x43e000ac+0xf4]+[0x43e001ac+x for x in [0x10,0x2c,0x48,0x64,0x80,0x9c,0xb8,0xd4,0xf0]]+[0x43e002ac+0xc]
 errors=[]
 def error(u,a,n,x):errors.append([u.reg_read(UC_ARM_REG_R0),u.reg_read(UC_ARM_REG_R1)]);m.return_value(0)
 m.u.hook_add(UC_HOOK_CODE,error,begin=0x43b2d6a4,end=0x43b2d6a4)
 def set_mask(mask):
  for i,a in enumerate(addresses):m.u.mem_write(a,struct.pack('<H',int(bool(mask&(1<<i)))))
 def run():
  p=0x43010000;m.u.mem_write(p,struct.pack('<20H',*([1]*10+[0xa5a5]*10)));m.u.mem_write(0x43e5d514,bytes(120));errors.clear();result=m.call(0x43b19804,p)
  return result,list(struct.unpack('<10H',m.u.mem_read(p+20,20))),bytes(m.u.mem_read(0x43e5d514,120)),list(errors)
 masks=[0]+[1<<i for i in range(12)]+[0x3ff,0xfff];baseline=[]
 for mask in masks:
  set_mask(mask);assert m.call(0x43b3f3a4)==mask
  result,out,status,err=run();expected=[int(bool(mask&(1<<i))) for i in range(10)]
  assert result==1,(hex(mask),result,out,expected,err)
  assert [status[12*i] for i in range(10)]==[6 if bit else 0 for bit in expected]
  assert err==[[i,0x25] for i,bit in enumerate(expected) if bit]
  baseline.append({'raw_debounced_mask':hex(mask),'observed_end_result_flags':out,'slot_status_codes':[status[12*i] for i in range(10)],'published_error_count':len(err)})
 # Candidate leaf patch only; run same ORIGINAL caller, without a result oracle.
 m.u.mem_write(0x43b3f3a4,bytes.fromhex('0000a0e31eff2fe1'));m.u.ctl_remove_cache(0x43b3f3a4,0x43b3f3b0);patched=[]
 for mask in masks:
  set_mask(mask);before=[bytes(m.u.mem_read(a,2)) for a in addresses];result,out,status,err=run()
  assert result==1 and out==[0]*10 and not err and all(status[12*i]==0 for i in range(10)),(hex(mask),result,out,err)
  assert before==[bytes(m.u.mem_read(a,2)) for a in addresses]
  patched.append({'raw_debounced_mask':hex(mask),'end_result_flags':out})
 return {'getter':'0x43b3f3a4','original_caller':'0x43b19804','original_diagnostic_label':'ils','normal_mask_for_this_path':'0x000','descriptor_state_addresses':[hex(a) for a in addresses],'unmodified_cases':baseline,'candidate_leaf_cases':patched,'raw_sensor_cache_not_modified':True,'does_not_establish_electrical_polarity_or_all_physical_sensor_consumers':True}

def genuine_cases():
 m,module=machine();buffer=0x430c0000;messages=[]
 def allocate(u,a,n,x):m.u.mem_write(buffer,bytes(1024));m.write32(u.reg_read(UC_ARM_REG_R1),buffer);m.return_value(0)
 def send(u,a,n,x):messages.append(bytes(u.mem_read(buffer,256)));m.return_value(0)
 for pc,fn in [(0x43b0e1fc,allocate),(0x43b0e214,send),(0x43b0e204,lambda u,a,n,x:m.return_value(0))]:m.u.hook_add(UC_HOOK_CODE,fn,begin=pc,end=pc)
 rows=[];jct=struct.unpack_from('<I',module,0x1497e8)[0]
 for mask in [0]+[1<<i for i in range(10)]+[0x3ff]:
  info=bytearray(160)
  for slot in range(10):struct.pack_into('<H',info,slot*16+4,int(bool(mask&(1<<slot))))
  m.u.mem_write(0x43e5d58c,bytes(info));m.u.mem_write(0x43e5d506,b'\x01\0');m.call(0x43b1edd4);msg=messages[-1]
  assert struct.unpack_from('<H',msg,0x5a)[0]==mask
  m.u.mem_write(jct,bytes(128));m.u.mem_write(buffer,msg);m.call(0x43c49658,buffer)
  assert struct.unpack('<H',m.u.mem_read(jct+0x34,2))[0]==mask
  assert struct.unpack('<H',m.u.mem_read(jct+0x58,2))[0]==mask
  rows.append({'per_slot_non_genuine_mask':hex(mask),'native_message_mask':hex(struct.unpack_from('<H',msg,0x5a)[0]),'native_JCT_reported_mask':hex(struct.unpack('<H',m.u.mem_read(jct+0x34,2))[0])})
 return {'info_cache':'0x43e5d58c','record_stride':16,'non_genuine_field_offset':4,'native_sender':'0x43b1edd4','message_non_genuine_mask_offset':'0x5a','native_receiver':'0x43c49658','receiver_state_base':hex(jct),'cases':rows,'zero_mask_is_native_no_non_genuine_report':True,'sticky_receiver_history_also_tested':True,'does_not_claim_actual_chip_cryptographic_authentication':True}

if __name__=='__main__':
 report={'scope':'Original ARM routines and explicit RAM/OS fixtures; no physical printer attached','sensor_end':sensor_cases(),'genuine_reporting':genuine_cases(),'this_probe_generates_installable_EFU':False}
 (ROOT/'build/ink-sensor-genuine-results.json').write_text(json.dumps(report,indent=2)+'\n');print('Original sensor/end and sender-to-JCT genuine paths passed')
