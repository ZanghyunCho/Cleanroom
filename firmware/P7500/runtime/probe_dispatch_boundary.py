"""Reproduce physical dispatch and the failure of a null-callback bypass.

Only emulator RAM is modified. This is a boundary experiment, not a virtual
replacement for the still-unmapped native job payloads.
"""
import json
import struct
from probe_compiled_bindings import CompiledMachine
from probe_arm_integration import ROOT, OUT
from unicorn import UC_HOOK_CODE

TABLE_LITERAL=0x433f6e34
TABLE=0x4365c444
STRIDE=116
SELECTOR=0x43705f40


def main():
    m=CompiledMachine();m.format();m.install()
    if m.read32(TABLE_LITERAL)!=TABLE:
        raise AssertionError('Unexpected native dispatch table')
    original=bytes(m.u.mem_read(TABLE,2*STRIDE))
    callbacks=set(struct.unpack('<58I',original))-{0}
    if not all(0x433e0000<=p<0x43700000 and p%4==0 for p in callbacks):
        raise AssertionError('Table contains an unrecognized callback')
    routes=[]
    for slot in range(12):
        access=m.call(0x4340a84c,slot);driver=m.call(0x4340a8a0,slot)
        if (access,driver)!=(slot//6,1):
            raise AssertionError('Unexpected ink driver routing')
        routes.append({'slot':slot,'access':access,'driver':driver})
    channels=m.call(0x4340a840)
    access_routes=[]
    for channel in range(channels):
        access=m.call(0x4340a888,channel)
        access_routes.append((access,m.call(0x4340a8c0,access)))
    if access_routes!=[(0,1),(1,1),(2,0)]:
        raise AssertionError('Unexpected access configuration')

    # Positive control: real original dispatch must reach the physical driver's
    # entry. Stop there, before running any driver or touching hardware.
    reached=[]
    def tripwire(u,address,size,user):
        reached.append(address);m.ret(0)
    handles=[m.u.hook_add(UC_HOOK_CODE,tripwire,begin=p,end=p) for p in callbacks]
    for slot in range(12):
        before=len(reached);m.call(0x433f6a44,slot)
        if len(reached)!=before+1 or reached[-1]!=m.read32(TABLE+STRIDE+0x1c):
            raise AssertionError('Positive control missed physical driver dispatch')

    # Null every callback in these two rows, in emulator RAM only. Preserve the
    # exact original bytes for restoration. A successful return is insufficient.
    m.u.mem_write(TABLE,b'\0'*(2*STRIDE))
    start=len(reached);checks=0
    for slot in range(12):
        for entry in (0x433f6a44,0x433f6ab4):
            if m.call(entry,slot)!=0:raise AssertionError('Null callback return changed')
            if bytes(m.u.mem_read(SELECTOR,2))!=b'\x05\xff':
                raise AssertionError('Dispatch selector not restored')
            checks+=1
    for access,_ in access_routes:
        for entry in (0x433f67d0,0x433f6b24):
            if m.call(entry,access)!=0:raise AssertionError('Null access callback failed')
            checks+=1

    # Native request records have 40-byte stride, a nonzero word at +0 and a
    # pending status at +4. The original predicate still reports pending after
    # both polling and result collection when the callback is simply removed.
    jobs=bytearray(b'\xa5'*(channels*40))
    for i in range(channels):
        struct.pack_into('<I',jobs,i*40,1);jobs[i*40+4]=0
    m.u.mem_write(OUT,bytes(jobs));m.u.mem_write(OUT+0x400,b'\xa5'*12)
    if m.call(0x433f6cb4,OUT,0)!=0 or m.call(0x433f6bf0,OUT,OUT+0x400)!=0:
        raise AssertionError('Null job dispatcher result changed')
    pending=[m.call(0x433f6c90,OUT+i*40) for i in range(channels)]
    if pending!=[1]*channels or bytes(m.u.mem_read(OUT,len(jobs)))!=jobs:
        raise AssertionError('Expected pending-job counterexample no longer reproduces')
    if bytes(m.u.mem_read(OUT+0x400,12))!=b'\xa5'*12:
        raise AssertionError('Expected untouched result buffer changed')
    if len(reached)!=start:raise AssertionError('Disabled dispatch reached a physical driver')
    m.u.mem_write(TABLE,original)
    before=len(reached);m.call(0x433f6a44,0)
    if len(reached)!=before+1:raise AssertionError('Restoring original dispatch failed')
    for handle in handles:m.u.hook_del(handle)
    report={
        'scope':'Native ARM dispatch boundary experiment in emulator RAM only',
        'dispatch_table':hex(TABLE),'row_bytes':STRIDE,'ink_routes':routes,
        'access_routes':access_routes,'positive_physical_dispatch_controls':12,
        'null_callback_dispatch_cases':checks,'physical_callbacks_during_null_dispatch':0,
        'pending_jobs_after_null_poll':pending,'null_result_buffer_untouched':True,
        'original_dispatch_restored':True,
        'conclusion':'Null callbacks suppress tested driver calls but leave requests pending and results uninitialized; a job completion/result adapter is required.',
        'complete_virtual_job_adapter_implemented':False,
        'all_hardware_paths_proven_unreachable':False,
        'physical_printer_tested':False,
    }
    (ROOT/'analysis/native-dispatch-boundary-results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
