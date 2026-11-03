"""Build P7500 SPI images with only the two owner public-key copies changed."""
from pathlib import Path
import hashlib,json,shutil,sys,zipfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'delivery'))
from prepare_boot_diagnostic import merge,split,ORIGINAL
from verify_spi_readback import PROFILES
OFFSETS=(0x7010,0x6d000)
def sha(b):return hashlib.sha256(b).hexdigest()
def p256(key):
 if len(key)!=64:return False
 prime=int('ffffffff00000001000000000000000000000000ffffffffffffffffffffffff',16)
 b=int('5ac635d8aa3a93e7b3ebbd55769886bc651d06b0cc53b0f63bce3c3e27d2604b',16)
 x=int.from_bytes(key[:32],'big');y=int.from_bytes(key[32:],'big')
 return x<prime and y<prime and (y*y-x*x*x+3*x-b)%prime==0

def main():
 original=(ROOT/'original/merged.bin').read_bytes();assert sha(original)==ORIGINAL
 assert merge((ROOT/'original/IC3.BIN').read_bytes(),(ROOT/'original/IC4.BIN').read_bytes())==original
 old=original[OFFSETS[0]:OFFSETS[0]+64];assert p256(old)
 assert old==original[OFFSETS[1]:OFFSETS[1]+64]
 public=Path('/workspace/p7500-rebuild/analysis/owner-public.bin').read_bytes();assert p256(public) and public!=old
 assert sha(public)=='0cb5418f7bdfe9e27b6878cfd4bd92a927f61a7083cd9a3b818291ffb81c3c68'
 changed=bytearray(original)
 for off in OFFSETS:changed[off:off+64]=public
 # Verify every byte outside the two spans, not merely the decompressed code.
 last=0
 for off in OFFSETS:
  assert changed[last:off]==original[last:off];last=off+64
 assert changed[last:]==original[last:]
 assert changed[0x70000:]==original[0x70000:]
 assert sha(changed)=='6e121d870ad5ee7f9216b9232ca49485938617f65de19101b7929a36ec4f45d7'
 out=ROOT/'build/key-only';out.mkdir(parents=True,exist_ok=True)
 chips=split(changed);assert merge(*chips)==changed
 manifest={'classification':'KEY REPLACEMENT CANDIDATE; PHYSICAL BOOT AND CUSTOM EFU ACCEPTANCE NOT VERIFIED',
  'original_merged_sha256':ORIGINAL,'key_only_merged_sha256':sha(changed),'public_key_encoding':'NIST P-256, uncompressed X||Y, big-endian coordinates, 64 bytes',
  'original_public_key_sha256':sha(old),'owner_public_key_sha256':sha(public),'both_public_points_valid_p256':True,
  'changed_merged_ranges':[{'start':hex(off),'end_exclusive':hex(off+64),'bytes':64,'differing_bytes':sum(a!=b for a,b in zip(original[off:off+64],public))} for off in OFFSETS],
  'all_bytes_outside_key_ranges_equal_original':True,'all_bytes_from_0x70000_to_end_equal_original':True,
  'crom_recompressed':False,'virtualization_or_nv_expansion_included':False,'private_key_included':False,
  'physical_boot_verified':False,'custom_efu_acceptance_verified':False,'files':{}}
 for role,chip in zip(['IC13','IC14'],chips):
  name='P7500_KEY_ONLY_'+role+'.BIN';assert sha(chip)==PROFILES['key_only_original_firmware'][0 if role=='IC13' else 1]
  (out/name).write_bytes(chip);manifest['files'][name]={'physical_chip':role,'bytes':len(chip),'sha256':sha(chip)}
 (out/'owner-public.bin').write_bytes(public)
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 shutil.copyfile(ROOT/'delivery/KEY-ONLY.ko.md',out/'README.ko.md');shutil.copyfile(ROOT/'delivery/verify_spi_readback.py',out/'verify_spi_readback.py')
 checksums=[]
 for name in [*manifest['files'],'owner-public.bin','manifest.json','README.ko.md','verify_spi_readback.py']:
  checksums.append(sha((out/name).read_bytes())+'  '+name)
 (out/'SHA256SUMS.txt').write_text('\n'.join(checksums)+'\n')
 archive=ROOT/'build/P7500-KEY-ONLY-SPI.zip'
 names=[*manifest['files'],'owner-public.bin','manifest.json','README.ko.md','verify_spi_readback.py','SHA256SUMS.txt']
 with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for name in names:z.write(out/name,name)
 with zipfile.ZipFile(archive) as z:
  assert z.testzip() is None and set(z.namelist())==set(names)
  for name,info in manifest['files'].items():
   data=z.read(name);assert len(data)==info['bytes'] and sha(data)==info['sha256']
 report={'artifact':str(archive),'bytes':archive.stat().st_size,'sha256':sha(archive.read_bytes()),'manifest':manifest}
 (ROOT/'validation/key-only-package-results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
