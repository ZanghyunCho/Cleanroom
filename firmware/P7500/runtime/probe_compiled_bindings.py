"""Patch native entries IN EMULATED RAM to the compiled C adapters.

All counter/cover/identity/presence adaptation runs as ARM instructions.
Python hooks only implement byte-storage I/O, OS notifications, and fault
reporting. No on-device RAM or flash allocation is implied by this experiment.
"""
from pathlib import Path
import json
import struct
import sys
import time
from probe_arm_integration import Machine,ROOT,CTX,IO,COVERS,CAPS,OUT,STOP,CAPACITY,NATIVE_MIRROR
sys.path.insert(0,str(ROOT/'tools'))
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import *
from capstone import Cs,CS_ARCH_ARM,CS_MODE_ARM

FAULT=0x47000040
BINDINGS=0x46001400
HOOKS=[(0x433f57c0,'vr_native_get40'),(0x433f5934,'vr_native_set40'),
       (0x433f5b4c,'vr_native_add40'),(0x43403f68,'vr_native_set_cover'),
       (0x434027b0,'vr_native_read_mirror'),(0x43408d30,'vr_native_presence_ptr'),
       (0x434033a4,'vr_native_remaining_info'),(0x433f2f04,'vr_native_waste_info_ptr'),
       (0x43407f20,'vr_native_waste_remaining_info'),(0x43408318,'vr_native_waste_error_code')]

class CompiledMachine(Machine):
    def __init__(self,flash=None,cut=None):
        self.faults=[]
        super().__init__(flash,cut)
        self.u.hook_add(UC_HOOK_CODE,self.hook,begin=FAULT,end=FAULT)
        self.patches=[]
    def hook(self,u,address,size,user):
        if address==FAULT:
            raw=self.reg(UC_ARM_REG_R0);self.faults.append(raw if raw<0x80000000 else raw-0x100000000)
            self.ret(0);return
        if address in (0x47000000,0x47000010,0x47000020,0x47000030,0x4340e59c,0x4340e67c):
            super().hook(u,address,size,user)
        # Native adaptation is intentionally not performed by Python here.
    def install(self):
        trampolines=[];md=Cs(CS_ARCH_ARM,CS_MODE_ARM)
        for index,(entry,name) in enumerate(HOOKS):
            original=bytes(self.u.mem_read(entry,8))
            instructions=list(md.disasm(original,entry))
            needs_original=index<6 or index==7
            if needs_original and (len(instructions)!=2 or any('pc' in i.op_str or i.mnemonic.startswith(('b','ldm')) for i in instructions)):
                raise AssertionError(('Prologue requires relocation support',hex(entry),original.hex()))
            trampoline=0x47000200+index*32 if needs_original else 0
            if needs_original:
                # PC-independent prologue + absolute branch back to original body.
                self.u.mem_write(trampoline,original+struct.pack('<2I',0xe51ff004,entry+8))
            trampolines.append(trampoline)
            self.patches.append({'entry':hex(entry),'adapter':name,'adapter_address':hex(self.symbols[name]),
                                 'trampoline':hex(trampoline) if trampoline else None,'original_prologue_hex':original.hex()})
        self.u.mem_write(BINDINGS,struct.pack('<9I',*trampolines[:6],FAULT,NATIVE_MIRROR,trampolines[7]))
        if self.call('vr_native_attach',CTX,BINDINGS)!=0:raise AssertionError('Compiled adapter attachment failed')
        for entry,name in HOOKS:
            self.u.mem_write(entry,struct.pack('<2I',0xe51ff004,self.symbols[name]))
            self.u.ctl_remove_cache(entry,entry+8)

