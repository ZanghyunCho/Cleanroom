"""Fault injection for compact records and the synchronous native NV bridge."""
import ctypes as C
import json
import struct
import unittest
from test_runtime import LIB,ROOT,IO,Context,COVERS,CAPS,CAPACITY,info,state,fix_crc,fresh

class Request(C.Structure):
    _fields_=[('id',C.c_uint32),('bytes',C.c_uint32),('first',C.c_uint16),('last',C.c_uint16),
              ('reserved',C.c_uint8*2),('mode',C.c_uint8),('pad',C.c_uint8),('tail',C.c_uint32*2)]
NV_CALL=C.CFUNCTYPE(C.c_uint32,C.POINTER(Request),C.c_void_p)
class Api(C.Structure):_fields_=[('read',NV_CALL),('write',NV_CALL)]
class Backend(C.Structure):
    _fields_=[('api',Api),('capacities',C.c_uint64*12),('stage',(C.c_uint8*512)*2),
              ('dirty',C.c_uint32*2),('loaded',C.c_uint32*2),('fault',C.c_uint32)]
LIB.vr_nv_register_owner.argtypes=[C.c_void_p,C.c_uint32]
LIB.vr_nv_backend_init.argtypes=[C.POINTER(Backend),C.POINTER(Api),C.c_void_p,C.c_uint32,C.POINTER(C.c_uint64),C.POINTER(IO)]
LIB.vr_record_compact.argtypes=LIB.vr_record_expand.argtypes=[C.c_void_p,C.POINTER(C.c_uint64),C.c_void_p]
LIB.vr_nv_install_empty_records.argtypes=[C.POINTER(Backend)]
ORIGINAL=(ROOT/'decoded/crom-00070000-0.bin').read_bytes()[0x43740e74-0x433e0000:0x43740e74-0x433e0000+157*20]
COUNTS={'torn_logical_writes':0,'compact_bit_corruptions':0,'codec_boundary_records':0}

def table():
    t=C.create_string_buffer(ORIGINAL);assert LIB.vr_nv_register_owner(t,157)==0;return t
class Store:
    def __init__(self,records=None):
        self.records=[bytearray(x) for x in records] if records else [bytearray(b'\xff'*128) for _ in range(2)]
        self.cut=None;self.written=0;self.error=0;self.mismatch=False;self.writes=0;self.reads=0;self.errors=[]
        self.callbacks=(NV_CALL(self.read),NV_CALL(self.write));self.api=Api(*self.callbacks)
    def bank(self,r):
        r=r.contents
        if r.id not in (0x01607500,0x01607501) or r.bytes!=128 or r.first or r.last or r.mode:
            self.errors.append('Native request ABI mismatch');return None
        return r.id-0x01607500
    def read(self,r,p):
        bank=self.bank(r);self.reads+=1
        if self.error or bank is None:return self.error or 1
        data=bytes(self.records[bank]);data=(bytes([data[0]^1])+data[1:]) if self.mismatch and self.writes else data
        C.memmove(p,data,128);return 0
    def write(self,r,p):
        bank=self.bank(r);self.writes+=1
        if self.error or bank is None:return self.error or 1
        for i,v in enumerate(C.string_at(p,128)):
            if self.cut is not None and self.written>=self.cut:return 7
            self.records[bank][i]=v;self.written+=1
        return 0

def load(store,capacities=CAPS):
    b=Backend();io=IO();t=table()
    assert LIB.vr_nv_backend_init(C.byref(b),C.byref(store.api),t,157,capacities,C.byref(io))==0
    c=Context();status=LIB.vr_init(C.byref(c),C.byref(io),COVERS)
    # Keep all callbacks, backend memory, and IO alive during C calls.
    c.keepalive=(store,b,io,t)
    return c,status

def provisioned():
    s=Store();c,r=load(s);assert r==-1
    assert LIB.vr_format_empty(C.byref(c),CAPS)==0
    s.written=0;return s,c
