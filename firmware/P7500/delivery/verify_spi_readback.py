"""Read-only SHA-256 check of physical IC13/IC14 readback files. Never writes a chip."""
import argparse,hashlib,json
from pathlib import Path
SIZE=67108864
PROFILES={
 'original':('894056f5b002e75c26d636b269910a8f48eb1a95762e849f8fda7339e08914ed','4403822b3eb8e7a2fafb71bbc1f989377908334f81a0e02c70532a1c4ccf8b7e'),
 'delivered_installer_boot_failure_reported':('eec76055f646d7120f6c090cf10cda4fc5889d133c3a28b9919a300d0c087a33','5799602db15db92ff16f7ef89512610fddc626e26d767b1a4618dec87489629e')}
CODE_PREFIX_LENGTH=1932489
CODE_PREFIX_HASHES={'original': '1179fa3461dbdbf7949623e8e7aaff65a827896ed3bfde9fc5eae1c695d21bfe', 'delivered_installer': '0c23874a8cbb9a17ac47bd619e67fea77159405de9b53320a38499c287e580d9', 'delivered_runtime': 'e6c443fbf9b48c71a1b8463d605df423b117f6f1d5c3f082b55fcc369cf90fe3'}
def read_merged_prefix(paths,length):
 lane_bytes=((length+3)//4)*2
 lanes=[]
 for path in paths:
  with Path(path).open('rb') as f:lanes.append(f.read(lane_bytes))
 if any(len(b)!=lane_bytes for b in lanes):return None
 out=bytearray(lane_bytes*2);a,b=lanes
 out[0::4]=a[0::2];out[1::4]=a[1::2];out[2::4]=b[0::2];out[3::4]=b[1::2]
 return bytes(out[:length])

def inspect(paths):
 files=[]
 for role,path in zip(('IC13','IC14'),paths):
  p=Path(path);h=hashlib.sha256()
  with p.open('rb') as f:
   while True:
    b=f.read(1024*1024)
    if not b:break
    h.update(b)
  files.append({'physical_chip':role,'file':str(p),'bytes':p.stat().st_size,'sha256':h.hexdigest()})
 hashes=tuple(x['sha256'] for x in files);match=None;swapped=None
 for name,expected in PROFILES.items():
  if hashes==expected:match=name
  if hashes==expected[::-1]:swapped=name
 prefix=read_merged_prefix(paths,CODE_PREFIX_LENGTH)
 prefix_hash=hashlib.sha256(prefix).hexdigest() if prefix is not None else None
 prefix_match=next((name for name,h in CODE_PREFIX_HASHES.items() if h==prefix_hash),None)
 return {'boot_and_modified_code_prefix':{'merged_start':0,'merged_end_exclusive':CODE_PREFIX_LENGTH,'sha256':prefix_hash,'matches_known_prefix':prefix_match,'scope':'Only this prefix; does not verify every code or NV byte'},'files':files,'each_file_is_64MiB':all(x['bytes']==SIZE for x in files),'exact_known_image_pair':match,'reversed_known_image_pair':swapped,'unknown_is_not_automatically_a_write_failure':True,'note':'Runtime-promoted images and fresh operating-state dumps can legitimately differ; no chip write performed.'}
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('ic13_readback');p.add_argument('ic14_readback');a=p.parse_args();print(json.dumps(inspect([a.ic13_readback,a.ic14_readback]),indent=2))
if __name__=='__main__':main()
