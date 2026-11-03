"""Identify original updater HMAC primitive with public vectors, no device secrets."""
from pathlib import Path
import hashlib,hmac,json
from native import Updater
ROOT=Path(__file__).resolve().parent

def main():
 m=Updater((ROOT/'inputs/efu-extracted/EFU_File.rcx').read_bytes());rows=[]
 vectors=[(b'\x0b'*20,b'Hi There','b617318655057264e28bc0b6fb378c8ef146be00'),(b'Jefe'+bytes(16),b'what do ya want for nothing?','effcdf6ae5eb2fa2d27416d5f184df9c259a7c79'),(bytes(range(20)),bytes(range(256))*3,None)]
 for i,(key,message,known) in enumerate(vectors):
  m.u.mem_write(0x43001000,message);m.u.mem_write(0x43090000,key)
  m.call(0x3800208c,0x43000000,0x43001000,len(message),0x43090000)
  actual=bytes(m.u.mem_read(0x43000000,20));expected=hmac.new(key,message,hashlib.sha1).digest()
  assert actual==expected and (known is None or actual.hex()==known)
  rows.append({'public_test_vector':i,'native':actual.hex(),'standard_sha1':expected.hex(),'matches_standard':True,'matches_word_swapped_standard':actual==b''.join(expected[j:j+4][::-1] for j in range(0,20,4))})
 (ROOT/'build/hmac-vector-results.json').write_text(json.dumps(rows,indent=2)+'\n');print('Three public HMAC-SHA1 vectors passed original ARM code')
if __name__=='__main__':main()
