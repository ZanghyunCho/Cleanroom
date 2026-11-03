"""Lossless full-image metadata journal and existing core-state integration."""
import ctypes as C
import hashlib
import json
import unittest
from test_runtime import LIB,ROOT,Flash,IO,Context,COVERS,CAPS,CAPACITY,state

LIB.vm_store_bytes.restype=C.c_uint32
LIB.vm_init.argtypes=[C.c_void_p,C.POINTER(IO)]
LIB.vm_format_empty.argtypes=[C.c_void_p]
LIB.vm_core_io.argtypes=[C.c_void_p,C.POINTER(IO)]
LIB.vm_get.argtypes=LIB.vm_put.argtypes=[C.c_void_p,C.c_uint32,C.c_void_p,C.c_uint32]
COUNTS={'metadata_torn_writes':0,'record_bit_corruptions':0,'full_profiles_restored':0}
class MetaFlash(Flash):
    def __init__(self,image=None):super().__init__(image if image is not None else b'\xff'*8192)
    def read(self,_,bank,off,dst,n):
        if bank>1 or off+n>4096:return 0
        C.memmove(dst,bytes(self.image[bank*4096+off:bank*4096+off+n]),n);return 1
    def bulk(self,start,data):
        n=len(data)
        if self.cut_after is not None:n=min(n,max(0,self.cut_after-self.mutations))
        self.image[start:start+n]=data[:n];self.mutations+=n;return n==len(data)
    def erase(self,_,bank):return int(bank<2 and self.bulk(bank*4096,b'\xff'*4096))
    def write(self,_,bank,off,data,n):
        if bank>1 or off+n>4096:return 0
        new=C.string_at(data,n);old=self.image[bank*4096+off:bank*4096+off+n]
        if any(a&b!=b for a,b in zip(old,new)):return 0
        return int(self.bulk(bank*4096+off,new))
class Store:
    def __init__(self,image=None):
        self.flash=MetaFlash(image);self.mem=C.create_string_buffer(LIB.vm_store_bytes())
        self.status=LIB.vm_init(self.mem,C.byref(self.flash.io))
    def format(self):assert self.status==-1;assert LIB.vm_format_empty(self.mem)==0
    def get(self,slot):
        out=C.create_string_buffer(192);r=LIB.vm_get(self.mem,slot,out,192)
        assert r==0,r;return out.raw
    def put(self,slot,data):return LIB.vm_put(self.mem,slot,data,len(data))
    def core(self):
        io=IO();assert LIB.vm_core_io(self.mem,C.byref(io))==0
        ctx=Context();r=LIB.vr_init(C.byref(ctx),C.byref(io),COVERS)
        ctx.keepalive=(self,io)
        return ctx,r

def image(slot):return hashlib.shake_256(f'full-chip-metadata-{slot}'.encode()).digest(192)
class MetadataTests(unittest.TestCase):
    def test_all_metadata_and_core_reboot(self):
        s=Store();s.format();c,r=s.core();self.assertEqual(r,-1)
        self.assertEqual(LIB.vr_format_empty(C.byref(c),CAPS),0)
        for slot in range(13):self.assertEqual(s.put(slot,image(slot)),0)
        for slot in range(12):
            self.assertEqual(LIB.vr_consume(C.byref(c),slot,CAPACITY*91//100),0)
            LIB.vr_cover_open(C.byref(c),COVERS[slot]);LIB.vr_cover_close(C.byref(c),COVERS[slot])
        reboot=Store(s.flash.image);self.assertEqual(reboot.status,0);restored,r=reboot.core()
        self.assertEqual(r,0);self.assertEqual(state(c),state(restored))
        for slot in range(13):self.assertEqual(reboot.get(slot),image(slot));COUNTS['full_profiles_restored']+=1
    def test_every_byte_power_cut(self):
        s=Store();s.format();s.put(0,image(0));before=bytes(s.flash.image)
        old=s.get(0);new=image(1)
        for cut in range(8193):
            current=Store(before);current.flash.cut_after=cut;current.flash.mutations=0
            r=current.put(0,new);self.assertIn(r,(-3,0))
            reboot=Store(current.flash.image);self.assertEqual(reboot.status,0)
            actual=reboot.get(0);self.assertIn(actual,(old,new))
            if not r:self.assertEqual(actual,new)
            COUNTS['metadata_torn_writes']+=1
    def test_every_bit_corruption(self):
        s=Store();s.format();s.put(0,image(0));s.put(0,image(1));snapshot=bytes(s.flash.image)
        # Last commit is in bank zero: format A, image0 B, image1 A.
        for bit in range(4096*8):
            data=bytearray(snapshot);data[bit//8]^=1<<(bit%8)
            recovered=Store(data);self.assertEqual(recovered.status,0)
            self.assertEqual(recovered.get(0),image(0));COUNTS['record_bit_corruptions']+=1
    def test_empty_corrupt_and_bad_inputs(self):
        corrupt=Store(bytes(8192));self.assertEqual(corrupt.status,-2)
        self.assertEqual(LIB.vm_format_empty(corrupt.mem),-5)
        s=Store();s.format();out=C.create_string_buffer(b'\xa5'*192,192)
        self.assertEqual(LIB.vm_get(s.mem,0,out,192),-1);self.assertEqual(out.raw,b'\xa5'*192)
        self.assertEqual(s.put(13,image(0)),-4);self.assertEqual(s.put(0,b''),-4)
        self.assertEqual(s.put(0,b'\0'*193),-4)
    def test_duplicate_write_has_no_storage_mutation(self):
        s=Store();s.format();s.put(0,image(0));before=bytes(s.flash.image)
        s.flash.cut_after=0;s.flash.mutations=0
        self.assertEqual(s.put(0,image(0)),0);self.assertEqual(bytes(s.flash.image),before)

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(MetadataTests))
    report={'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'checks':COUNTS,
            'metadata_bytes_per_profile':192,'profiles':13,'storage_bytes_per_bank':4096,
            'scope':'Compiled lossless journal with injected two-bank storage; native printer allocation not bound',
            'physical_printer_tested':False}
    (ROOT/'analysis/full-metadata-host-results.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(not result.wasSuccessful())
