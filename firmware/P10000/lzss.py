"""Strict size-prefixed Epson LZSS decode/replay; preserves valid original references."""
import struct
def decode(stream,with_tokens=False):
 expected=struct.unpack_from('<I',stream)[0];ring=bytearray(4096);r=0xfee;s=4;out=bytearray();tokens=[]
 while len(out)<expected:
  flags=stream[s];s+=1
  for bit in range(8):
   if len(out)>=expected:break
   before=len(out)
   if flags&(1<<bit):
    value=stream[s];s+=1;out.append(value);ring[r]=value;r=(r+1)&4095;token=(True,bytes([value]),1,None)
   else:
    raw=stream[s:s+2];a,c=raw;s+=2;off=a|((c&0xf0)<<4);n=(c&15)+3;distance=(r-off)&4095 or 4096
    for j in range(n):
     value=ring[(off+j)&4095];out.append(value);ring[r]=value;r=(r+1)&4095
    token=(False,raw,n,before-distance)
   if with_tokens:tokens.append(token)
 assert len(out)==expected and s==len(stream),'Truncated/extra LZSS data'
 return bytes(out),tokens

def encode_preserving(stream,desired):
 original,tokens=decode(stream,True);assert len(original)==len(desired)
 encoded=[];offset=0;replaced=[]
 for literal,raw,n,reference in tokens:
  target=desired[offset:offset+n]
  if literal:encoded.append((True,target))
  else:
   # Replay the original absolute-ring reference against the desired output.
   predicted=bytes(desired[q] if q>=0 else 0 for q in range(reference,reference+n))
   if predicted==target:encoded.append((False,raw))
   else:
    encoded.extend((True,bytes([value])) for value in target)
    replaced.append({'decoded_offset':hex(offset),'length':n,'reference':hex(reference)})
  offset+=n
 result=bytearray(struct.pack('<I',len(desired)))
 for pos in range(0,len(encoded),8):
  group=encoded[pos:pos+8];result.append(sum((1<<bit) for bit,(literal,_) in enumerate(group) if literal))
  for _,raw in group:result.extend(raw)
 assert decode(result)[0]==desired
 return bytes(result),replaced
