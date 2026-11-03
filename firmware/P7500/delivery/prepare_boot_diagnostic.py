"""Build one-variable boot diagnostics from the exact original chip files; no device access."""
from pathlib import Path
import argparse,hashlib,json
SIZE=67108864
ORIGINAL='ae9b0cd5f15f1f2edcfd671c9131d9383243e1fbf9c59b0bf31dcaa04968c551'
def sha(b):return hashlib.sha256(b).hexdigest()
def merge(a,b):
 if len(a)!=SIZE or len(b)!=SIZE:raise ValueError('Both inputs must be exactly 64 MiB')
 out=bytearray(2*SIZE);out[0::4]=a[0::2];out[1::4]=a[1::2];out[2::4]=b[0::2];out[3::4]=b[1::2];return out
def split(data):
 out=[]
 for start in [0,2]:
  b=bytearray(SIZE);b[0::2]=data[start::4];b[1::2]=data[start+1::4];out.append(b)
 return out
def apply(original,variant,manifest,root):
 if sha(original)!=ORIGINAL:raise ValueError('Original merged SHA-256 mismatch: wrong firmware, lane order, or input')
 info=manifest['variants'][variant];out=bytearray(original)
 if variant=='key-only':
  public=(root/'owner-public.bin').read_bytes()
  if len(public)!=64 or sha(public)!=info['public_sha256']:raise ValueError('Public-key artifact mismatch')
  for offset in info['offsets']:out[offset:offset+64]=public
 else:
  patch=(root/'crom-nop.patch').read_bytes();start,end=info['rom_range']
  if len(patch)!=end-start or sha(patch)!=info['patch_sha256']:raise ValueError('Diagnostic code patch mismatch')
  out[start:end]=patch
 if sha(out)!=info['merged_sha256']:raise ValueError('Diagnostic result hash mismatch')
 return out

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('variant',choices=['key-only','crom-nop']);p.add_argument('original_ic13');p.add_argument('original_ic14');p.add_argument('output');a=p.parse_args()
 root=Path(__file__).resolve().parent;m=json.loads((root/'diagnostic-manifest.json').read_text());dst=Path(a.output)
 if dst.exists() and (not dst.is_dir() or any(dst.iterdir())):raise ValueError('Output must be a new or empty directory')
 original=merge(Path(a.original_ic13).read_bytes(),Path(a.original_ic14).read_bytes());out=apply(original,a.variant,m,root);chips=split(out)
 assert merge(*chips)==out
 for role,data in zip(['IC13','IC14'],chips):
  if sha(data)!=m['variants'][a.variant]['chips'][role]['sha256']:raise ValueError('Output lane hash mismatch')
 dst.mkdir(parents=True,exist_ok=True)
 for role,data in zip(['IC13','IC14'],chips):(dst/(role+'.BIN')).write_bytes(data)
 (dst/'sha256.json').write_text(json.dumps({'variant':a.variant,'classification':'DIAGNOSTIC ONLY; PHYSICAL BOOT NOT VERIFIED','files':m['variants'][a.variant]['chips']},indent=2)+'\n')
 print(json.dumps({'output':str(dst),'variant':a.variant,'files':m['variants'][a.variant]['chips'],'physical_boot_verified':False},indent=2))
if __name__=='__main__':main()
