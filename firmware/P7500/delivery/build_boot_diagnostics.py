"""Prepare key-only and equivalent-instruction CROM diagnostics. No repair claim."""
from pathlib import Path
import hashlib,json,shutil,sys,zipfile,struct,time,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tools'),str(ROOT/'delivery')]
from crom import patch_frame,decode_frame
from prepare_boot_diagnostic import merge,split,apply,sha,ORIGINAL
from probe_native_crom import check
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM
from unicorn.arm_const import *

def main():
 start=time.time();original=(ROOT/'original/merged.bin').read_bytes();assert sha(original)==ORIGINAL
 out=ROOT/'build/boot-diagnostics';out.mkdir(parents=True,exist_ok=True)
 public=(Path('/workspace/p7500-rebuild/analysis/owner-public.bin')).read_bytes();assert len(public)==64
 (out/'owner-public.bin').write_bytes(public)
 oldframe=0x70004;desired,end,_,_=decode_frame(original,oldframe);desired=bytearray(desired)
 offset=0x2c;before=bytes.fromhex('0000a0e1');after=bytes.fromhex('000080e3');assert desired[offset:offset+4]==before
 # Execute both original MOV and equivalent ORR in ARM mode, with flags retained.
 cases=0
 for value in [0,1,0x80000000,0xffffffff,0x12345678]:
  for flags in range(16):
   results=[]
   for code in [before,after]:
    u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0x10000,4096);u.mem_write(0x10000,code);u.reg_write(UC_ARM_REG_CPSR,0x13|(flags<<28));u.reg_write(UC_ARM_REG_R0,value);u.emu_start(0x10000,0x10004,count=1);results.append((u.reg_read(UC_ARM_REG_R0),u.reg_read(UC_ARM_REG_CPSR)))
   assert results[0]==results[1];cases+=1
 desired[offset:offset+4]=after
 changed=[i for i,(a,b) in enumerate(zip(desired,decode_frame(original,oldframe)[0])) if a!=b];assert changed==[0x2e,0x2f]
 frame,codec=patch_frame(original,oldframe,bytes(desired));assert decode_frame(frame,0)[0]==desired
 second_end=end+int.from_bytes(original[end+2:end+6],'big');second=original[end:second_end]
 patch=b'CROM'+frame+second;patch_end=max(second_end,0x70000+len(patch))
 assert all(v==255 for v in original[second_end:patch_end]);patch+=b'\xff'*(patch_end-0x70000-len(patch))
 (out/'crom-nop.patch').write_bytes(patch)
 key_image=bytearray(original)
 for off in [0x7010,0x6d000]:key_image[off:off+64]=public
 nop_image=bytearray(original);nop_image[0x70000:patch_end]=patch
 assert nop_image[:0x70000]==original[:0x70000] and nop_image[patch_end:]==original[patch_end:]
 assert key_image[0x7050:0x6d000]==original[0x7050:0x6d000] and key_image[0x6d040:]==original[0x6d040:]
 manifest={'classification':'BOOT DIAGNOSTICS ONLY; NO VIRTUALIZATION; PHYSICAL BOOT NOT VERIFIED','original_merged_sha256':ORIGINAL,'variants':{
  'key-only':{'purpose':'Only two public-key copies differ; original CROM, native startup and NV definitions retained','offsets':[0x7010,0x6d000],'public_sha256':sha(public),'merged_sha256':sha(key_image)},
  'crom-nop':{'purpose':'Only equivalent MOV R0,R0 -> ORR R0,R0,#0 instruction change, then CROM re-encoding; original public keys and NV definitions retained','instruction_address':'0x433e002c','decoded_offset':offset,'original_bytes':before.hex(),'replacement_bytes':after.hex(),'changed_decoded_offsets':[hex(x) for x in changed],'arm_equivalence_cases_passed':cases,'rom_range':[0x70000,patch_end],'patch_sha256':sha(patch),'merged_sha256':sha(nop_image),'codec':codec}}}
 for name,data in [('key-only',key_image),('crom-nop',nop_image)]:
  chips=split(data);assert merge(*chips)==data
  manifest['variants'][name]['chips']={role:{'bytes':len(b),'sha256':sha(b)} for role,b in zip(['IC13','IC14'],chips)}
 (out/'diagnostic-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 for name in ['key-only','crom-nop']:assert apply(original,name,manifest,out)==(key_image if name=='key-only' else nop_image)
 native=check('crom_nop_only',nop_image);assert native['native_decode_return']==1 and all(f['all_bytes_equal_python_decoder'] for f in native['frames'])
 shutil.copyfile(ROOT/'delivery/prepare_boot_diagnostic.py',out/'prepare_boot_diagnostic.py');shutil.copyfile(ROOT/'delivery/BOOT-DIAGNOSTICS.ko.md',out/'README.ko.md')
 cli_checks=[]
 with tempfile.TemporaryDirectory(prefix='p7500-boot-diag-cli-') as temp:
  for variant in ['key-only','crom-nop']:
   dst=Path(temp)/variant
   subprocess.run([sys.executable,str(out/'prepare_boot_diagnostic.py'),variant,str(ROOT/'original/IC3.BIN'),str(ROOT/'original/IC4.BIN'),str(dst)],check=True,capture_output=True)
   for role in ['IC13','IC14']:
    p=dst/(role+'.BIN');assert p.stat().st_size==67108864 and sha(p.read_bytes())==manifest['variants'][variant]['chips'][role]['sha256']
   cli_checks.append({'variant':variant,'cli_executed_from_packaged_script':True,'both_output_file_sizes_and_hashes_verified':True})
 report={'generator_cli_checks':cli_checks,'classification':manifest['classification'],'original_inputs_checked':True,'key_only_changes_public_keys_only':True,'crom_nop_retains_original_keys_nv_and_all_runtime_hooks':True,'equivalent_instruction_cases':cases,'native_crom_probe':native,'physical_printer_boot_verified':False,'elapsed_seconds':round(time.time()-start,3)}
 (out/'diagnostic-checks.json').write_text(json.dumps(report,indent=2)+'\n');(ROOT/'validation/boot-diagnostic-checks.json').write_text(json.dumps(report,indent=2)+'\n')
 archive=ROOT/'build/P7500-BOOT-ISOLATION-DIAGNOSTICS.zip'
 with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
  for name in ['owner-public.bin','crom-nop.patch','diagnostic-manifest.json','prepare_boot_diagnostic.py','README.ko.md','diagnostic-checks.json']:z.write(out/name,name)
 with zipfile.ZipFile(archive) as z:assert z.testzip() is None
 print(json.dumps({'artifact':str(archive),'sha256':sha(archive.read_bytes()),'bytes':archive.stat().st_size,'report':report},indent=2))
if __name__=='__main__':main()
