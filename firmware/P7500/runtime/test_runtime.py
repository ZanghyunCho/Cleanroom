"""Fault injection against the compiled C runtime and durable file backend."""
import ctypes as C
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

ROOT=Path(__file__).resolve().parents[1]
LIB=C.CDLL(str(ROOT/'build/libvirtual_cartridge.so'))
READ=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_uint32,C.c_uint32,C.c_void_p,C.c_uint32)
ERASE=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_uint32)
WRITE=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_uint32,C.c_uint32,C.c_void_p,C.c_uint32)
SYNC=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_uint32)
class IO(C.Structure):
    _fields_=[('user',C.c_void_p),('read',READ),('erase',ERASE),('write',WRITE),('sync',SYNC)]
class Slot(C.Structure):
    _fields_=[('used',C.c_uint64),('capacity',C.c_uint64),('generation',C.c_uint32)]
class Context(C.Structure):
    _fields_=[('io',IO),('slots',Slot*12),('sequence',C.c_uint64),
              ('active',C.c_uint32),('ready',C.c_uint32),('empty',C.c_uint32),
              ('fault',C.c_uint32),('busy',C.c_uint32),('opened',C.c_uint32),('covers',C.c_uint8*12)]
class Info(C.Structure):
    _fields_=[('used',C.c_uint64),('capacity',C.c_uint64),('generation',C.c_uint32),
              ('present',C.c_uint32),('virtualized',C.c_uint32),('remaining_percent',C.c_uint32),
              ('nominal_ml',C.c_uint32),('serial',C.c_char*11),('manufacturer',C.c_char*6),('model',C.c_char*16)]
P=C.POINTER(Context)
LIB.vr_init.argtypes=[P,C.POINTER(IO),C.POINTER(C.c_uint8)]
LIB.vr_format_empty.argtypes=[P,C.POINTER(C.c_uint64)]
LIB.vr_consume.argtypes=[P,C.c_uint32,C.c_uint64]
LIB.vr_reconcile_usage.argtypes=[P,C.c_uint32,C.c_uint64]
LIB.vr_cover_open.argtypes=LIB.vr_cover_close.argtypes=[P,C.c_uint32]
LIB.vr_get_usage.argtypes=[P,C.c_uint32];LIB.vr_get_usage.restype=C.c_uint64
LIB.vr_get_generation.argtypes=LIB.vr_get_percent.argtypes=[P,C.c_uint32]
LIB.vr_get_generation.restype=LIB.vr_get_percent.restype=C.c_uint32
LIB.vr_get_info.argtypes=[P,C.c_uint32,C.POINTER(Info)]
LIB.vr_publish_ink_identity.argtypes=[P,C.c_uint32,C.c_void_p,C.c_uint32]
LIB.vr_exchange.argtypes=[P,C.c_uint32,C.c_uint32,C.c_void_p,C.c_uint32,C.c_void_p,C.c_uint32]
COVERS=(C.c_uint8*12)(*([1]*6+[0]*6))
CAPACITY=7_000_000
CAPS=(C.c_uint64*12)(*([CAPACITY]*12))
COUNTS={'power_cuts':0,'bit_corruptions':0,'boundary_scenarios':0,'protocol_requests':0}