class NativeNvTests(unittest.TestCase):
    def test_codec_boundaries(self):
        f,c=fresh();base=bytes(f.image[c.active*512:(c.active+1)*512])
        for used in (0,1,0xffffffff,0x100000000,0xffffffffff):
            for generation in (0,1,0xffffffff):
                for marker in (0xffffffff,0x54494d43):
                    record=bytearray(base)
                    for slot in range(12):struct.pack_into('<QI',record,32+slot*20,used,generation)
                    struct.pack_into('<I',record,28,marker);fix_crc(record)
                    packed=C.create_string_buffer(128);expanded=C.create_string_buffer(512)
                    self.assertEqual(LIB.vr_record_compact(bytes(record),CAPS,packed),0)
                    self.assertEqual(LIB.vr_record_expand(packed,CAPS,expanded),0)
                    self.assertEqual(expanded.raw,record);COUNTS['codec_boundary_records']+=1
    def test_native_registration_preserves_other_rows(self):
        t=table();expected=bytearray(ORIGINAL)
        for row,id in ((121,0x01607500),(122,0x01607501)):struct.pack_into('<2I',expected,row*20,id,0x10080)
        self.assertEqual(t.raw[:157*20],expected);self.assertEqual(LIB.vr_nv_register_owner(t,157),0)
        for offset in (120*20,121*20+4,122*20+8):
            damaged=bytearray(ORIGINAL);damaged[offset]^=1;t=C.create_string_buffer(bytes(damaged))
            self.assertEqual(LIB.vr_nv_register_owner(t,157),-5);self.assertEqual(t.raw[:157*20],damaged)
    def test_reboot_and_generation(self):
        s,c=provisioned()
        for slot in range(12):
            self.assertEqual(LIB.vr_consume(C.byref(c),slot,CAPACITY*91//100),0)
            self.assertEqual(LIB.vr_cover_open(C.byref(c),COVERS[slot]),1)
            self.assertGreater(LIB.vr_cover_close(C.byref(c),COVERS[slot]),0)
        reboot,status=load(Store(s.records));self.assertEqual(status,0);self.assertEqual(state(c),state(reboot))
        for slot in range(12):self.assertEqual(info(c,slot).serial,info(reboot,slot).serial)
        self.assertFalse(s.errors)
    def test_torn_logical_writes(self):
        s,c=provisioned();LIB.vr_consume(C.byref(c),0,CAPACITY*95//100)
        old=state(c);records=[bytes(x) for x in s.records]
        for cut in range(257):
            t=Store(records);current,status=load(t);self.assertEqual(status,0)
            LIB.vr_cover_open(C.byref(current),1);t.cut=cut;t.written=0
            result=LIB.vr_cover_close(C.byref(current),1);self.assertIn(result,(-3,1))
            reboot,status=load(Store(t.records));self.assertEqual(status,0)
            if state(reboot)!=old:
                self.assertEqual((reboot.slots[0].used,reboot.slots[0].generation),(0,1))
            if result==1:self.assertEqual(state(reboot),state(current))
            COUNTS['torn_logical_writes']+=1
    def test_compact_corruption(self):
        s,c=provisioned();LIB.vr_consume(C.byref(c),0,123);before=state(c)
        LIB.vr_consume(C.byref(c),0,456);active=c.active
        for bit in range(128*8):
            records=[bytearray(x) for x in s.records];records[active][bit//8]^=1<<(bit%8)
            reboot,status=load(Store(records))
            # Magic corruption is intentionally an unknown-format I/O error;
            # CRC/data/marker corruption can fall back to the preceding bank.
            if bit<32:self.assertEqual(status,-3)
            else:self.assertEqual(status,0);self.assertEqual(state(reboot),before)
            COUNTS['compact_bit_corruptions']+=1
    def test_bad_backend_never_formats(self):
        s=Store();s.error=1;c,status=load(s);self.assertEqual(status,-3)
        self.assertEqual(LIB.vr_format_empty(C.byref(c),CAPS),-5);self.assertEqual(s.writes,0)
        s,c=provisioned();s.error=0x1003
        self.assertEqual(LIB.vr_consume(C.byref(c),0,123),-3)
        self.assertEqual(c.keepalive[1].fault,1)
        s,c=provisioned();s.mismatch=True
        self.assertEqual(LIB.vr_consume(C.byref(c),0,123),-3);self.assertEqual(c.keepalive[1].fault,1)
    def test_capacity_binding(self):
        s,c=provisioned();wrong=(C.c_uint64*12)(*([CAPACITY+1]*12))
        reboot,status=load(Store(s.records),wrong);self.assertEqual(status,-2)
    def test_unknown_record_extension_not_discarded(self):
        f,c=fresh();record=bytearray(f.image[c.active*512:(c.active+1)*512])
        record[-1]=0;fix_crc(record);out=C.create_string_buffer(b'\xa5'*128,128)
        self.assertEqual(LIB.vr_record_compact(bytes(record),CAPS,out),-2)
        self.assertEqual(out.raw,b'\xa5'*128)
    def test_owner_id_collision_not_registered(self):
        original=bytearray(ORIGINAL);struct.pack_into('<I',original,0,0x01607500)
        t=C.create_string_buffer(bytes(original))
        self.assertEqual(LIB.vr_nv_register_owner(t,157),-5)
        self.assertEqual(t.raw[:157*20],original)
    def test_installer_initialization_is_explicit(self):
        s,c=provisioned();LIB.vr_consume(C.byref(c),0,123)
        records=[bytes(x) for x in s.records]
        again,status=load(s);self.assertEqual(status,0);self.assertEqual(s.records,[bytearray(x) for x in records])
        b=again.keepalive[1]
        self.assertEqual(LIB.vr_nv_install_empty_records(C.byref(b)),0)
        self.assertEqual(s.records,[bytearray(b'\xff'*128)]*2)
        reset,status=load(s);self.assertEqual(status,-1)
        self.assertEqual(LIB.vr_format_empty(C.byref(reset),CAPS),0)
        self.assertEqual(info(reset,0).used,0)

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(NativeNvTests))
    report={'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'checks':COUNTS,
            'scope':'Compiled bridge with injected logical NV records; physical flash service not emulated',
            'native_flash_power_loss_contract_verified':False}
    (ROOT/'analysis/native-nv-host-results.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(not result.wasSuccessful())
