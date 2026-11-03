"""Bounded address-decoding hypotheses against two original MACs; never print keys."""
from pathlib import Path
import hashlib,hmac,json,struct,time
from native import *
ROOT=Path(__file__).resolve().parent;INPUT=ROOT/'inputs';OUT=ROOT/'build'
ADDRESSES=[0x2a366a4c,0x24216420,0x2a38a9a4,0x241f3098,0x24219fec]
MODEL=0x807;MESSAGE=bytes([MODEL%100])+bytes(19)
def derive(material):return hmac.new(material,MESSAGE,hashlib.sha1).digest()
def mac(key,msg):return hmac.new(key,msg,hashlib.sha1).digest()
def main():
 start=time.time();rcx=(INPUT/'efu-extracted/EFU_File.rcx').read_bytes();pairs=[(rcx[p+112:p+112+524288],rcx[p+70:p+90]) for p in [0xd0ee5e,0x110d052]]
 # Validate the model-derived-key calculation using a public synthetic test material.
 u=Updater(rcx);material=bytes(range(20))
 for i,a in enumerate(ADDRESSES):
  u.u.mem_map(a&~4095,4096);u.u.mem_write(a,material[i*4:i*4+4])
 u.call(0x38000924,MODEL,0x43000000);assert bytes(u.u.mem_read(0x43000000,20))==derive(material)
 sources={n:(INPUT/p).read_bytes() for n,p in {
 'nor32':'nand-dump/merged-IC2-low-IC3-high.bin','ic2':'nand-dump/IC2.BIN','ic3':'nand-dump/IC3.BIN','ic6':'additional-ics/IC6_4MB.BIN','ic18':'additional-ics/IC18_4MB.BIN','ic7':'additional-ics/IC7_128Kb.BIN'}.items()}
 seen=set();count=0;matches=[];tested=[]
 for name,data in sources.items():
  for bits in range(10,len(data).bit_length()):
   for shift in range(0,5):
    mask=(1<<bits)-1;offsets=[(a>>shift)&mask for a in ADDRESSES]
    if any(o+4>len(data) for o in offsets):continue
    raw=b''.join(data[o:o+4] for o in offsets)
    for transform in ['little_words','byte_swap32','swap16_halves','swap_bytes16']:
     if transform=='little_words':material=raw
     elif transform=='byte_swap32':material=b''.join(raw[i:i+4][::-1] for i in range(0,20,4))
     elif transform=='swap16_halves':material=b''.join(raw[i+2:i+4]+raw[i:i+2] for i in range(0,20,4))
     else:material=b''.join(raw[i:i+2][::-1] for i in range(0,20,2))
     if material in seen:continue
     seen.add(material);count+=1
     if mac(derive(material),pairs[0][0])==pairs[0][1]:
      both=mac(derive(material),pairs[1][0])==pairs[1][1];match={'source':name,'address_shift':shift,'address_mask_bits':bits,'word_transform':transform,'source_offsets':[hex(o) for o in offsets],'both_original_MACs_match':both};matches.append(match);print('MATCH',json.dumps(match),flush=True)
 print('MAPPING_SUMMARY',count,'unique_material_hypotheses','matches',len(matches),flush=True)
 report={'scope':'Bounded file address/width mapping hypotheses; not proof of physical mapping absent matching MACs','synthetic_model_key_derivation_matches_original_ARM':True,'unique_material_hypotheses':count,'matches':matches,'key_material_not_printed_or_saved':True,'elapsed_seconds':round(time.time()-start,3)}
 (OUT/'key-mapping-results.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
