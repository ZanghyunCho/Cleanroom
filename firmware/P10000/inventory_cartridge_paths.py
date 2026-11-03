"""Index firmware cartridge/IES diagnostics and direct ARM PC-relative references."""
from pathlib import Path
import struct,re,json
ROOT=Path(__file__).resolve().parent

def ror(v,n):return ((v>>n)|(v<<(32-n)))&0xffffffff if n else v

def inventory(data,base):
 strings=[]
 for m in re.finditer(rb'\[[A-Za-z][A-Za-z0-9_ ]{2,30}\][^\x00]{1,500}\x00',data):
  text=m.group()[:-1].decode('cp932',errors='replace')
  if re.search(r'CSIC|\bIES\b|Ink.?End|ink.?end|カートリッジ|純正|仕向|インクエンド|T80[0-9]|国内外',text):
   strings.append({'offset':hex(m.start()),'address':hex(base+m.start()),'text':text,'references':[]})
 by_address={int(s['address'],16):s for s in strings}
 for off in range(0,len(data)-4,4):
  w=struct.unpack_from('<I',data,off)[0];target=None
  if w&0x0e1f0000==0x020f0000 and (w>>21)&15 in [2,4]:
   n=ror(w&255,2*((w>>8)&15));target=base+off+8+(n if (w>>21)&15==4 else -n)
  elif w&0x0f7f0000==0x051f0000:
   lit=off+8+((w&4095) if w&(1<<23) else -(w&4095))
   if 0<=lit<=len(data)-4:target=struct.unpack_from('<I',data,lit)[0]
  if target in by_address:by_address[target]['references'].append(hex(base+off))
 return strings

def main():
 report={}
 for name,base in [('main-block-2.bin',0x44200000),('main-block-3.bin',0x43b00000)]:
  data=(ROOT/'inputs'/name).read_bytes();rows=inventory(data,base)
  report[name]={'assumed_link_base':hex(base),'diagnostics':rows}
 (ROOT/'build/cartridge-path-inventory.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 for row in report['main-block-3.bin']['diagnostics']:
  if re.search(r'純正|仕向|国内外|Tコード|装着|インクエンド|CSIC_sub_SaveConsentNonGenuine|CSチェック',row['text']):print(json.dumps(row,ensure_ascii=False))
if __name__=='__main__':main()
