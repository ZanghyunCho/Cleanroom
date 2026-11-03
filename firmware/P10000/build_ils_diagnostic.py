"""Isolate ILS leaf change: published V4 module with exactly 8 bytes restored."""
from pathlib import Path
import hashlib,json,struct
from build_ink_virtual import patched_module as v3_module
from probe_ink_sensor_and_genuine import machine
ROOT=Path(__file__).resolve().parent

def patched_module():
 base,_=v3_module(True);anchor=json.loads((ROOT/'validation/ink-metadata-v4-patches.json').read_text())['decoded_sha256']
 assert hashlib.sha256(base).hexdigest()==anchor,'Current source no longer reproduces published V4'
 original=(ROOT/'inputs/main-block-3.bin').read_bytes();offset=0x3f3a4;out=bytearray(base)
 assert base[offset:offset+8]==bytes.fromhex('0000a0e31eff2fe1')
 out[offset:offset+8]=original[offset:offset+8]
 assert out[:offset]==base[:offset] and out[offset+8:]==base[offset+8:]
 m,_=machine();m.u.mem_write(0x43b00000,bytes(out));cases=[]
 for mask in [0]+[1<<i for i in range(12)]+[0x3ff,0xfff]:
  for i in range(12):m.u.mem_write(0x43e00184+i*28,struct.pack('<H',int(bool(mask&(1<<i)))))
  actual=m.call(0x43b3f3a4);assert actual==mask;cases.append({'input_mask':hex(mask),'native_getter_return':hex(actual)})
 assert bytes(out[0x9a000:0x9c000])==original[0x9a000:0x9c000]
 report={'classification':'DIAGNOSTIC ONLY; NOT A VERIFIED PUMP FIX','baseline':'Published V4, matching reported installed version','baseline_sha256':anchor,'decoded_sha256':hashlib.sha256(out).hexdigest(),'restored_offset':hex(offset),'restored_bytes':original[offset:offset+8].hex(),'only_8_decoded_bytes_restored':True,'sensor_getter_cases':cases,'pressure_driver_0x9a000_to_0x9c000_matches_original':True,'nominal_volume_680_defect_intentionally_not_mixed_into_this_diagnostic':True,'pump_interlocks_modified':False,'physical_pump_tested':False}
 (ROOT/'build/ils-diagnostic-module.bin').write_bytes(out);(ROOT/'build/ils-diagnostic-patches.json').write_text(json.dumps(report,indent=2)+'\n');return bytes(out),report
if __name__=='__main__':print(json.dumps(patched_module()[1],indent=2))