class Flash:
    def __init__(self,image=None,files=None):
        self.image=bytearray(image if image is not None else b'\xff'*1024)
        self.cut_after=None;self.mutations=0;self.syncs=0;self.fail_sync=None
        self.reads=0;self.fail_read=None;self.reenter=None;self.errors=[];self.files=files
        self.callbacks=(READ(self.read),ERASE(self.erase),WRITE(self.write),SYNC(self.sync))
        self.io=IO(None,*self.callbacks)
    def read(self,_,bank,offset,dst,count):
        self.reads+=1
        if self.reads==self.fail_read:return 0
        if bank>1 or offset+count>512:self.errors.append('read bounds');return 0
        if self.files:
            data=os.pread(self.files[bank],count,offset)
            if len(data)!=count:return 0
        else:data=bytes(self.image[bank*512+offset:bank*512+offset+count])
        C.memmove(dst,data,count);return 1
    def change(self,index,value,erase=False):
        if self.cut_after is not None and self.mutations>=self.cut_after:return False
        if not erase and self.image[index]&value!=value:
            self.errors.append('flash zero-to-one write');return False
        self.image[index]=value;self.mutations+=1
        if self.files:
            if os.pwrite(self.files[index//512],bytes([value]),index%512)!=1:return False
        return True
    def erase(self,_,bank):
        if bank>1:return 0
        for i in range(512):
            if not self.change(bank*512+i,255,True):return 0
        return 1
    def write(self,_,bank,offset,src,count):
        if bank>1 or offset+count>512:self.errors.append('write bounds');return 0
        for i,v in enumerate(C.string_at(src,count)):
            if not self.change(bank*512+offset+i,v):return 0
        return 1
    def sync(self,_,bank):
        self.syncs+=1
        if self.reenter:self.reenter()
        if self.syncs==self.fail_sync:return 0
        if self.files:os.fsync(self.files[bank])
        return 1
    def reset_faults(self):
        self.cut_after=None;self.mutations=0;self.syncs=0;self.reads=0
        self.fail_sync=None;self.fail_read=None

def load(flash):
    ctx=Context();status=LIB.vr_init(C.byref(ctx),C.byref(flash.io),COVERS)
    return ctx,status
def fresh(flash=None):
    flash=flash or Flash();ctx,status=load(flash)
    assert status==-1,status
    assert LIB.vr_format_empty(C.byref(ctx),CAPS)==0
    flash.reset_faults();return flash,ctx
def info(ctx,slot):
    out=Info();assert LIB.vr_get_info(C.byref(ctx),slot,C.byref(out))==0;return out
def state(ctx):
    return tuple((x.used,x.capacity,x.generation) for x in ctx.slots)
def fix_crc(record):
    struct.pack_into('<I',record,24,zlib.crc32(record[:24]+record[32:]))

class RuntimeTests(unittest.TestCase):
    def test_slot_boundaries_and_serial_generation(self):
        for slot in range(12):
            for percent in (1,9,10,11,100):
                flash,ctx=fresh();used=(100-percent)*(CAPACITY//100)
                self.assertEqual(LIB.vr_consume(C.byref(ctx),slot,used),0)
                serial0=info(ctx,slot).serial
                self.assertEqual(LIB.vr_get_percent(C.byref(ctx),slot),percent)
                before=state(ctx);cover=COVERS[slot]
                self.assertEqual(LIB.vr_cover_close(C.byref(ctx),cover),0)
                self.assertEqual(state(ctx),before)
                self.assertEqual(LIB.vr_cover_open(C.byref(ctx),cover),1)
                self.assertEqual(LIB.vr_cover_open(C.byref(ctx),cover),0)
                expected=(1<<slot) if percent<10 else 0
                self.assertEqual(LIB.vr_cover_close(C.byref(ctx),cover),expected)
                card=info(ctx,slot)
                self.assertEqual(card.generation,1 if percent<10 else 0)
                self.assertEqual(card.used,0 if percent<10 else used)
                self.assertEqual(card.serial!=serial0,percent<10)
                for other in range(12):
                    if other!=slot:self.assertEqual((ctx.slots[other].used,ctx.slots[other].generation),(0,0))
                self.assertEqual(LIB.vr_consume(C.byref(ctx),slot,CAPACITY*95//100),0)
                before=state(ctx)
                self.assertEqual(LIB.vr_cover_close(C.byref(ctx),cover),0)
                self.assertEqual(state(ctx),before)
                reboot,status=load(flash);self.assertEqual(status,0);self.assertEqual(state(reboot),before)
                self.assertEqual(info(reboot,slot).serial,card.serial)
                COUNTS['boundary_scenarios']+=1
                self.assertFalse(flash.errors)

    def test_power_cut_at_every_written_byte(self):
        flash,ctx=fresh();self.assertEqual(LIB.vr_consume(C.byref(ctx),0,CAPACITY*95//100),0)
        baseline=bytes(flash.image);old=state(ctx);old_serial=info(ctx,0).serial
        for cut in range(1025):
            f=Flash(baseline);c,status=load(f);self.assertEqual(status,0)
            LIB.vr_cover_open(C.byref(c),1);f.reset_faults();f.cut_after=cut
            result=LIB.vr_cover_close(C.byref(c),1)
            self.assertIn(result,(-3,1))
            restored,status=load(Flash(f.image));self.assertEqual(status,0)
            current=state(restored)
            if restored.slots[0].generation==0:
                self.assertEqual(current,old);self.assertEqual(info(restored,0).serial,old_serial)
            else:
                self.assertEqual(restored.slots[0].generation,1);self.assertEqual(restored.slots[0].used,0)
                self.assertEqual(info(restored,0).serial,b'V000000001')
                self.assertEqual(current[1:],old[1:])
            self.assertFalse(f.errors);COUNTS['power_cuts']+=1

    def test_each_record_bit_corruption_falls_back(self):
        flash,ctx=fresh();LIB.vr_consume(C.byref(ctx),0,CAPACITY*95//100)
        old=state(ctx);LIB.vr_cover_open(C.byref(ctx),1);LIB.vr_cover_close(C.byref(ctx),1)
        latest=bytes(flash.image);active=ctx.active
        for bit in range(512*8):
            damaged=bytearray(latest);damaged[active*512+bit//8]^=1<<(bit%8)
            restored,status=load(Flash(damaged));self.assertEqual(status,0)
            self.assertEqual(state(restored),old);COUNTS['bit_corruptions']+=1

    def test_ambiguous_commit_requires_recovery(self):
        for fail_kind in ('sync','read'):
            flash,ctx=fresh();LIB.vr_consume(C.byref(ctx),0,CAPACITY*95//100)
            LIB.vr_cover_open(C.byref(ctx),1);flash.reset_faults()
            if fail_kind=='sync':flash.fail_sync=2
            else:flash.fail_read=2
            self.assertEqual(LIB.vr_cover_close(C.byref(ctx),1),-3)
            self.assertEqual(ctx.fault,1)
            self.assertEqual(LIB.vr_consume(C.byref(ctx),0,1),-5)
            flash.reset_faults();restored,status=load(flash);self.assertEqual(status,0)
            self.assertEqual((restored.slots[0].generation,restored.slots[0].used),(1,0))

    def test_reboot_drops_unclosed_cover_edge(self):
        flash,ctx=fresh();LIB.vr_consume(C.byref(ctx),0,CAPACITY*95//100)
        LIB.vr_cover_open(C.byref(ctx),1)
        restored,status=load(flash);self.assertEqual(status,0)
        self.assertEqual(LIB.vr_cover_close(C.byref(restored),1),0)
        self.assertEqual(restored.slots[0].generation,0)

    def test_repeated_resets_survive_reboot_without_serial_reuse(self):
        flash,ctx=fresh();seen={info(ctx,0).serial}
        for generation in range(1,41):
            self.assertEqual(LIB.vr_consume(C.byref(ctx),0,CAPACITY*95//100),0)
            LIB.vr_cover_open(C.byref(ctx),1)
            self.assertEqual(LIB.vr_cover_close(C.byref(ctx),1),1)
            ctx,status=load(flash);self.assertEqual(status,0)
            card=info(ctx,0);self.assertEqual(card.generation,generation)
            self.assertNotIn(card.serial,seen);seen.add(card.serial)
            self.assertEqual(card.used,0)
        for initial in (0xfe,0xff,0xffff,0xffffff):
            record=bytearray(flash.image[ctx.active*512:(ctx.active+1)*512])
            struct.pack_into('<Q',record,32,CAPACITY*95//100)
            struct.pack_into('<I',record,40,initial);fix_crc(record)
            f=Flash(record+bytearray(b'\xff'*512));c,status=load(f);self.assertEqual(status,0)
            LIB.vr_cover_open(C.byref(c),1);self.assertEqual(LIB.vr_cover_close(C.byref(c),1),1)
            self.assertEqual(c.slots[0].generation,initial+1)
            self.assertEqual(info(c,0).serial,('V0'+f'{initial+1:08X}').encode())

    def test_native_usage_reports_are_monotonic(self):
        flash,ctx=fresh();LIB.vr_consume(C.byref(ctx),0,12345)
        sequence=ctx.sequence
        for report in (0,1,12344,12345):
            self.assertEqual(LIB.vr_reconcile_usage(C.byref(ctx),0,report),0)
            self.assertEqual(ctx.slots[0].used,12345);self.assertEqual(ctx.sequence,sequence)
        self.assertEqual(LIB.vr_reconcile_usage(C.byref(ctx),0,12346),0)
        self.assertEqual(ctx.slots[0].used,12346)
        self.assertEqual(LIB.vr_reconcile_usage(C.byref(ctx),0,1<<40),-4)

    def test_negative_backend_errors_are_not_success(self):
        flash,ctx=fresh()
        callback=SYNC(lambda user,bank:-5)
        ctx.io.sync=callback
        self.assertEqual(LIB.vr_consume(C.byref(ctx),0,1),-3)
        self.assertEqual(ctx.slots[0].used,0)

    def test_protocol_profiles_and_identity_publication(self):
        flash,ctx=fresh();models=[b'T44M7',b'T44M3',b'T44MA',b'T44M1',b'T44M6',b'T44M9',
                                b'T44M5',b'T44M4',b'T44MB',b'T44M8',b'T44MD',b'T44M2']
        serials=set()
        for slot in range(13):
            out=Info();self.assertEqual(LIB.vr_exchange(C.byref(ctx),2,slot,None,0,C.byref(out),C.sizeof(out)),0)
            self.assertEqual((out.present,out.virtualized,out.remaining_percent),(1,1,100))
            self.assertEqual(out.manufacturer,b'EPSON');self.assertNotIn(out.serial,serials);serials.add(out.serial)
            if slot<12:self.assertEqual((out.model,out.nominal_ml),(models[slot],700))
            raw=(C.c_uint8*10)();self.assertEqual(LIB.vr_exchange(C.byref(ctx),3,slot,None,0,raw,10),0)
            self.assertEqual(bytes(raw),out.serial);COUNTS['protocol_requests']+=2
            if slot<12:
                original=bytes((i*31+slot)&255 for i in range(192));mirror=C.create_string_buffer(original,192)
                self.assertEqual(LIB.vr_publish_ink_identity(C.byref(ctx),slot,mirror,192),0)
                changed={2*(49+i//2)+(0 if i%2 else 1) for i in range(10)}
                changed|={2*(57+i//2)+(0 if i%2 else 1) for i in range(5)}
                for i,(before,after) in enumerate(zip(original,mirror.raw)):
                    if i not in changed:self.assertEqual(before,after)
        amount=C.c_uint64(100)
        self.assertEqual(LIB.vr_exchange(C.byref(ctx),5,12,C.byref(amount),8,None,0),-4)
        self.assertEqual(info(ctx,12).remaining_percent,100)
        marker=C.create_string_buffer(b'unchanged',10)
        self.assertEqual(LIB.vr_exchange(C.byref(ctx),999,0,None,0,marker,10),-4)
        self.assertEqual(marker.raw,b'unchanged\x00')
        self.assertEqual(LIB.vr_exchange(C.byref(ctx),3,13,None,0,marker,10),-4)

    def test_corruption_version_and_exhaustion(self):
        ctx,status=load(Flash(bytes(1024)));self.assertEqual(status,-2)
        self.assertEqual(LIB.vr_format_empty(C.byref(ctx),CAPS),-5)
        f,c=fresh();record=bytearray(f.image[c.active*512:(c.active+1)*512])
        struct.pack_into('<I',record,8,2);fix_crc(record)
        image=bytearray(f.image);image[:512]=record
        _,status=load(Flash(image));self.assertEqual(status,-8)
        record=bytearray(f.image[:512]);struct.pack_into('<Q',record,32,CAPACITY*95//100)
        struct.pack_into('<I',record,40,0xffffffff);fix_crc(record)
        f=Flash(record+bytearray(b'\xff'*512));c,status=load(f);self.assertEqual(status,0)
        LIB.vr_cover_open(C.byref(c),1);before=state(c)
        self.assertEqual(LIB.vr_cover_close(C.byref(c),1),-6);self.assertEqual(state(c),before)
        self.assertEqual(LIB.vr_consume(C.byref(c),0,(1<<64)-1),0)
        self.assertEqual(c.slots[0].used,(1<<40)-1)

    def test_callback_reentrancy(self):
        flash,ctx=fresh();out=[]
        flash.reenter=lambda:out.append(LIB.vr_consume(C.byref(ctx),1,1))
        self.assertEqual(LIB.vr_consume(C.byref(ctx),0,1),0)
        self.assertEqual(out,[-7,-7]);self.assertEqual(ctx.slots[1].used,0)

    def test_file_backend_recovers_in_new_process(self):
        with tempfile.TemporaryDirectory() as td:
            paths=[Path(td)/f'bank{i}' for i in range(2)]
            for p in paths:p.write_bytes(b'\xff'*512)
            fds=[os.open(p,os.O_RDWR) for p in paths]
            try:
                flash,ctx=fresh(Flash(files=fds))
                LIB.vr_consume(C.byref(ctx),0,CAPACITY*95//100)
                LIB.vr_cover_open(C.byref(ctx),1);self.assertEqual(LIB.vr_cover_close(C.byref(ctx),1),1)
            finally:
                for fd in fds:os.close(fd)
            result=subprocess.check_output([sys.executable,__file__,'--recover',*map(str,paths)],text=True)
            recovered=json.loads(result)
            self.assertEqual(recovered,{'generation':1,'used':0,'serial':'V000000001'})

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--recover':
        f=Flash(Path(sys.argv[2]).read_bytes()+Path(sys.argv[3]).read_bytes());ctx,status=load(f)
        assert status==0,status
        print(json.dumps({'generation':ctx.slots[0].generation,'used':ctx.slots[0].used,'serial':info(ctx,0).serial.decode()}))
    else:
        suite=unittest.defaultTestLoader.loadTestsFromTestCase(RuntimeTests)
        result=unittest.TextTestRunner(verbosity=2).run(suite)
        report={'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
                'skipped':len(result.skipped),'checks':COUNTS,'backend_scope':'Byte-programmable simulated banks and fsync file backend; printer flash not bound'}
        (ROOT/'analysis/virtual-runtime-host-results.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2));sys.exit(not result.wasSuccessful())
