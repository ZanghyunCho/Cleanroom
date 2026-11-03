"""Execute the compiled backend through original synchronous P7500 NV APIs.

Original ARM validates records and submits/waits for NV messages. The OS and
physical NV worker are modeled with fsync files; native flash GC is NOT run.
"""
import json
import os
import struct
import tempfile
import time
from pathlib import Path
from probe_compiled_bindings import CompiledMachine
from probe_arm_integration import ROOT,CTX,IO,CAPS,COVERS,OUT,CAPACITY
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import *
from capstone import Cs,CS_ARCH_ARM,CS_MODE_ARM

BACKEND=0x46004000
MESSAGE=0x46008000
REPLY=0x46008100
TABLE=0x43740e74
MAP=0xb9a5802c
IMPORTS=(0x436415bc,0x436415b4,0x436415a4,0x4364158c,0x4364159c,
         0x4360ba90,0x4360c650,0x4360c404,0x4360c428)

class NvMachine(CompiledMachine):
    def __init__(self,paths):
        super().__init__()
        self.paths=paths;self.events=[];self.pending=None;self.fail_completion=0;self.observe=None
        self.write_completions=0;self.fail_write_after_store=None
        self.u.mem_map(0xb9a40000,0x20000)
        for a in IMPORTS:self.u.hook_add(UC_HOOK_CODE,self.native_os,begin=a,end=a)
        # Without the legacy range guard, registration must be refused.
        if self.call('vr_nv_p7500_register_owner')!=0xfffffffb:
            raise AssertionError('Owner registration accepted an unguarded native API')
        validator=0x435f3274;trampoline=0x47000700
        raw=bytes(self.u.mem_read(validator,8))
        instructions=list(Cs(CS_ARCH_ARM,CS_MODE_ARM).disasm(raw,validator))
        if len(instructions)!=2 or any('pc' in i.op_str or i.mnemonic.startswith(('b','ldm')) for i in instructions):
            raise AssertionError('NV validator prologue needs relocation support')
        self.u.mem_write(trampoline,raw+struct.pack('<2I',0xe51ff004,validator+8))
        if self.call('vr_nv_guard_attach',trampoline)!=0:raise AssertionError('NV guard attachment failed')
        self.u.mem_write(validator,struct.pack('<2I',0xe51ff004,self.symbols['vr_nv_guard']))
        self.u.ctl_remove_cache(validator,validator+8)
        # Run the ORIGINAL layout constructor both before and after registration.
        self.call(0x435f364c)
        before=bytes(self.u.mem_read(MAP,157*12))
        volumes_before=bytes(self.u.mem_read(0xb9a57c8c,29*32))
        if self.call('vr_nv_p7500_register_owner')!=0:raise AssertionError('Native registration failed')
        if self.call('vr_nv_p7500_init',BACKEND,CAPS,IO)!=0xfffffffb:
            raise AssertionError('Backend accepted a stale native ID map')
        self.call(0x435f364c)
        after=bytes(self.u.mem_read(MAP,157*12))
        if bytes(self.u.mem_read(0xb9a57c8c,29*32))!=volumes_before:
            raise AssertionError('Owner registration changed native volume geometry')
        for row in range(157):
            old=struct.unpack_from('<3I',before,row*12);new=struct.unpack_from('<3I',after,row*12)
            if row in (121,122):
                if new!=(0x01607500+row-121,*old[1:]):raise AssertionError('Owner mapping moved')
            elif old!=new:raise AssertionError(('Original record mapping changed',row))
        self.layout_before=before;self.layout_after=after
        # Original off-by-one validation really does accept the aliased legacy
        # index. Exercise both the original ARM routine and the compiled guard.
        for index in range(11):
            self.u.mem_write(OUT,struct.pack('<IIHH',0x01600945,1,index,index)+b'\0'*12)
            if self.call(trampoline,OUT,OUT+128,1,OUT+256)!=0:
                raise AssertionError('Unexpected original legacy range contract')
            guarded=self.call(validator,OUT,OUT+128,1,OUT+256)
            if guarded!=(0 if index<10 else 0x1002):
                raise AssertionError('Legacy alias guard rejected valid data or admitted alias')
        alias=self.call(0x435f37e8,0x01600945,10,0,OUT+256)
        owner=self.call(0x435f37e8,0x01607500,0,0,OUT+256)
        if alias!=owner:raise AssertionError('Legacy alias counterexample no longer reproduces')
        for id in (0x01607500,0x01607501):
            for operation in (1,2):
                self.u.mem_write(OUT,struct.pack('<IIHH',id,128,1,1)+b'\0'*12)
                if self.call(trampoline,OUT,OUT+128,operation,OUT+256)!=0:
                    raise AssertionError('Unexpected original owner range behavior')
                if self.call(validator,OUT,OUT+128,operation,OUT+256)!=0x1002:
                    raise AssertionError('Owner out-of-bounds index admitted')
        if self.call('vr_nv_p7500_init',BACKEND,CAPS,IO)!=0:raise AssertionError('P7500 NV binding failed')
        self.nv_init_status=self.call('vr_init',CTX,IO,COVERS)
    def native_os(self,u,a,size,user):
        r0,r1,r2=[self.reg(r) for r in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2)]
        if a==0x436415bc:u.mem_write(r0,bytes([r1&255])*r2);self.ret(r0)
        elif a==0x436415b4:u.mem_write(r0,bytes(u.mem_read(r1,r2)));self.ret(r0)
        elif a in (0x4364158c,0x4364159c):
            if r0!=8:raise AssertionError('Unexpected NV mutex')
            self.ret(0)
        elif a==0x436415a4:
            if r0!=REPLY:raise AssertionError('Unexpected message free')
            self.ret(0)
        elif a==0x4360ba90:
            u.mem_write(MESSAGE,b'\0'*128);u.mem_write(r1,struct.pack('<I',MESSAGE));self.ret(0)
        elif a==0x4360c650:u.mem_write(r0,struct.pack('<2H',0x23,0));self.ret(0)
        elif a==0x4360c404:
            if r0!=0x1a or self.pending is not None:raise AssertionError('Unexpected NV request dispatch')
            opcode=struct.unpack('<H',u.mem_read(r1+0x10,2))[0]
            request=self.read32(r1+0x14);data=self.read32(r1+0x20)
            raw=bytes(u.mem_read(request,24));id,n,first,last=struct.unpack_from('<IIHH',raw)
            if id not in (0x01607500,0x01607501) or n!=128 or first or last or raw[14]:
                raise AssertionError('Original native wrapper received wrong record ABI')
            if opcode not in (1,2):raise AssertionError('Unexpected NV operation')
            self.pending=(opcode,id-0x01607500,data)
            self.events.append(('queued',opcode))
            # Queue acceptance does not mutate storage or fabricate completion.
            self.ret(0)
        elif a==0x4360c428:
            if r0!=0x1b or self.pending is None:raise AssertionError('Native wrapper did not wait for its NV reply')
            opcode,bank,data=self.pending;self.pending=None
            if self.observe:self.observe()
            result=self.fail_completion
            if not result:
                if opcode==1:
                    try:raw=self.paths[bank].read_bytes()
                    except FileNotFoundError:raw=b''
                    if len(raw)!=128:result=1
                    else:u.mem_write(data,raw)
                else:
                    fd=os.open(self.paths[bank],os.O_WRONLY|os.O_CREAT,0o600)
                    try:
                        if os.pwrite(fd,bytes(u.mem_read(data,128)),0)!=128:raise AssertionError('Short NV fixture write')
                        os.fsync(fd)
                    finally:os.close(fd)
                    directory=os.open(self.paths[bank].parent,os.O_RDONLY|os.O_DIRECTORY)
                    try:os.fsync(directory)
                    finally:os.close(directory)
                    self.write_completions+=1
                    if self.write_completions==self.fail_write_after_store:result=7
            self.events.append(('completed',opcode,result))
            u.mem_write(REPLY,b'\0'*128);u.mem_write(REPLY+0x14,struct.pack('<H',result))
            u.mem_write(r2,struct.pack('<I',REPLY));self.ret(0)

