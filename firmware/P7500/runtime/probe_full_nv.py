"""Full metadata through original NV APIs and a compiled prefix-preserving worker.

Physical flash calls are a file-backed test transport, not on-device evidence.
"""
import json
import os
import struct
import tempfile
import time
from pathlib import Path
from probe_compiled_bindings import CompiledMachine
from probe_native_nv import NvMachine,IMPORTS,MESSAGE,REPLY,TABLE,MAP
from probe_arm_integration import ROOT,CTX,IO,CAPS,COVERS,OUT,NATIVE_MIRROR,CAPACITY
from test_metadata_store import image
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import *
from capstone import Cs,CS_ARCH_ARM,CS_MODE_ARM

VM=0x46010000;VF=0x46018000;SCRATCH=0x46022000;OUTER_IO=0x46025000;API=0x46025800
RAW_READ=0x470009a0;RAW_WRITE=0x470009b0;FINISH=0x47000980
OBJECT=9216;PREFIX=1024;OBJECT_ID=0x01600fff

class FullMachine(CompiledMachine):
    instruction_limit=30_000_000
    timeout_us=15_000_000
    def __init__(self,path,installer=False):
        super().__init__();self.path=path;self.events=[];self.pending=None;self.fail_completion=0
        self.worker_continuation=None;self.before_worker=None;self.fail_after_write=False
        self.u.mem_map(0xb9a40000,0x20000)
        for a in (*IMPORTS,RAW_READ,RAW_WRITE,FINISH):self.u.hook_add(UC_HOOK_CODE,self.full_os,begin=a,end=a)
        self.call(0x435f364c);before=bytes(self.u.mem_read(MAP,157*12))
        volumes=bytes(self.u.mem_read(0xb9a57c8c,29*32))
        for index,(entry,symbol) in enumerate(((0x435f3274,'vf_guard'),(0x435f1e58,'vf_worker_write'))):
            raw=bytes(self.u.mem_read(entry,8));instructions=list(Cs(CS_ARCH_ARM,CS_MODE_ARM).disasm(raw,entry))
            if len(instructions)!=2 or any('pc' in x.op_str or x.mnemonic.startswith(('b','ldm')) for x in instructions):
                raise AssertionError('Full NV hook prologue requires relocation')
            trampoline=0x47000700+index*32
            self.u.mem_write(trampoline,raw+struct.pack('<2I',0xe51ff004,entry+8))
            if not index and self.call('vf_guard_attach',trampoline)!=0:raise AssertionError('Guard attach failed')
            self.u.mem_write(entry,struct.pack('<2I',0xe51ff004,self.symbols[symbol]));self.u.ctl_remove_cache(entry,entry+8)
        if self.call('vf_extend_profile',TABLE,157)!=0:raise AssertionError('Unknown NV table profile')
        self.call(0x435f364c)
        if bytes(self.u.mem_read(MAP,157*12))!=before:raise AssertionError('An existing NV record mapping moved')
        after=bytes(self.u.mem_read(0xb9a57c8c,29*32));expected=bytearray(volumes)
        for off in (10*32+4,10*32+12):struct.pack_into('<I',expected,off,struct.unpack_from('<I',volumes,off)[0]+8192)
        if after!=expected:raise AssertionError('Unexpected volume geometry change')
        if self.call('vf_validate_layout',TABLE,MAP,0xb9a57c8c)!=0:raise AssertionError('NV capacity/layout guard failed')
        if self.call('vf_worker_attach',RAW_READ,RAW_WRITE,SCRATCH,OBJECT)!=0:raise AssertionError('Worker attach failed')
        self.u.mem_write(API,struct.pack('<2I',0x435efdd4,0x435efdf0))
        if self.call('vf_init',VF,API,OUTER_IO)!=0:raise AssertionError('Full NV bridge attach failed')
        if installer and self.call('vf_install_empty',VF)!=0:raise AssertionError('Explicit installation failed')
        self.store_status=self.call('vm_init',VM,OUTER_IO)
        if installer:
            if self.store_status!=0xffffffff or self.call('vm_format_empty',VM)!=0:raise AssertionError('Metadata format failed')
        elif self.store_status!=0:raise AssertionError(('Metadata restore failed',hex(self.store_status)))
        if self.call('vm_core_io',VM,IO)!=0:raise AssertionError('Nested core IO failed')
        self.core_status=self.call('vr_init',CTX,IO,COVERS)
        if installer:
            if self.core_status!=0xffffffff or self.call('vr_format_empty',CTX,CAPS)!=0:raise AssertionError('Core format failed')
            for slot in range(13):
                self.u.mem_write(OUT,image(slot))
                if self.call('vm_put',VM,slot,OUT,192)!=0:raise AssertionError('Initial metadata seed failed')
        elif self.core_status!=0:raise AssertionError('Core restore failed')
        self.install()
        if self.call('vr_native_metadata_attach',VM)!=0:raise AssertionError('Native metadata attach failed')
    def transfer(self,request,data,write=False):
        raw=bytes(self.u.mem_read(request,24));id,n,first,last=struct.unpack_from('<IIHH',raw)
        if id!=OBJECT_ID or not 0<n<=OBJECT or first or last:raise AssertionError('Unexpected full NV request')
        if self.fail_completion:return self.fail_completion
        current=self.path.read_bytes()
        if write:
            if n!=OBJECT:raise AssertionError('Prefix worker did not expand native write')
            fd=os.open(self.path,os.O_WRONLY)
            try:
                if os.pwrite(fd,bytes(self.u.mem_read(data,n)),0)!=n:raise AssertionError('Short NV fixture write')
                os.fsync(fd)
            finally:os.close(fd)
            return 7 if self.fail_after_write else 0
        if len(current)<n:return 1
        self.u.mem_write(data,current[:n]);return 0
    def reply(self,result,output,lr):
        self.events.append(('completed',result));self.pending=None
        self.u.mem_write(REPLY,b'\0'*128);self.u.mem_write(REPLY+0x14,struct.pack('<H',result))
        self.u.mem_write(output,struct.pack('<I',REPLY));self.u.reg_write(UC_ARM_REG_R0,0);self.u.reg_write(UC_ARM_REG_PC,lr)
    def full_os(self,u,a,size,user):
        r0,r1,r2=[self.reg(r) for r in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2)]
        if a in (RAW_READ,RAW_WRITE):self.ret(self.transfer(r0,r1,a==RAW_WRITE));return
        if a==FINISH:
            output,lr=self.worker_continuation;self.worker_continuation=None
            self.reply(r0,output,lr);return
        if a==0x4360c404:
            if r0!=0x1a or self.pending is not None:raise AssertionError('Unexpected NV queue use')
            op=struct.unpack('<H',u.mem_read(r1+0x10,2))[0]
            self.pending=(op,self.read32(r1+0x14),self.read32(r1+0x20));self.events.append(('queued',op));self.ret(0);return
        if a==0x4360c428:
            if r0!=0x1b or self.pending is None:raise AssertionError('Missing NV completion wait')
            op,request,data=self.pending;lr=self.reg(UC_ARM_REG_LR)
            if op==1:self.reply(self.transfer(request,data),r2,lr);return
            if op!=2:raise AssertionError('Unsupported NV message operation')
            if self.before_worker:self.before_worker();self.before_worker=None
            self.worker_continuation=(r2,lr)
            for reg,value in ((UC_ARM_REG_R0,request),(UC_ARM_REG_R1,data),(UC_ARM_REG_R2,0xb9a57c8c+10*32),(UC_ARM_REG_LR,FINISH)):
                u.reg_write(reg,value)
            u.reg_write(UC_ARM_REG_PC,0x435f1e58);return
        NvMachine.native_os(self,u,a,size,user)

