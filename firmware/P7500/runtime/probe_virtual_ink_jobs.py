"""Exercise compiled upper ink jobs through original ARM callers.

The normal result bytes are compared with original result decoders supplied
completed, zero-error records. Physical driver callbacks are trapped, not mocked
as successful chip exchanges. This covers two jobs, not the full CSIC subsystem.
"""
import json
import struct
import time
from probe_compiled_bindings import CompiledMachine, BINDINGS
from probe_arm_integration import ROOT, OUT, CTX, CAPACITY
from unicorn import UC_HOOK_CODE

MASK=OUT+0x500
RESULT=OUT+0x600
TABLE=0x4365c444
SELECTOR=0x43705f40
CHECK=0x433f6e90
STATUS=0x433f71fc


def main():
    start=time.monotonic();m=CompiledMachine();m.format();m.install()
    references={}
    # These original decoders never invoke a chip transaction. Feed completed
    # zero-error records and let the actual ARM code establish the result ABI.
    for access in (0,1):
        for kind,mode in (('check',0),('status',0),('status',1)):
            m.u.mem_write(SELECTOR,bytes([access,0xff]))
            record=bytearray(40);struct.pack_into('<I',record,0,1)
            m.u.mem_write(OUT,bytes(record));m.u.mem_write(RESULT,b'\xa5'*12)
            args=(OUT,RESULT) if kind=='check' else (mode,OUT,RESULT)
            decoder=0x433f823c if kind=='check' else 0x433f8584
            if m.call(decoder,*args)!=0 or m.read32(OUT)!=0:
                raise AssertionError('Native reference decoder did not complete')
            references[(kind,mode,access)]=bytes(m.u.mem_read(RESULT,12))
    m.u.mem_write(SELECTOR,b'\x05\xff')

    reached=[]
    def forbidden(u,address,size,user):
        reached.append(address)
        raise AssertionError(('Virtual ink job reached physical callback',hex(address)))
    callbacks=set(struct.unpack('<58I',m.u.mem_read(TABLE,232)))-{0}
    for address in callbacks:m.u.hook_add(UC_HOOK_CODE,forbidden,begin=address,end=address)
    cases=0
    for bits in range(1<<12):
        # Nonboolean selection values must also count as selected.
        selections=[0x80000000 if bits&(1<<s) else 0 for s in range(12)]
        m.u.mem_write(MASK,struct.pack('<12I',*selections))
        groups=[g for g in (0,1) if bits&(0x3f<<(g*6))]
        for kind,mode in (('check',0),('status',0),('status',1)):
            expected=bytearray(b'\xa5'*12)
            for access in groups:
                native=references[(kind,mode,access)]
                expected[access*6:access*6+6]=native[access*6:access*6+6]
            m.u.mem_write(RESULT,b'\xa5'*12)
            args=(MASK,RESULT) if kind=='check' else (mode,MASK,RESULT)
            if m.call(CHECK if kind=='check' else STATUS,*args)!=0:
                raise AssertionError(('Job failed',bits,kind,mode))
            if bytes(m.u.mem_read(RESULT,12))!=expected:
                raise AssertionError(('Native result ABI mismatch',bits,kind,mode))
            if bytes(m.u.mem_read(SELECTOR,2))!=b'\x05\xff':
                raise AssertionError('Upper virtual job changed physical driver selector')
            cases+=1
    # NULL mask selects all; a mask/result alias must use the original mask.
    for kind,mode in (('check',0),('status',0),('status',1)):
        normal=0 if kind=='check' else 2
        args=(0,RESULT) if kind=='check' else (mode,0,RESULT)
        if m.call(CHECK if kind=='check' else STATUS,*args)!=0:
            raise AssertionError('NULL selection mask failed')
        if bytes(m.u.mem_read(RESULT,12))!=bytes([normal]*12):
            raise AssertionError('NULL mask did not fill all slots')
        m.u.mem_write(MASK,struct.pack('<12I',1,*([0]*11)))
        args=(MASK,MASK) if kind=='check' else (mode,MASK,MASK)
        if m.call(CHECK if kind=='check' else STATUS,*args)!=0:
            raise AssertionError('Aliased selection failed')
        if bytes(m.u.mem_read(MASK,12))!=bytes([normal]*6+[0]*6):
            raise AssertionError('Aliased mask was overwritten before snapshot')
    # Actual unmodified upper wrappers parse results and combine the two jobs.
    m.u.mem_write(MASK,struct.pack('<12I',*([1]*12)))
    for entry in (0x433fef44,0x433fee4c):
        if m.call(entry,MASK,RESULT)!=0:
            raise AssertionError(('Original wrapper rejected virtual job',hex(entry)))
    combined_cases=[0,0xfff,0x555,0xaaa]+[1<<s for s in range(12)]
    for bits in combined_cases:
        selected=[int(bool(bits&(1<<s))) for s in range(12)]
        m.u.mem_write(MASK,struct.pack('<12I',*selected))
        m.u.mem_write(RESULT-4,b'HEAD'+b'\xa5'*48+b'TAIL')
        if m.call(0x433fef6c,MASK,RESULT)!=0:
            raise AssertionError('Original combined check/status wrapper failed')
        if struct.unpack('<12I',m.u.mem_read(RESULT,48))!=tuple(selected):
            raise AssertionError('Combined native wrapper selected the wrong usable slots')
        if bytes(m.u.mem_read(RESULT-4,4))!=b'HEAD' or bytes(m.u.mem_read(RESULT+48,4))!=b'TAIL':
            raise AssertionError('Combined native wrapper overwrote result boundaries')
    m.u.mem_write(MASK,struct.pack('<12I',*([1]*12)))
    # Queries must neither consume ink nor reset a low cartridge. Only its cover
    # transaction may advance generation. Verify restored state as well.
    m.call(0x433ffe50,0,CAPACITY*91//100)
    before=m.info(0)
    for entry,args in ((CHECK,(MASK,RESULT)),(STATUS,(0,MASK,RESULT)),(STATUS,(1,MASK,RESULT))):
        if m.call(entry,*args)!=0 or m.info(0)!=before:
            raise AssertionError('Query changed virtual identity/usage')
    m.call(0x4340e5c8,1);m.call(0x4340e6a0,1)
    if m.info(0)['generation']!=1:raise AssertionError('Cover transaction no longer advances identity')
    reboot=CompiledMachine(bytes(m.flash));reboot.install()
    if reboot.info(0)!=m.info(0) or reboot.call(CHECK,0,RESULT)!=0:
        raise AssertionError('Restored virtual state unavailable to upper query')
    # Faulted storage must not publish healthy results or fall back to hardware.
    m.cut=0;m.mutations=0;m.call(0x433ffe50,0,1)
    for entry,args in ((CHECK,(MASK,RESULT)),(STATUS,(0,MASK,RESULT)),(STATUS,(1,MASK,RESULT))):
        m.u.mem_write(RESULT,b'\xa5'*12)
        if m.call(entry,*args)!=1 or bytes(m.u.mem_read(RESULT,12))!=b'\x05'*12:
            raise AssertionError('Faulted job reported healthy status')
    for entry in (0x433fef44,0x433fee4c):
        if m.call(entry,MASK,RESULT)!=1:
            raise AssertionError('Original wrapper swallowed virtual job failure')
    if m.call(0x433fef6c,MASK,RESULT)!=1 or bytes(m.u.mem_read(RESULT,48))!=b'\0'*48:
        raise AssertionError('Faulted combined wrapper marked slots usable')
    if m.faults!=[-3] or reached:raise AssertionError('Unexpected faults or hardware dispatch')
    # Validate rejected binding routes without destroying an existing attachment.
    invalid=CompiledMachine();invalid.format();invalid.install()
    stub=0x47000600
    invalid.u.mem_write(stub,struct.pack('<2I',0xe3a00020,0xe12fff1e))
    invalid.u.mem_write(BINDINGS+36,struct.pack('<I',stub))
    if invalid.call('vr_native_attach',CTX,BINDINGS)!=0xfffffffc:
        raise AssertionError('Out-of-range access route accepted')
    if invalid.call(CHECK,0,RESULT)!=0:raise AssertionError('Rejected attachment damaged previous routes')
    for entry,args in ((CHECK,(0,0)),(STATUS,(0,0,0)),(STATUS,(2,0,RESULT))):
        bad=CompiledMachine();bad.format();bad.install()
        bad.u.mem_write(RESULT,b'\xa5'*12)
        if bad.call(entry,*args)!=1 or bad.faults!=[-4]:
            raise AssertionError('Invalid job arguments were not rejected')
        if bytes(bad.u.mem_read(RESULT,12))!=b'\xa5'*12:
            raise AssertionError('Rejected job changed result storage')
    report={
        'scope':'Two compiled upper ink jobs, patched ARM entries and original upper callers',
        'selection_mode_cases_passed':cases,'original_decoder_reference_cases':len(references),
        'null_mask_and_alias_cases_passed':6,'original_upper_wrappers_passed':3,
        'combined_native_selection_cases':len(combined_cases),
        'invalid_job_argument_cases_passed':3,
        'query_preserves_usage_generation':True,
        'cover_generation_and_reboot_passed':True,'faulted_jobs_rejected':3,
        'faulted_original_upper_wrappers_rejected':3,
        'invalid_route_rejected_without_replacing_attachment':True,
        'physical_driver_callbacks_entered':len(reached),
        'native_normal_check_code':0,'native_normal_status_code':2,
        'full_chip_communication_virtualized':False,'native_persistence_backend_bound':False,
        'physical_printer_tested':False,'elapsed_seconds':round(time.monotonic()-start,3),
    }
    (ROOT/'analysis/virtual-ink-job-results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
