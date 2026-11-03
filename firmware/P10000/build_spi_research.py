"""Compare targeted boot-code bypass vs metadata-only gating, from exact FM018GB dump."""
from pathlib import Path
import struct,json,hashlib,time
from native import *
from lzss import decode,encode_preserving
ROOT=Path(__file__).resolve().parent;INPUT=ROOT/'inputs';OUT=ROOT/'build';OUT.mkdir(exist_ok=True)
ORIGINAL='68b953939ffe425203af51309fbd1e7f6a479e0cf2f25c5f05b4a5931749c476'
TARGET=0x1400000;FUNCTION=0x13954;OLD=bytes.fromhex('18109fe5000050e3');NEW=bytes.fromhex('0000a0e31eff2fe1')
def sha(b):return hashlib.sha256(b).hexdigest()
def branch(source,target,condition=14):
 n=target-source-8;assert n%4==0 and -(1<<25)<=n<(1<<25)
 return struct.pack('<I',(condition<<28)|0x0a000000|((n//4)&0xffffff))
def imm(value):
 for rot in range(16):
  n=((value<<(2*rot))|(value>>(32-2*rot)))&0xffffffff if rot else value
  if n<256:return (rot<<8)|n
 raise ValueError('ARM immediate not representable')
def merge(a,b):
 assert len(a)==len(b)==16777216
 out=bytearray(33554432);out[0::4]=a[0::2];out[1::4]=a[1::2];out[2::4]=b[0::2];out[3::4]=b[1::2];return out
def split(d):
 out=[]
 for start in [0,2]:
  c=bytearray(len(d)//2);c[0::2]=d[start::4];c[1::2]=d[start+1::4];out.append(c)
 return out

def make_payload(old,flag,desired=None):
 n,total,packed_size,packed_sum=struct.unpack_from('<4I',old);stream=old[112:112+packed_size];decoded,_=decode(stream)
 assert len(decoded)==n and sum(decoded)&0xffffffff==total and sum(stream)&0xffffffff==packed_sum
 assert decoded[FUNCTION:FUNCTION+8]==OLD
 patched=bytearray(decoded);patched[FUNCTION:FUNCTION+8]=NEW;patched=bytes(patched)
 assert patched[:FUNCTION]==decoded[:FUNCTION] and patched[FUNCTION+8:]==decoded[FUNCTION+8:]
 if desired is not None:
  assert len(desired)==len(decoded) and desired[FUNCTION:FUNCTION+8]==NEW
  patched=bytes(desired)
 replay,_=encode_preserving(stream,decoded);assert replay==stream
 packed,refs=encode_preserving(stream,patched);assert decode(packed)[0]==patched
 header=bytearray(old[:112]);struct.pack_into('<4I',header,0,n,sum(patched)&0xffffffff,len(packed),sum(packed)&0xffffffff);header[32]=flag
 return bytes(header)+packed,patched,{'decoded_bytes':n,'decoded_sha256':sha(patched),'changed_decoded_range':['0x13954','0x1395c'] if desired is None else 'see region-maintenance-patches.json','original_stream_bytes':len(stream),'new_stream_bytes':len(packed),'converted_references':refs,'unchanged_replay_exact_original':True}

def getter_checks(m,remaining):
 m.u.mem_map(0x7ff02000,0x1000);cases=0;maximum=688000000
 for index in [0,1,2,3,0xffffffff]:
  for used in [0,1,123456789,maximum-1,maximum,maximum+1,0xffffffff]:
   for slot in range(3):m.write32(0x7ff02210+16*slot,used)
   assert m.call(0x43b13954,index)==0
   assert m.call(remaining,index)==maximum;cases+=2
 return cases

def validate(original,image,expected,mode):
 m=Boot(image);assert m.call(m.SELF_CHECK)==1
 # Exact-original oracle for the OTHER block only; never substitutes target authentication.
 original_body=original[0xf00000+112:0xf00000+112+524288];original_tag=original[0xf00000+70:0xf00000+90];calls=[]
 def oracle(u,a,n,x):
  p=u.reg_read(UC_ARM_REG_R0);size=u.reg_read(UC_ARM_REG_R1);tag=u.reg_read(UC_ARM_REG_R2)
  assert p==0xf00000+112,'Target authentication was not bypassed'
  same=bytes(u.mem_read(p,size))==original_body and bytes(u.mem_read(tag,20))==original_tag;calls.append({'unchanged_other_block':same});m.return_value(0 if same else 1)
 m.u.hook_add(UC_HOOK_CODE,oracle,begin=m.AUTH,end=m.AUTH)
 assert m.call(m.GATE,1)==1 and len(calls)==1
 assert m.call(0x17e8,1)==1
 actual=bytes(m.u.mem_read(0x43b00000,len(expected)));assert actual==expected
 cases=getter_checks(m,0x43b24d4c)
 # A different active block must still reject a changed authenticated prefix.
 address=0xf00000+112+128;m.u.mem_write(address,bytes([original[address]^1]));assert m.call(m.GATE,1)==0
 return {'mode':mode,'original_boot_self_checksum_passed':True,'original_boot_gate_returned_success':True,'target_hmac_not_called':True,'other_block_authentication_retained':True,'other_block_tamper_rejected_by_exact_original_oracle':True,'original_native_lzss_loader_returned_success':True,'all_native_decoded_bytes_equal_expected':True,'usage_and_remaining_cases_passed':cases,'cryptographic_oracle_limitation':'Only unchanged other block uses exact-original oracle; its HMAC was not computed','full_boot_or_hardware_tested':False}

def main():
 start=time.time();original=(INPUT/'nand-dump/merged-IC2-low-IC3-high.bin').read_bytes();assert sha(original)==ORIGINAL
 old_size=112+struct.unpack_from('<I',original,TARGET+8)[0];old=original[TARGET:TARGET+old_size];reports=[];files={}
 for mode in ['metadata-only','targeted-boot-code']:
  payload,expected,codec=make_payload(old,0 if mode=='metadata-only' else 1);image=bytearray(original)
  assert TARGET+len(payload)<0x1600000
  if len(payload)>old_size:assert all(v==255 for v in original[TARGET+old_size:TARGET+len(payload)])
  image[TARGET:TARGET+len(payload)]=payload;allowed=[(TARGET,TARGET+len(payload))]
  if mode=='targeted-boot-code':
   site=0x18b4;cave=0x1ff00;assert original[site:site+4]==bytes.fromhex('2010d0e5') and original[cave:cave+16]==bytes(16)
   image[site:site+4]=branch(site,cave)
   code=struct.pack('<I',0xe3500000|imm(TARGET))+branch(cave+4,0x18f4,0)+original[site:site+4]+branch(cave+12,site+4)
   assert len(code)==16;image[cave:cave+16]=code
   assert sum(original[:0x1fff0])&0xffffffff==struct.unpack_from('<I',original,0x1fff0)[0]
   struct.pack_into('<I',image,0x1fff0,sum(image[:0x1fff0])&0xffffffff);allowed += [(site,site+4),(cave,cave+16),(0x1fff0,0x1fff4)]
  else:assert image[:0x20000]==original[:0x20000]
  last=0
  for lo,hi in sorted(allowed):assert image[last:lo]==original[last:lo];last=hi
  assert image[last:]==original[last:]
  test=validate(original,bytes(image),expected,mode);chips=split(image);assert merge(*chips)==image
  names=[]
  for role,data in zip(['IC2','IC3'],chips):
   name=f'LAB_UNVERIFIED_FM018GB_{mode}_{role}.BIN';(OUT/name).write_bytes(data);files[name]={'bytes':len(data),'sha256':sha(data)};names.append(name)
  reports.append({'variant':mode,'classification':'LAB ONLY; NOT PHYSICALLY BOOT VERIFIED','merged_sha256':sha(image),'target_header_auth_flag':image[TARGET+32],'boot_code_modified':mode=='targeted-boot-code','allowed_changed_ranges':[[hex(a),hex(b)] for a,b in allowed],'codec':codec,'validation':test,'files':names})
 report={'original_sha256':ORIGINAL,'original_firmware_version':'FM018GB','not_FM001PA':True,'variants':reports,'files':files,'physical_printer_tested':False,'elapsed_seconds':round(time.time()-start,3)}
 (OUT/'spi-research-results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
