"""Original cached-status readers with explicit RAM fixtures, not physical sensor tests."""
from pathlib import Path
import struct,json
from native import *
ROOT=Path(__file__).resolve().parent

def main():
 data=(ROOT/'inputs/main-block-3.bin').read_bytes();m=Boot((ROOT/'inputs/nand-dump/merged-IC2-low-IC3-high.bin').read_bytes())
 m.u.mem_write(0x43b00000,data);m.u.mem_map(0x43e00000,0x200000)
 m.u.hook_add(UC_HOOK_CODE,lambda u,a,n,x:m.return_value(0),begin=0x43ba8ad4,end=0x43ba8ad4)
 status=struct.unpack_from('<I',data,0x1e810)[0];cases=[]
 for label,slots,expected in [('all_normal',[],1),('all_status_one',list(range(10)),0)]+[(f'one_nonzero_slot_{s}',[s],0) for s in range(10)]:
  cache=bytearray(120)
  for s in slots:cache[12*s]=1
  m.u.mem_write(status,bytes(cache));out=0x43010000;m.u.mem_write(out,bytes([0xa5])*48)
  all_usable=m.call(0x43b1e46c);m.call(0x43b1aa94,out);flags=struct.unpack('<10H',m.u.mem_read(out,20))
  assert all_usable==expected and flags==tuple(0 if s in slots else 1 for s in range(10))
  assert bytes(m.u.mem_read(out+24,24))==bytes([0xa5])*24
  cases.append({'case':label,'all_usable':all_usable,'per_slot_usable':list(flags)})
 report={'scope':'Original cached status consumers, explicit synthetic RAM contents; no physical cartridge/sensor input','status_record_base':hex(status),'record_stride':12,'status_zero_means_usable_for_these_consumers':True,'entry_all_usable':'0x43b1e46c','entry_availability':'0x43b1aa94','cases':cases,'outside_output_boundaries_preserved':True,'does_not_establish_genuine_identity_or_physical_IES_state':True,'patch_or_installable_firmware_generated':False}
 (ROOT/'build/cartridge-status-results.json').write_text(json.dumps(report,indent=2)+'\n');print('12 original ARM cached-status cases passed')
if __name__=='__main__':main()
