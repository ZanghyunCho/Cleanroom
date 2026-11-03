"""Test original authentication branches. MAC oracle is NOT cryptographic verification."""
from pathlib import Path
import hashlib,json,struct,time
from native import *
ROOT=Path(__file__).resolve().parent;INPUT=ROOT/'inputs';OUT=ROOT/'build';OUT.mkdir(exist_ok=True)
def sha(b):return hashlib.sha256(b).hexdigest()

def updater_cases(rcx):
 h=0x110d044;n=14+1410330;original=rcx[h:h+n];rows=[]
 for label,outer,inner,mutate,repair,expected,auth_count in [
  ('original_with_exact_original_pair_oracle',1,1,False,True,1,1),
  ('modified_prefix_auth_retained',1,1,True,True,0,1),
  ('outer_only_clear',0,1,True,True,1,0),
  ('inner_only_clear',1,0,True,True,0,0),
  ('both_flags_clear',0,0,True,True,1,0),
  ('both_clear_bad_checksum',0,0,True,False,1,0)]:
  m=Updater(rcx);request=bytearray(original);request[1]=outer;request[14+32]=inner
  if mutate:request[14+112+128]^=1
  struct.pack_into('<I',request,10,(sum(request[14:])&0xffffffff)^(0 if repair else 1))
  m.u.mem_write(0x43010000,bytes(request));calls=[]
  def oracle(u,a,size,user):
   data=u.reg_read(UC_ARM_REG_R0);length=u.reg_read(UC_ARM_REG_R1);tag=u.reg_read(UC_ARM_REG_R2)
   same=(bytes(u.mem_read(data,length))==original[14+112:14+112+length] and bytes(u.mem_read(tag,20))==original[14+70:14+90])
   calls.append({'bytes':length,'exact_original_input_and_tag':same});m.return_value(0 if same else 1)
  m.u.hook_add(UC_HOOK_CODE,oracle,begin=m.AUTH,end=m.AUTH)
  result=m.call(m.GATE,0x43010000,1);assert result==expected and len(calls)==auth_count,(label,result,calls)
  checksum=m.call(m.SUM,0x43010000,1)
  assert checksum==(1 if repair else 0),(label,checksum)
  rows.append({'case':label,'auth_gate_return':result,'checksum_gate_return':checksum,'auth_calls':calls})
 return rows

def boot_cases(image):
 rows=[];target=0x1400000;original_pairs={}
 for a in [0xf00000,target]:original_pairs[a]=(image[a+112:a+112+524288],image[a+70:a+90])
 for label,flag,change,damage_other,expected,count in [
  ('original_with_exact_original_pair_oracle',1,False,False,1,2),
  ('modified_prefix_auth_retained',1,True,False,0,2),
  ('target_flag_clear',0,True,False,1,1),
  ('target_clear_other_block_damaged',0,True,True,0,1)]:
  m=Boot(image);m.u.mem_write(target+32,bytes([flag]))
  if change:m.u.mem_write(target+112+128,bytes([image[target+112+128]^1]))
  if damage_other:m.u.mem_write(0xf00000+112+128,bytes([image[0xf00000+112+128]^1]))
  calls=[]
  def oracle(u,a,size,user):
   data=u.reg_read(UC_ARM_REG_R0);length=u.reg_read(UC_ARM_REG_R1);tag=u.reg_read(UC_ARM_REG_R2);base=data-112;old,oldtag=original_pairs[base]
   same=bytes(u.mem_read(data,length))==old and bytes(u.mem_read(tag,20))==oldtag
   calls.append({'header':hex(base),'exact_original_input_and_tag':same});m.return_value(0 if same else 1)
  m.u.hook_add(UC_HOOK_CODE,oracle,begin=m.AUTH,end=m.AUTH)
  result=m.call(m.GATE,1);assert result==expected and len(calls)==count,(label,result,calls)
  rows.append({'case':label,'return':result,'auth_calls':calls})
 return rows

def original_loader(image,expected):
 m=Boot(image);result=m.call(0x17e8,1);actual=bytes(m.u.mem_read(0x43b00000,len(expected)))
 assert result==1 and actual==expected,(result,sha(actual),sha(expected),m.logs)
 return {'entry':'0x17e8','return':result,'original_native_loader_and_lzss_decoder_executed':True,'bytes':len(actual),'sha256':sha(actual),'all_bytes_equal_python_decode':True,'hardware_or_crypto_fixture_used':False}

def main():
 start=time.time();rcx=(INPUT/'efu-extracted/EFU_File.rcx').read_bytes();image=(INPUT/'nand-dump/merged-IC2-low-IC3-high.bin').read_bytes();expected=(INPUT/'nand-dump/FM018GB-block-1.bin').read_bytes()
 report={'scope':'Original ARM code in Cortex-A9 Unicorn; exact-original MAC oracle used only in gate branch tests, not a real HMAC computation','updater_gate_cases':updater_cases(rcx),'boot_gate_cases':boot_cases(image),'original_native_loader_control':original_loader(image,expected),'physical_printer_tested':False,'elapsed_seconds':round(time.time()-start,3)}
 (OUT/'gate-results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