def main():
    start=time.monotonic();m=CompiledMachine();m.format();m.install()
    identities=[];cases=0
    for slot in range(12):
        cover=m.call(0x4340a9f8,slot)
        p=m.call(0x43408d30,slot)
        if m.u.mem_read(p,1)!=b'\x01':raise AssertionError('Compiled presence adapter failed')
        old,vendor=m.native_identity(slot)
        if vendor!='EPSON':raise AssertionError('Compiled vendor adapter failed')
        m.call(0x433ffe50,slot,CAPACITY*90//100)
        if m.call(0x433fffd8,slot)!=10 or m.call(0x434033a4,slot)!=10:
            raise AssertionError('Native and provider percentage diverged at 10')
        m.call(0x4340e5c8,cover);m.call(0x4340e6a0,cover)
        if m.info(slot)['generation']!=0:raise AssertionError('Compiled binding reset exactly 10')
        m.call(0x433ffe50,slot,1)
        before=m.info(slot)
        m.call(0x433ffd3c,slot)  # stale native zero report, not an owner cover reset
        if m.info(slot)!=before:raise AssertionError('Stale native zero erased durable usage')
        m.call(0x4340e6a0,cover)
        if m.info(slot)!=before:raise AssertionError('Close without a fresh open reset generation')
        m.call(0x4340e5c8,cover);m.call(0x4340e6a0,cover)
        card=m.info(slot);new,vendor=m.native_identity(slot)
        if (card['generation'],card['used'],card['percent'])!=(1,0,100):raise AssertionError('Compiled transaction mismatch')
        if old==new or new!=card['serial'] or vendor!='EPSON':raise AssertionError('Compiled native identity mismatch')
        identities.append(new);cases+=2
    snapshot=bytes(m.flash);expected=[m.info(s) for s in range(13)]
    waste_pointer=m.call(0x433f2f04,0)
    if bytes(m.u.mem_read(waste_pointer,8))!=bytes([1,0,0,100,0,0,0,0]):
        raise AssertionError('Native waste profile layout mismatch')
    if m.call(0x43407f20,0)!=100 or any(m.call(0x43408318,i)!=0 for i in range(0x24)):
        raise AssertionError('Native virtual waste remaining/error getter failed')
    reboot=CompiledMachine(snapshot)
    if reboot.init_status!=0:raise AssertionError('Compiled runtime restore failed')
    reboot.install()
    for s in range(13):
        if reboot.info(s)!=expected[s]:raise AssertionError('Persistent profile differed after ARM reboot')
        if s<12 and reboot.native_identity(s)[0]!=identities[s]:raise AssertionError('Restored identity not visible to original native getter')
    # Durable write failure is reported instead of silently treating the native
    # void-return counter operation as a successful consumption update.
    reboot.cut=0;reboot.mutations=0
    reboot.call(0x433ffe50,0,123)
    if reboot.call('vr_native_fault')!=0xfffffffd or reboot.faults!=[-3]:
        raise AssertionError('Compiled adapter swallowed a storage failure')
    p=reboot.call(0x43408d30,0)
    if reboot.u.mem_read(p,1)!=b'\0' or reboot.call(0x434033a4,0)!=ord('n'):
        raise AssertionError('Faulted adapter published a healthy/full profile')
    waste_pointer=reboot.call(0x433f2f04,0)
    if reboot.u.mem_read(waste_pointer,1)!=b'\0' or reboot.call(0x43407f20,0)!=ord('n'):
        raise AssertionError('Faulted adapter published a healthy maintenance profile')
    if m.faults:raise AssertionError(('Unexpected compiled adapter faults',m.faults))
    report={
        'scope':'Actual 8-byte ARM entry patches to compiled C adapters in emulated RAM',
        'native_boundary_cases_passed':cases,'generation_and_native_serial_cases_passed':12,
        'stale_native_zero_reports_preserved':12,'restored_profiles_passed':13,
        'native_presence_slots_passed':12,'storage_failure_reporting_passed':True,
        'native_maintenance_info_layout_passed':True,'native_maintenance_error_getters_passed':0x24,
        'patches':m.patches,'elapsed_seconds':round(time.monotonic()-start,3),
        'python_hooks':'Storage transport, OS notifications and fault reporting only',
        'printer_ram_and_flash_placement_allocated':False,
        'printer_nor_erase_sync_contract_verified':False,
        'hardware_asic_spi_authentication_tested':False,
        'maintenance_scope':'Compiled native information/remaining/error getters; no physical GF-chip wire emulation',
        'flash_image_generated':False,
    }
    (ROOT/'analysis/compiled-native-binding-results.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
