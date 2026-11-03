"""Prepare SPI images from fresh readbacks, preserving all non-program bytes.

Standard library only. Run locally beside manifest.json and *-rom.patch files.
"""
from pathlib import Path
import argparse,hashlib,json
SIZE=64*1024*1024

def digest(data):return hashlib.sha256(data).hexdigest()
def merge(a,b):
 if len(a)!=SIZE or len(b)!=SIZE:raise ValueError('Each physical chip must be exactly 64 MiB')
 out=bytearray(SIZE*2)
 for data,start in ((a,0),(b,2)):
  out[start::4]=data[0::2];out[start+1::4]=data[1::2]
 return out

def split(data):
 if len(data)!=SIZE*2:raise ValueError('Merged image must be exactly 128 MiB')
 chips=[]
 for start in (0,2):
  chip=bytearray(SIZE);chip[0::2]=data[start::4];chip[1::2]=data[start+1::4];chips.append(chip)
 return chips

def apply(data,stage,manifest,patch):
 region=manifest['rom_region'];start,end=region['start'],region['end']
 expected=region['original_sha256' if stage=='install' else 'installer_sha256']
 if digest(data[start:end])!=expected:raise ValueError('ROM fingerprint mismatch: wrong chip order, firmware or installation stage')
 old=bytes.fromhex(manifest['original_public_key' if stage=='install' else 'owner_public_key'])
 new=bytes.fromhex(manifest['owner_public_key'])
 if len(old)!=64 or len(new)!=64:raise ValueError('Invalid public-key length')
 for off in manifest['public_key_offsets']:
  if data[off:off+64]!=old:raise ValueError('Public-key fingerprint mismatch')
 if len(patch)!=end-start or digest(patch)!=region['installer_sha256' if stage=='install' else 'runtime_sha256']:
  raise ValueError('ROM patch integrity failure')
 result=bytearray(data);result[start:end]=patch
 if stage=='install':
  for off in manifest['public_key_offsets']:result[off:off+64]=new
 # No other byte is replaced: this includes native NV data created by installer.
 return result

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('stage',choices=['install','runtime'])
 p.add_argument('ic13');p.add_argument('ic14');p.add_argument('output');args=p.parse_args()
 root=Path(__file__).resolve().parent;manifest=json.loads((root/'manifest.json').read_text())
 patch=(root/('installer-rom.patch' if args.stage=='install' else 'runtime-rom.patch')).read_bytes()
 source=merge(Path(args.ic13).read_bytes(),Path(args.ic14).read_bytes())
 result=apply(source,args.stage,manifest,patch);output=Path(args.output)
 if output.exists() and any(output.iterdir()):raise ValueError('Output directory must be empty')
 output.mkdir(parents=True,exist_ok=True);hashes={}
 for name,data in zip(('IC13.BIN','IC14.BIN'),split(result)):
  (output/name).write_bytes(data);hashes[name]=digest(data)
 if merge(*[(output/name).read_bytes() for name in ('IC13.BIN','IC14.BIN')])!=result:raise ValueError('Lane round-trip failure')
 report={'stage':args.stage,'input_merged_sha256':digest(source),'output_merged_sha256':digest(result),'files':hashes,
         'physical_chip_tested':False,'non_program_bytes_preserved':True}
 (output/'sha256.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
