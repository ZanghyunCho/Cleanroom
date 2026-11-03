"""FM001PA EFU research variants with metadata-gated blocks; physical testing separate."""
from pathlib import Path
import json,struct,time,zipfile,argparse
from native import *
from build_spi_research import make_payload,getter_checks,sha
ROOT=Path(__file__).resolve().parent; INPUT=ROOT/'inputs'; OUT=ROOT/'build'
def main():
 parser=argparse.ArgumentParser();group=parser.add_mutually_exclusive_group();group.add_argument('--region-maintenance',action='store_true');group.add_argument('--ink-virtual',action='store_true');group.add_argument('--ink-metadata',action='store_true');group.add_argument('--ils-diagnostic',action='store_true');args=parser.parse_args()
 extra=None;runtime=None;ink_runtime=None
 if args.ils_diagnostic:
  from build_ils_diagnostic import patched_module
  extra,ink_runtime=patched_module()
 if args.ink_virtual or args.ink_metadata:
  from build_ink_virtual import patched_module
  from probe_ink_virtual import run as ink_run
  from probe_region_maintenance import run as v2_run
  extra,_=patched_module(metadata_fix=args.ink_metadata);ink_runtime=ink_run(extra);runtime=v2_run(extra)
  if args.ink_metadata:
   from probe_ink_metadata import run as metadata_run
   ink_runtime['metadata']=metadata_run(extra)
  (OUT/('ink-metadata-v4-runtime-results.json' if args.ink_metadata else 'ink-virtual-runtime-results.json')).write_text(json.dumps(ink_runtime,indent=2)+'\n')
  (OUT/('ink-metadata-v4-v2-regression-results.json' if args.ink_metadata else 'ink-virtual-v2-regression-results.json')).write_text(json.dumps(runtime,indent=2)+'\n')
 if args.region_maintenance:
  from build_region_maintenance import patched_module
  from probe_region_maintenance import run
  extra,_=patched_module();runtime=run(extra)
  (OUT/'region-maintenance-runtime-results.json').write_text(json.dumps(runtime,indent=2)+'\n')
 start=time.time();raw=(INPUT/'efu-extracted/EFU_File.rcx').read_bytes()
 assert sha(raw)=='b2f8fbe030603a758a713210b7284a195b7959a8f118a5f9e3ad6167e6acfe6a'
 first=0x52b;end=0x12a030a;record=0x110d044
 kind,flag,address,size,total=struct.unpack_from('<BBIII',raw,record)
 assert (kind,flag,address,size)==(1,1,0x1400000,1410330)
 old=raw[record+14:record+14+size];payload,expected,codec=make_payload(old,0,extra)
 if args.ink_virtual or args.ink_metadata:codec['changed_decoded_range']='see '+('ink-metadata-v4-patches.json' if args.ink_metadata else 'ink-virtual-patches.json')+', including base V2 ranges'
 if args.ils_diagnostic:codec['changed_decoded_range']='see ils-diagnostic-patches.json and unchanged published V4 patch manifest'
 replacement=struct.pack('<BBIII',kind,0,address,len(payload),sum(payload)&0xffffffff)+payload
 component=bytearray(raw[first:record]+replacement+raw[record+14+size:end])
 delta=len(component)-(end-first);assert delta>=0
 assert component[-32:]==raw[end-32:end]
 assert component[36:36+59620]==raw[0x54f:0xee33]
 struct.pack_into('<I',component,17,len(component)-23)
 struct.pack_into('<I',component,28,len(component)-36)
 struct.pack_into('<I',component,32,sum(component[36:])&0xffffffff)
 header=raw[:first].replace(b'5 = "19529183"',('5 = "'+str(len(component))+'"').encode());assert len(header)==first
 changed=header+component+raw[end:]
 assert changed[first+len(component):]==raw[end:]
 # Parse all five records again, not just the changed record.
 pos=0xee34;records=[]
 for i in range(5):
  k,f,a,n,s=struct.unpack_from('<BBIII',changed,pos);body=changed[pos+14:pos+14+n]
  assert len(body)==n and sum(body)&0xffffffff==s
  records.append((pos,k,f,a,n));pos+=14+n
 assert changed[pos:first+len(component)]==raw[end-32:end]
 m=Updater(raw);base=0x60000000;m.u.mem_map(base,0x2000000);m.u.mem_write(base,changed[0xee34:pos]);calls=[]
 original=raw[0xd0ee5e:0xd0ee5e+4186598]
 def oracle(u,a,n,x):
  p=u.reg_read(UC_ARM_REG_R0);length=u.reg_read(UC_ARM_REG_R1);tag=u.reg_read(UC_ARM_REG_R2)
  assert bytes(u.mem_read(p,length))==original[112:112+length]
  assert bytes(u.mem_read(tag,20))==original[70:90]
  calls.append(p);m.return_value(0)
 m.u.hook_add(UC_HOOK_CODE,oracle,begin=m.AUTH,end=m.AUTH)
 assert m.call(m.SUM,base,5)==1 and m.call(m.GATE,base,5)==1 and len(calls)==1
 # Independent original boot decompressor, temporary emulator memory only.
 image=(INPUT/'nand-dump/merged-IC2-low-IC3-high.bin').read_bytes();boot=Boot(image)
 boot.u.mem_write(address,payload);assert boot.call(0x17e8,1)==1
 assert bytes(boot.u.mem_read(0x43b00000,len(expected)))==expected
 cases=getter_checks(boot,0x43b24d70)
 source=INPUT/'extracted/SC-P10000_FM001PA.EFU';dest=OUT/('P10000_FM001PA_V4.5.EFU' if args.ils_diagnostic else ('LAB_UNVERIFIED_FM001PA_INK_METADATA_V4.EFU' if args.ink_metadata else ('LAB_UNVERIFIED_FM001PA_INK_VIRTUAL_V3.EFU' if args.ink_virtual else ('LAB_UNVERIFIED_FM001PA_REGION_MAINTENANCE_V2.EFU' if args.region_maintenance else 'LAB_UNVERIFIED_FM001PA_METADATA_ONLY.EFU'))));entries=[]
 with zipfile.ZipFile(source) as src,zipfile.ZipFile(dest,'w') as dst:
  for info in src.infolist():
   old_entry=src.read(info.filename);new_entry=changed if info.filename=='EFU_File.rcx' else old_entry
   dst.writestr(info,new_entry);entries.append({'name':info.filename,'changed':new_entry!=old_entry,'sha256':sha(new_entry)})
 with zipfile.ZipFile(dest) as z:
  assert z.testzip() is None and z.read('EFU_File.rcx')==changed
  for entry in entries:assert sha(z.read(entry['name']))==entry['sha256']
 report={'classification':'LAB ONLY; TRANSPORT AND PHYSICAL BOOT UNVERIFIED','firmware':'FM001PA','region_maintenance_runtime':runtime,'ink_virtual_runtime':ink_runtime,'output':dest.name,'bytes':dest.stat().st_size,'sha256':sha(dest.read_bytes()),'rcx_sha256':sha(changed),'component_growth_bytes':delta,'codec':codec,'all_five_record_byte_sums_valid':True,'native_updater_sum_gate_passed':True,'native_updater_auth_gate_passed':True,'target_auth_not_called':True,'unchanged_other_block_exact_original_oracle_calls':len(calls),'authentication_code_unchanged':True,'opaque_32_byte_trailer_unchanged_but_not_validated':True,'native_boot_decoder_full_output_exact':True,'getter_and_remaining_cases_passed':cases,'zip_crc_passed':True,'entries':entries,'limitations':['Other block authentication uses an exact-original oracle, not a real MAC calculation','NML front receiver and opaque trailer semantics unresolved','Standalone decompressor test temporarily combines old boot emulator with new module, never outputs a mixed-version SPI image','No physical boot, USB transport, update or power-loss test performed'],'elapsed_seconds':round(time.time()-start,3)}
 (OUT/('ils-diagnostic-efu-results.json' if args.ils_diagnostic else ('ink-metadata-v4-efu-results.json' if args.ink_metadata else ('ink-virtual-efu-results.json' if args.ink_virtual else ('region-maintenance-efu-results.json' if args.region_maintenance else 'efu-research-results.json'))))).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