def main():
    start=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='p7500-nv-') as tmp:
        paths=[Path(tmp)/f'owner-{i}.bin' for i in range(2)]
        # Explicitly preprovisioned test fixtures. Missing records must not be
        # interpreted as empty media by the production bridge.
        for path in paths:path.write_bytes(b'\xff'*128)
        m=NvMachine(paths)
        if m.nv_init_status!=0xffffffff:raise AssertionError('Preprovisioned empty objects not recognized')
        if m.call('vr_format_empty',CTX,CAPS)!=0:raise AssertionError('Native NV formatting failed')
        m.install()
        for slot in range(12):
            old=bytes(m.u.mem_read(CTX+24,12*24))
            def unpublished():
                if bytes(m.u.mem_read(CTX+24,12*24))!=old:
                    raise AssertionError('Core published state before NV completion')
            m.observe=unpublished
            m.call(0x433ffe50,slot,CAPACITY*91//100)
            m.observe=None
            cover=m.call(0x4340a9f8,slot)
            m.call(0x4340e5c8,cover);m.call(0x4340e6a0,cover)
            if m.info(slot)['generation']!=1:raise AssertionError('Native-NV cover transaction failed')
        expected=[m.info(s) for s in range(13)]
        reboot=NvMachine(paths)
        if reboot.nv_init_status!=0:raise AssertionError('Fresh ARM machine failed to restore native NV files')
        reboot.install()
        for s in range(13):
            if reboot.info(s)!=expected[s]:raise AssertionError('Native NV reboot state differs')
        before=reboot.info(0);reboot.fail_completion=7
        reboot.call(0x433ffe50,0,1)
        if reboot.faults!=[-3] or reboot.info(0)!=before:
            raise AssertionError('Queue acceptance swallowed NV completion failure')
        stable=NvMachine(paths)
        if stable.nv_init_status!=0 or stable.info(0)!=before:
            raise AssertionError('Failed service operation changed durable state')
        # A commit can reach storage even when its completion reports failure.
        # The runtime must fault, then recover the committed identity at reboot.
        ambiguous=NvMachine(paths);ambiguous.install()
        ambiguous.call(0x433ffe50,0,CAPACITY*95//100)
        generation=ambiguous.info(0)['generation']
        ambiguous.fail_write_after_store=ambiguous.write_completions+2
        ambiguous.call(0x4340e5c8,1);ambiguous.call(0x4340e6a0,1)
        if ambiguous.faults!=[-3]:raise AssertionError('Ambiguous commit was accepted')
        recovered=NvMachine(paths)
        if recovered.nv_init_status!=0 or recovered.info(0)['generation']!=generation+1:
            raise AssertionError('Reboot failed to reconcile ambiguous committed generation')
        paths[0].unlink();missing=NvMachine(paths)
        if missing.nv_init_status!=0xfffffffd:
            raise AssertionError('Missing NV record was auto-initialized')
        if missing.call('vr_nv_install_empty_records',BACKEND)!=0:
            raise AssertionError('Explicit installer provisioning failed')
        if missing.call('vr_init',CTX,IO,COVERS)!=0xffffffff:
            raise AssertionError('Installer did not leave two explicitly empty records')
        if missing.call('vr_format_empty',CTX,CAPS)!=0:
            raise AssertionError('Initial owner format failed after provisioning')
        installed=NvMachine(paths)
        if installed.nv_init_status!=0 or installed.info(0)['generation']!=0:
            raise AssertionError('New owner state did not survive a fresh ARM instance')
        report={
            'scope':'Compiled ARM backend through original NV validation, queue submission and completion wait; fsync worker fixture',
            'native_api_entries':['0x435efdd4','0x435efdf0'],
            'owner_record_ids':['0x01607500','0x01607501'],
            'original_record_mappings_preserved':155,'owner_record_offsets_preserved':2,
            'original_volume_geometries_preserved':29,'compact_bytes_per_bank':128,
            'generation_transactions_passed':12,'restored_profiles_passed':13,
            'state_not_published_before_service_completion':True,'queued_but_failed_completion_rejected':True,
            'failed_reply_after_durable_commit_reconciled_on_reboot':True,
            'missing_record_not_autoformatted':True,'native_queue_events':len(m.events),
            'stale_native_id_map_rejected':True,
            'unguarded_native_registration_rejected':True,
            'legacy_valid_indices_preserved':10,'legacy_off_by_one_owner_alias_blocked':True,
            'owner_out_of_bounds_read_write_cases_blocked':4,
            'native_flash_worker_and_gc_executed':False,'explicit_installer_provisioning_passed':True,
            'automatic_boot_reset_enabled':False,
            'printer_startup_hook_installed':False,'physical_printer_tested':False,
            'elapsed_seconds':round(time.monotonic()-start,3)}
    (ROOT/'analysis/native-nv-arm-results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
