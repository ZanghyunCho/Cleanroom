"""Execute statically patched actual-address modules, not emulator-linked code.

Legacy DSM restore and physical NV worker are fixtures. No physical boot claim.
"""
from pathlib import Path
import json,os,struct,sys,tempfile,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'runtime'));sys.path.insert(0,str(ROOT/'delivery'))
from assemble import assemble,branch
from probe_compiled_bindings import CompiledMachine
from probe_full_nv import FullMachine,FINISH,IMPORTS,RAW_READ,RAW_WRITE
from probe_arm_integration import OUT,NATIVE_MIRROR,CAPACITY
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import *

class DeliveryMachine(FullMachine):
    instruction_limit=500_000_000
    timeout_us=30_000_000
    def __init__(self,path,mode):
        CompiledMachine.__init__(self)
        self.path=path;self.events=[];self.pending=None;self.fail_completion=0;self.worker_continuation=None
        self.before_worker=None;self.fail_after_write=False;self.heap=0x46030000;self.allocations=[]
        module,symbols,self.assembly=assemble(mode)
        self.u.mem_write(0x433e0000,module);self.symbols=symbols
        self.u.ctl_remove_cache(0x433e0000,0x43745ca0)
        if self.call(0x43409858)!=1:raise AssertionError('Native config initialization failed')
        self.u.mem_map(0xb9a40000,0x20000)
        for a in (*IMPORTS,RAW_READ,RAW_WRITE,FINISH):self.u.hook_add(UC_HOOK_CODE,self.full_os,begin=a,end=a)
        for a in (0x4360c948,0x435f0dfc,symbols['original_write'],symbols['original_restore']):
            self.u.hook_add(UC_HOOK_CODE,self.bootstrap_os,begin=a,end=a)
        self.call(0x435f364c)
        self.call(0x433f2f94)
    def bootstrap_os(self,u,a,size,user):
        r0,r1,r2,r3=[self.reg(r) for r in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)]
        if a==0x4360c948:
            if r0!=1 or r1 or r2>128*1024 or self.heap+r2>0x46100000:raise AssertionError('Invalid bootstrap allocation')
            address=self.heap;self.heap=(self.heap+r2+7)&~7;u.mem_write(r3,struct.pack('<I',address))
            self.allocations.append(r2);self.ret(0);return
        if a==0x435f0dfc:self.ret(self.transfer(r0,r1));return
        if a==self.symbols['original_write']:self.ret(self.transfer(r0,r1,True));return
        # Minimal legacy DSM restore fixture. It calls the ACTUAL statically
        # patched pointer getters before the owner context is attached, and
        # writes through both pointers. A NULL early getter faults immediately.
        stub=0x43fc0000;code=[0xe92d4010,0xe3a00000]
        code.append(struct.unpack('<I',branch(stub+len(code)*4,0x43408d30,link=True))[0])
        code += [0xe3a01001,0xe5c01000,0xe3a00000]
        code.append(struct.unpack('<I',branch(stub+len(code)*4,0x433f2f04,link=True))[0])
        code += [0xe3a01001,0xe5c01000,0xe3a00000,0xe8bd8010]
        u.mem_write(stub,struct.pack('<'+'I'*len(code),*code));u.ctl_remove_cache(stub,stub+len(code)*4)
        u.reg_write(UC_ARM_REG_PC,stub)
    def core_state(self):
        address=self.call('payload_context')
        return [struct.unpack('<QQI',self.u.mem_read(address+24+s*24,20)) for s in range(12)]

def main():
    start=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='p7500-delivery-') as temp:
        path=Path(temp)/'object';prefix=bytes((i*13)&255 for i in range(1024));path.write_bytes(prefix)
        installed=DeliveryMachine(path,'installer')
        if installed.call('payload_status')!=0:raise AssertionError(('Installer bootstrap failed',hex(installed.call('payload_status'))))
        if path.read_bytes()[:1024]!=prefix:raise AssertionError('Installer replaced native prefix')
        if installed.call(0x434039b0,0)!=CAPACITY:raise AssertionError('Native capacity not bound')
        installed.call(0x433ffe50,0,CAPACITY*91//100)
        installed.call(0x4340e5c8,1);installed.call(0x4340e6a0,1)
        p=NATIVE_MIRROR;data=bytearray(installed.u.mem_read(p,192));data[151]^=0xa7;installed.u.mem_write(p,bytes(data))
        if installed.call(0x43400f18,0,0)!=0:raise AssertionError('Installed native metadata flush failed')
        waste=bytearray(installed.u.mem_read(0x437c7874,192));waste[190]=0x5a;installed.u.mem_write(0x437c7874,bytes(waste))
        if installed.call(0x4340716c,0,0)!=0:raise AssertionError('GF metadata flush failed')
        if installed.call(0x43406d98,0,15)!=0 or installed.call(0x434072e4,0,2)!=0:raise AssertionError('GF control write failed')
        if installed.call(0x43406d24,0,OUT)!=0 or struct.unpack('<H',installed.u.mem_read(OUT,2))[0]!=15:
            raise AssertionError('GF command overwrote independent mode')
        installed.u.mem_write(OUT,b'\xa5'*8)
        if installed.call(0x433f771c,0,OUT)!=0 or installed.u.mem_read(OUT,1)!=b'\0':raise AssertionError('Native GF bus ready ABI mismatch')
        expected=installed.core_state()
        running=DeliveryMachine(path,'runtime')
        if running.call('payload_status')!=0 or running.core_state()!=expected:raise AssertionError('Runtime bootstrap restore failed')
        if running.u.mem_read(NATIVE_MIRROR+151,1)!=bytes([data[151]]):raise AssertionError('Ink metadata not restored on bootstrap')
        if running.u.mem_read(0x437c7874+190,1)!=b'\x5a':raise AssertionError('Maintenance metadata not restored')
        if running.call(0x43406d24,0,OUT)!=0 or struct.unpack('<H',running.u.mem_read(OUT,2))[0]!=15:raise AssertionError('GF mode not durable')
        # The runtime image must never format unknown or missing owner records.
        unknown=Path(temp)/'uninitialized';unknown.write_bytes(prefix)
        failed=DeliveryMachine(unknown,'runtime')
        if failed.call('payload_status')==0 or unknown.read_bytes()!=prefix:raise AssertionError('Runtime autoformatted missing metadata')
        report={'scope':'Actual-address statically patched module, native NV APIs and compiled bootstrap; legacy DSM restore/physical NV fixtures',
                'installer_bootstrap_passed':True,'runtime_bootstrap_restore_passed':True,
                'early_native_pointer_getters_passed':True,'heap_allocation_bytes':installed.allocations,
                'ink_generation_and_full_metadata_restored':True,'maintenance_full_metadata_and_mode_restored':True,
                'native_gf_bus_ready_passed':True,'native_prefix_preserved':True,'runtime_missing_metadata_not_formatted':True,
                'physical_printer_boot_tested':False,'physical_power_cut_tested':False,
                'elapsed_seconds':round(time.monotonic()-start,3)}
    (ROOT/'analysis/delivery-bootstrap-results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
