"""Bounded independent 0x24/0x2a chip-window hypotheses; no key values in output."""
from probe_key_mappings import *
import itertools,argparse

def options(data,addresses):
 seen={}
 for bits in range(10,len(data).bit_length()):
  for shift in range(5):
   offsets=[(a>>shift)&((1<<bits)-1) for a in addresses]
   if any(o+4>len(data) for o in offsets):continue
   raw=b''.join(data[o:o+4] for o in offsets)
   for name,b in [('little',raw),('swap32',b''.join(raw[i:i+4][::-1] for i in range(0,len(raw),4))),('halves',b''.join(raw[i+2:i+4]+raw[i:i+2] for i in range(0,len(raw),4))),('swap16',b''.join(raw[i:i+2][::-1] for i in range(0,len(raw),2)))]:
    seen.setdefault(b,{'bits':bits,'shift':shift,'transform':name,'offsets':[hex(o) for o in offsets]})
 return seen

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--start-index',type=int,default=0);parser.add_argument('--seconds',type=int,default=180);args=parser.parse_args()
 start=time.time();rcx=(INPUT/'efu-extracted/EFU_File.rcx').read_bytes();pairs=[(rcx[p+112:p+112+524288],rcx[p+70:p+90]) for p in [0xd0ee5e,0x110d052]]
 sources={n:(INPUT/p).read_bytes() for n,p in {'nor32':'nand-dump/merged-IC2-low-IC3-high.bin','ic2':'nand-dump/IC2.BIN','ic3':'nand-dump/IC3.BIN','ic6':'additional-ics/IC6_4MB.BIN','ic18':'additional-ics/IC18_4MB.BIN','ic7':'additional-ics/IC7_128Kb.BIN'}.items()}
 groups={}
 for group in [0x24,0x2a]:
  addresses=[a for a in ADDRESSES if a>>24==group];opts={}
  for name,data in sources.items():
   for raw,meta in options(data,addresses).items():opts.setdefault(raw,dict(meta,source=name))
  groups[group]=opts
 print('GROUPS',len(groups[0x24]),len(groups[0x2a]),'maximum_combinations',len(groups[0x24])*len(groups[0x2a]),flush=True)
 matches=[];count=0;complete=True
 for (x,mx),(y,my) in itertools.islice(itertools.product(groups[0x24].items(),groups[0x2a].items()),args.start_index,None):
  material=y[:4]+x[:4]+y[4:8]+x[4:12];key=derive(material);count+=1
  if mac(key,pairs[0][0])==pairs[0][1]:
   row={'window24':mx,'window2a':my,'both_original_MACs_match':mac(key,pairs[1][0])==pairs[1][1]};matches.append(row);print('MATCH',json.dumps(row),flush=True)
  if count%25000==0:print('PROGRESS',count,'seconds',round(time.time()-start,1),flush=True)
  if time.time()-start>args.seconds:complete=False;break
 report={'scope':'Independent masked/scaled windows over provided files; no brute force of arbitrary secret key space','unique_window24_options':len(groups[0x24]),'unique_window2a_options':len(groups[0x2a]),'start_index':args.start_index,'end_index_exclusive':args.start_index+count,'combinations_checked':count,'enumeration_completed':complete,'matches':matches,'no_key_values_printed_or_saved':True,'elapsed_seconds':round(time.time()-start,3)}
 (OUT/('mixed-key-mapping-results.json' if args.start_index==0 else f'mixed-key-mapping-results-from-{args.start_index}.json')).write_text(json.dumps(report,indent=2)+'\n');print('DONE',json.dumps(report),flush=True)
if __name__=='__main__':main()
