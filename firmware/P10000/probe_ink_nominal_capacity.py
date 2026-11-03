"""Prove nominal-volume vs net-weight semantics using original FM001PA parser."""
from pathlib import Path
import json,struct
from probe_ink_sensor_and_genuine import machine
ROOT=Path(__file__).resolve().parent

def main():
 module=(ROOT/'build/ink-virtual-module.bin').read_bytes();m,original=machine();m.u.mem_write(0x43b00000,module);m.u.mem_write(0x7ff029b3,b'\x04');assert m.call(0x43b1ce48)==1
 cases=[]
 for kind,(net,nominal) in enumerate([(100,110),(340,350),(680,700)]):
  for slot in range(10):
   tcode=struct.unpack_from('<H',original,0x192886+kind*20+slot*2)[0]
   assert m.call(0x43b2e65c,slot,0x25,tcode)==0
   assert m.call(0x43b2e65c,slot,0x24,net*5)==0
   m.call(0x43b2606c,slot)
   observed_nominal=struct.unpack('<H',m.u.mem_read(0x43e5d58c+slot*16,2))[0]
   observed_net=struct.unpack('<H',m.u.mem_read(0x43e5d664+slot*56+8,2))[0]
   assert (observed_net,observed_nominal)==(net,nominal),(kind,slot,observed_net,observed_nominal)
   cases.append({'class':kind,'slot':slot,'Tcode':tcode,'net_weight_field':observed_net,'nominal_volume_field':observed_nominal})
 report={'scope':'Original parser 0x43b2606c over virtual chip words; no physical pump test','entry':'0x43b2606c','native_cases':cases,'confirmed_V3_and_V4_template_defect':'information record first halfword is 680 but native class-2 output is 700','causality_for_reported_pump_failure_established':False}
 (ROOT/'build/ink-nominal-capacity-results.json').write_text(json.dumps(report,indent=2)+'\n');print('30 native nominal/net-weight cases passed')
if __name__=='__main__':main()
