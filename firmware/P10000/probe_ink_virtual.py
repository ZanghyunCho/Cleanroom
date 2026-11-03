"""Integrated V3 ARM paths. No chip/crypto return-value success oracles."""
from pathlib import Path
import json,struct
from probe_ink_sensor_and_genuine import machine
from native import *
ROOT=Path(__file__).resolve().parent

def run(module):
 m,original=machine();m.u.mem_write(0x43b00000,module);m.u.mem_write(0x7ff029b3,b'\x04');messages=[];completed=[];buffer=0x430c0000
 def allocate(u,a,n,x):m.u.mem_write(buffer,bytes(1024));m.write32(u.reg_read(UC_ARM_REG_R1),buffer);m.return_value(0)
 def send(u,a,n,x):messages.append(bytes(u.mem_read(buffer,256)));m.return_value(0)
 def complete(u,a,n,x):p=u.reg_read(UC_ARM_REG_R0);completed.append(bytes(u.mem_read(p,128)));m.return_value(0)
 for pc,fn in [(0x43b0e1fc,allocate),(0x43b0e214,send),(0x43b0e204,lambda u,a,n,x:m.return_value(0)),(0x43ba50c0,complete),(0x43b2dab4,lambda u,a,n,x:m.return_value(0)),(0x43b18a74,lambda u,a,n,x:m.return_value(0))]:m.u.hook_add(UC_HOOK_CODE,fn,begin=pc,end=pc)
 def forbidden(u,a,n,x):raise AssertionError('Chip transport unexpectedly entered '+hex(a))
 for pc in [0x43b29720,0x43b24f2c,0x43b26c70,0x43b2b564,0x43b2b7e8,0x43b1844c,0x43b17a80]:m.u.hook_add(UC_HOOK_CODE,forbidden,begin=pc,end=pc)
 p=0x43010000
 # First native query initializes the in-image word state without a RAM alias outside the module.
 assert m.call(0x43b2c0ec,0,0x25,p)==0 and m.u.mem_read(p,2)==struct.pack('<H',8026)
 assert m.call(0x43b1ce48)==1
 for s,code in enumerate([8026,8022,8029,8020,8025,8021,8028,8027,8024,8023]):
  assert m.call(0x43b2c0ec,s,0x25,p)==0 and m.u.mem_read(p,2)==struct.pack('<H',code)
 # Native field write and read use actual compiled backend and preserve a value across refresh.
 assert m.call(0x43b2e65c,3,0x0f,37)==0
 assert m.call(0x43b199a8)==1
 assert m.call(0x43b2c0ec,3,0x0f,p)==0 and m.u.mem_read(p,2)==struct.pack('<H',37)
 # All 77 valid fields use the integrated production backend, including native RMW writes.
 schema=[];table=struct.unpack_from('<I',original,0x2cbcc)[0]-0x43b00000;field_cases=0
 for i in range(100):
  element,address,mask=struct.unpack_from('<BBH',original,table+4*i)
  if element==0x4e:break
  schema.append({'element':element,'word_address':address,'mask':mask})
 for slot in range(10):
  for row in schema:
   if not row['mask']:continue
   shift=(row['mask']&-row['mask']).bit_length()-1;maximum=row['mask']>>shift
   for value in [0,maximum,maximum&0x55]:
    address=0x43b1a100+2*(slot*84+row['word_address']);before=struct.unpack('<H',m.u.mem_read(address,2))[0]
    assert m.call(0x43b2e65c,slot,row['element'],value)==0
    after=struct.unpack('<H',m.u.mem_read(address,2))[0]
    assert after==((before&~row['mask'])|(value<<shift)|0x8000)
    assert m.call(0x43b2c0ec,slot,row['element'],p)==0
    assert struct.unpack('<H',m.u.mem_read(p,2))[0]==value;field_cases+=1
 m.u.mem_write(0x43b1a790,bytes(4));assert m.call(0x43b199a8)==1
 # Selected operation handlers preserve surrounding buffers.
 for pc,ret in [(0x43b1b328,1),(0x43b19424,0),(0x43b1b450,1),(0x43b1e274,1)]:
  m.u.mem_write(p,bytes([0xa5])*128);assert m.call(pc,p)==ret
  if pc==0x43b1b328:
   assert struct.unpack('<10H',m.u.mem_read(p,20))==(1,)*10 and m.u.mem_read(p+20,8)==bytes([0xa5])*8
 # Physical ILS descriptor states all active; the production getter still reports normal.
 for i in range(12):m.u.mem_write(0x43e00184+i*28,b'\x01\0')
 assert m.call(0x43b3f3a4)==0
 m.u.mem_write(p,struct.pack('<20H',*([1]*10+[0xa5a5]*10)));assert m.call(0x43b19804,p)==1
 assert struct.unpack('<10H',m.u.mem_read(p+20,20))==(0,)*10
 # Repeated fault/absence publications cannot restore a rejected state.
 for state in [1,2,4,6,7,9,11,12,255]:
  m.u.mem_write(p,bytes([state])*160);m.call(0x43b20014,p);m.call(0x43b1fef4,p)
  for slot in range(10):
   record=bytes(m.u.mem_read(0x43e5d514+12*slot,12));assert record[:2]==b'\0\x64' and struct.unpack_from('<I',record,4)[0]==680000000
   info=bytes(m.u.mem_read(0x43e5d58c+16*slot,16));assert info[4:8]==bytes(4) and info[10]==0
  m.call(0x43b1edd4);msg=messages[-1];assert struct.unpack_from('<H',msg,0x5a)[0]==0
  m.u.mem_write(buffer,msg);m.call(0x43c49658,buffer)
  assert m.u.mem_read(0x43e83e40+0x34,2)==b'\0\0' and m.u.mem_read(0x43e83e40+0x58,2)==b'\0\0'
 assert m.call(0x43b199a8)==1
 # Every original per-slot identity packet says ready and contains an explicitly virtual serial.
 identity=[]
 for s in range(10):
  m.u.mem_write(0x43e5d508,struct.pack('<H',1<<s));m.call(0x43b1f10c,s);msg=messages[-1]
  assert msg[0x1c]==s and struct.unpack_from('<I',msg,0x20)[0]==1
  assert struct.unpack_from('<H',msg,0x3e)[0]==680 and msg[0x60:0x62]==b'V3'
  identity.append({'slot':s,'virtual_serial':msg[0x60:0x6a].decode()})
 m.u.mem_write(0x43e5d504,b'\x01\0');m.call(0x43b1f374);msg=messages[-1]
 assert struct.unpack_from('<10I',msg,0x1c)==(0,)*10
 assert msg[0x44:0x4e]==bytes([100])*10
 assert struct.unpack_from('<10I',msg,0x50)==(680000000,)*10
 # Native public presence handler and completion, with normal work mode and no real CO reads.
 m.u.mem_write(0x43e5d49c,b'\x00');m.u.mem_write(p,bytes(128));m.call(0x43b158a4,p)
 assert struct.unpack_from('<I',completed[-1],0x1c)[0]==1
 assert struct.unpack_from('<10H',completed[-1],0x20)==(1,)*10
 # Native detection request completion, then native upper IKS consumer through an IPC bridge.
 m.u.mem_write(p,bytes(128));m.u.mem_write(p+0x20,struct.pack('<10H',*([1]*10)));m.call(0x43b155ac,p)
 detect_reply=completed[-1];assert struct.unpack_from('<I',detect_reply,0x1c)[0]==1
 detect_flags=detect_reply[0x34:0x48];assert detect_flags==bytes(20)
 bridge={'flags':detect_flags};notices=[]
 def selected(u,a,n,x):u.mem_write(u.reg_read(UC_ARM_REG_R0),struct.pack('<10H',*([1]*10))+bytes(48));m.return_value(0)
 def ipc(u,a,n,x):u.mem_write(u.reg_read(UC_ARM_REG_R0)+20,bridge['flags']);m.return_value(1)
 def notice(u,a,n,x):notices.append(1);m.return_value(0)
 for pc,fn in [(0x43c2a594,selected),(0x43b33e48,ipc),(0x43b3e370,lambda u,a,n,x:m.return_value(0)),(0x43c347cc,notice)]:m.u.hook_add(UC_HOOK_CODE,fn,begin=pc,end=pc)
 m.u.mem_write(p,b'\xa5\xa5');assert m.call(0x43c136d0,p)==1 and m.u.mem_read(p,2)==b'\0\0'
 bridge['flags']=struct.pack('<10H',*([1]*10));m.u.mem_write(p,b'\0\0');assert m.call(0x43c136d0,p)==1 and m.u.mem_read(p,2)==b'\x01\0'
 bridge['flags']=detect_flags
 # Native whole-cartridge check runs patched check + original sensor-end path.
 assert m.call(0x43b1a9a8)==1
 # V2 maintenance stays isolated from ink operation refreshes.
 assert m.call(0x43b1c048)==1
 maintenance=bytes(m.u.mem_read(0x43e5d62c,24));assert m.call(0x43b199a8)==1
 assert bytes(m.u.mem_read(0x43e5d62c,24))==maintenance
 m.call(0x43b1aa94,p);assert struct.unpack('<12H',m.u.mem_read(p,24))==(1,)*12
 return {'native_word_backend_and_field_read_write_passed':True,'integrated_native_field_write_readback_cases_passed':field_cases,'word_state_preserved_across_refresh':True,'synthetic_identity_packets':identity,'native_presence_query_and_completion_passed':True,'native_detection_completion_and_upper_IKS_no_end_passed':True,'upper_IKS_counterexample_empty_flags_detected':True,'native_whole_cartridge_check_passed':True,'fault_and_absence_states_cannot_restore_non_normal_report':True,'native_sender_to_JCT_no_non_genuine_mask':True,'native_status_packet_all_slots_ready_full':True,'ils_raw_active_input_reports_normal_through_native_caller':True,'physical_chip_transport_entries_not_entered':True,'V2_maintenance_preserved':True,'all_12_native_availability_flags_usable':True,'fixtures':['RAM and settings mapped explicitly','Logging, OS allocation/send/free and request completion hooks','NV/date housekeeping at 0x43b2dab4 and 0x43b18a74 stubbed; not storage validation','Original upper IKS job uses an explicit IPC bridge carrying actual native detection reply; selected-slot, mode and notification OS fixtures','No physical chip or cryptographic success oracle'],'physical_printer_tested':False,'factory_authentication_not_reproduced':True,'synthetic_chip_template_semantics_not_fully_characterized':True}
if __name__=='__main__':
 report=run((ROOT/'build/ink-virtual-module.bin').read_bytes());(ROOT/'build/ink-virtual-runtime-results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