def main():
    start=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='p7500-full-nv-') as temp:
        path=Path(temp)/'native-record';prefix=bytes((i*11)&255 for i in range(PREFIX));path.write_bytes(prefix)
        m=FullMachine(path,True)
        if path.read_bytes()[:PREFIX]!=prefix:raise AssertionError('Installer changed original native prefix')
        for slot in range(12):
            p=NATIVE_MIRROR+slot*192;raw=bytearray(m.u.mem_read(p,192));raw[150]^=0x5a
            m.u.mem_write(p,bytes(raw))
            if m.call(0x43400f18,slot,0)!=0:raise AssertionError('Full-image native flush failed')
            m.call(0x433ffe50,slot,CAPACITY*91//100)
            cover=m.call(0x4340a9f8,slot);m.call(0x4340e5c8,cover);m.call(0x4340e6a0,cover)
        expected=[m.info(s) for s in range(13)]
        # Native prefix update must preserve all owner records.
        before=path.read_bytes()[PREFIX:];new_prefix=bytes((i*7)&255 for i in range(PREFIX))
        m.u.mem_write(OUT,new_prefix);m.u.mem_write(OUT+0x800,struct.pack('<II',OBJECT_ID,PREFIX)+b'\0'*16)
        if m.call(0x435efdf0,OUT+0x800,OUT)!=0:raise AssertionError('Native prefix update failed')
        if path.read_bytes()[:PREFIX]!=new_prefix or path.read_bytes()[PREFIX:]!=before:raise AssertionError('Prefix update lost owner metadata')
        reboot=FullMachine(path)
        for slot in range(13):
            if reboot.info(slot)!=expected[slot]:raise AssertionError('Full NV core restore mismatch')
            if reboot.call('vm_get',VM,slot,OUT,192)!=0:raise AssertionError('Full profile restore failed')
            raw=bytes(reboot.u.mem_read(OUT,192))
            if slot<12 and raw[150]!=(image(slot)[150]^0x5a):raise AssertionError('Unknown chip metadata byte was lost')
            if slot==12 and raw!=image(12):raise AssertionError('Maintenance metadata lost')
        # A newer native prefix appearing between owner read and write wins.
        latest=b'Z'*PREFIX
        def concurrent_prefix():
            with path.open('r+b') as f:f.write(latest);f.flush();os.fsync(f.fileno())
        reboot.before_worker=concurrent_prefix
        changed=bytearray(image(12));changed[170]^=1;reboot.u.mem_write(OUT,bytes(changed))
        if reboot.call('vm_put',VM,12,OUT,192)!=0:raise AssertionError('Prefix merge caused false storage failure')
        if path.read_bytes()[:PREFIX]!=latest:raise AssertionError('Stale owner snapshot overwrote latest native prefix')
        report={'scope':'Full journal and compiled native mirror adapter through original NV API and compiled prefix-preserving worker',
                'existing_record_mappings_preserved':157,'native_prefix_preserved':True,'native_prefix_update_preserved_owner_data':True,
                'concurrent_latest_prefix_preserved':True,'full_ink_profiles_restored':12,'maintenance_profile_restored':True,
                'core_profiles_restored':13,'object_bytes':OBJECT,'native_volume_extra_logical_bytes':8192,
                'native_flash_worker_executed':False,'physical_printer_tested':False,'elapsed_seconds':round(time.monotonic()-start,3)}
    (ROOT/'analysis/full-native-nv-results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
