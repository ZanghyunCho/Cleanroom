"""Upper native mirror transfers with the original NV API bound to the core.

Unknown mirror fields are RAM metadata, not a persistent full cartridge image.
"""
import json
import struct
import tempfile
import time
from pathlib import Path
from probe_native_nv import NvMachine
from probe_compiled_bindings import CompiledMachine
from probe_arm_integration import ROOT,CTX,CAPS,OUT,CAPACITY,NATIVE_MIRROR
from unicorn import UC_HOOK_CODE

DIRTY=0x437c6f40
READ=0x43400c3c
WRITES=(0x434006ec,0x43400dec,0x43400f18)

def main():
    start=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='p7500-data-') as tmp:
        paths=[Path(tmp)/f'bank-{i}' for i in range(2)]
        for path in paths:path.write_bytes(b'\xff'*128)
        m=NvMachine(paths)
        if m.call('vr_format_empty',CTX,CAPS)!=0:raise AssertionError('Native NV format failed')
        m.install();entered=[]
        def forbidden(u,a,size,user):
            entered.append(a);raise AssertionError(('Virtual data path entered chip transport',hex(a)))
        # Detect ASIC operations, GF/MR bit-banging and EPC transactions, beyond
        # just the driver callback table tested by the status-job probe.
        m.u.hook_add(UC_HOOK_CODE,forbidden,begin=0x433f7af8,end=0x433fd0a3)
        m.u.hook_add(UC_HOOK_CODE,forbidden,begin=0x43628820,end=0x43629d20)
        reads=0;writes=0;wrapper_cases=0
        for slot in range(12):
            mirror=NATIVE_MIRROR+slot*192;dirty=DIRTY+slot*96
            m.call(0x433ffe50,slot,CAPACITY*91//100)
            m.call(0x4340e5c8,m.call(0x4340a9f8,slot))
            m.call(0x4340e6a0,m.call(0x4340a9f8,slot))
            identity=m.native_identity(slot)
            good=bytes(m.u.mem_read(mirror,192));before=m.info(slot)
            # Serial/vendor are confirmed words 49..53 and 57..59. Corrupt them
            # in the native view and check that only the read prefix is repaired.
            stale=bytearray(good)
            for byte in (*range(98,108),*range(114,118),119):stale[byte]=0
            for words in range(97):
                m.u.mem_write(mirror,bytes(stale));m.u.mem_write(dirty,b'\xa5'*96)
                if m.call(READ,slot,words)!=0:raise AssertionError('Virtual prefix read failed')
                if bytes(m.u.mem_read(mirror,192))!=good[:words*2]+bytes(stale[words*2:]):
                    raise AssertionError(('Read changed unknown/out-of-prefix words',slot,words))
                if bytes(m.u.mem_read(dirty,96))!=b'\xa5'*96:
                    raise AssertionError('Read cleared pending native writes')
                reads+=1
            for entry in WRITES:
                for keep in (0,1):
                    m.u.mem_write(mirror,bytes(stale));m.u.mem_write(dirty,b'\x01'*96)
                    if m.call(entry,slot,keep)!=0:raise AssertionError('Virtual RAM mirror flush failed')
                    if bytes(m.u.mem_read(mirror,192))!=good:raise AssertionError('Flush lost owner identity or unknown RAM metadata')
                    if bytes(m.u.mem_read(dirty,96))!=bytes([keep]*96):
                        raise AssertionError('Native dirty-flag contract changed')
                    if m.info(slot)!=before:raise AssertionError('Data transfer changed durable usage/generation')
                    writes+=1
            # Unmodified native recovery wrapper flushes and clears its flag.
            m.call(0x43402f2c,slot,1)
            if m.call(0x434007a8,slot)!=0 or m.call(0x43402f20,slot)!=0:
                raise AssertionError('Native recovery wrapper rejected virtual flush')
            if m.native_identity(slot)!=identity:raise AssertionError('Native wrapper replaced owner serial')
            wrapper_cases+=1
        expected=[m.info(s) for s in range(13)]
        reboot=NvMachine(paths);reboot.install()
        for s in range(12):
            if reboot.call(READ,s,96)!=0 or reboot.native_identity(s)[0]!=expected[s]['serial']:
                raise AssertionError('Read failed to expose NV-restored generation')
        m.fail_completion=7;m.call(0x433ffe50,0,1)
        old=bytes(m.u.mem_read(NATIVE_MIRROR,192));m.u.mem_write(DIRTY,b'\x01'*96)
        for entry,args in ((READ,(0,96)),*[(e,(0,0)) for e in WRITES]):
            if m.call(entry,*args)!=1:raise AssertionError('Faulted transfer returned success')
            if bytes(m.u.mem_read(NATIVE_MIRROR,192))!=old or bytes(m.u.mem_read(DIRTY,96))!=b'\x01'*96:
                raise AssertionError('Faulted transfer mutated mirror/dirty flags')
        if entered:raise AssertionError('Unexpected physical transport')
        bad_cases=((READ,(12,1)),(READ,(0,97)),(WRITES[0],(12,0)),
                   (WRITES[1],(0,2)),(WRITES[2],(0,2)))
        for entry,args in bad_cases:
            bad=CompiledMachine();bad.format();bad.install()
            original=bytes(bad.u.mem_read(NATIVE_MIRROR,12*192))
            if bad.call(entry,*args)!=1 or bad.faults!=[-4]:
                raise AssertionError('Invalid native data request accepted')
            if bytes(bad.u.mem_read(NATIVE_MIRROR,12*192))!=original:
                raise AssertionError('Invalid native data request changed RAM metadata')
        report={'scope':'Compiled upper ink RAM mirror reads/flushes, using NV-backed durable owner state',
                'partial_read_cases_passed':reads,'flush_mode_cases_passed':writes,
                'unmodified_recovery_wrappers_passed':wrapper_cases,
                'restored_owner_identity_reads_passed':12,'faulted_transfer_cases_passed':4,
                'invalid_data_request_cases_passed':len(bad_cases),
                'physical_chip_transport_entries':len(entered),
                'unknown_mirror_metadata_scope':'Preserved native RAM view; not persisted as a full chip image',
                'full_chip_communication_virtualized':False,'physical_printer_tested':False,
                'elapsed_seconds':round(time.monotonic()-start,3)}
    (ROOT/'analysis/virtual-ink-data-results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
