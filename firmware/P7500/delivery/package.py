"""Build an explicitly experimental SPI handoff from the user's verified dump."""
from pathlib import Path
import hashlib,json,struct,sys,zipfile,shutil
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'delivery'))
from assemble import assemble
from prepare import merge,split,apply,digest
from crom import patch_frame,decode_frame
EXPECTED='ae9b0cd5f15f1f2edcfd671c9131d9383243e1fbf9c59b0bf31dcaa04968c551'

def main():
 original=(ROOT/'original/merged.bin').read_bytes()
 if digest(original)!=EXPECTED:raise ValueError('Original merged dump integrity failure')
 public=(Path('/workspace/p7500-rebuild/analysis/owner-public.bin')).read_bytes()
 if len(public)!=64 or original[0x7010:0x7050]!=original[0x6d000:0x6d040]:raise ValueError('Public key profile mismatch')
 begin=0x70000;first=begin+4;first_end=first+int.from_bytes(original[first+2:first+6],'big')
 second_end=first_end+int.from_bytes(original[first_end+2:first_end+6],'big');second=original[first_end:second_end]
 patches={};reports={};end=second_end
 for mode in ('installer','runtime'):
  desired,symbols,report=assemble(mode)
  frame,codec=patch_frame(original,first,desired)
  decoded,parsed,_,_=decode_frame(frame,0)
  if decoded!=desired or parsed!=len(frame):raise ValueError('CROM round-trip failed')
  patches[mode]=b'CROM'+frame+second;end=max(end,begin+len(patches[mode]))
  reports[mode]={'assembly':report,'codec':codec,'second_original_frame_preserved':True}
  print(mode,'CROM verified',len(frame),flush=True)
 if any(x!=255 for x in original[second_end:end]):raise ValueError('Compressed output exceeds verified FF padding')
 for mode in patches:patches[mode]+=b'\xff'*(end-begin-len(patches[mode]))
 manifest={'classification':'EXPERIMENTAL; NOT PHYSICALLY BOOT/POWER-CUT VERIFIED',
  'original_merged_sha256':EXPECTED,'rom_region':{'start':begin,'end':end,
    'original_sha256':digest(original[begin:end]),'installer_sha256':digest(patches['installer']),'runtime_sha256':digest(patches['runtime'])},
  'original_public_key':original[0x7010:0x7050].hex(),'owner_public_key':public.hex(),'public_key_offsets':[0x7010,0x6d000],
  'physical_printer_tested':False,'physical_power_cut_tested':False,
  'runtime_requires_installer_state':True,'preserve_fresh_readback_before_runtime_upgrade':True,
  'reports':reports}
 out=ROOT/'build/delivery/handoff';out.mkdir(parents=True,exist_ok=True)
 for mode in patches:(out/f'{mode}-rom.patch').write_bytes(patches[mode])
 installer=apply(original,'install',manifest,patches['installer'])
 chips=split(installer)
 if merge(*chips)!=installer:raise ValueError('Physical lane reconstruction failed')
 manifest['installer_files']={}
 for name,data in zip(('EXPERIMENTAL_INSTALLER_IC13.BIN','EXPERIMENTAL_INSTALLER_IC14.BIN'),chips):
  (out/name).write_bytes(data);manifest['installer_files'][name]={'bytes':len(data),'sha256':digest(data)}
 # Test stage-two promotion with arbitrary changed native data. It must survive.
 post=bytearray(installer);post[-4096:]=bytes((i*19)&255 for i in range(4096))
 runtime=apply(post,'runtime',manifest,patches['runtime'])
 if runtime[:begin]!=post[:begin] or runtime[end:]!=post[end:]:raise ValueError('Runtime promotion overwrote native state')
 if merge(*split(runtime))!=runtime:raise ValueError('Runtime lane round-trip failure')
 manifest['stage_two_state_preservation_test_passed']=True
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 shutil.copyfile(ROOT/'delivery/prepare.py',out/'prepare.py');shutil.copyfile(ROOT/'delivery/README.ko.md',out/'README.ko.md')
 for name in ('delivery-bootstrap-results.json','full-native-nv-results.json','full-metadata-host-results.json'):
  shutil.copyfile(ROOT/'analysis'/name,out/name)
 archive=ROOT/'build/P7500-EXPERIMENTAL-SPI.zip'
 with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  names=['EXPERIMENTAL_INSTALLER_IC13.BIN','EXPERIMENTAL_INSTALLER_IC14.BIN',
         'installer-rom.patch','runtime-rom.patch','manifest.json','prepare.py','README.ko.md',
         'delivery-bootstrap-results.json','full-native-nv-results.json','full-metadata-host-results.json']
  for name in names:z.write(out/name,name)
 report={'artifact':str(archive),'bytes':archive.stat().st_size,'sha256':digest(archive.read_bytes()),
  'installer_chip_files':manifest['installer_files'],'physical_printer_tested':False,
  'stage_two_state_preservation_test_passed':True}
 (ROOT/'analysis/spi-package-results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
