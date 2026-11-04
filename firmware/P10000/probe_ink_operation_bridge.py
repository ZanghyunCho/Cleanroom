"""Native CSIC replies -> native API -> IKS availability refresh and operation gate.

Two CPU instances replace only the RTOS message transport. This is not a real
printer boot, scheduler, pressure controller, or physical chip emulation.
"""
from pathlib import Path
import hashlib
import json
import struct
from native import UC_HOOK_CODE, UC_ARM_REG_R0, UC_ARM_REG_R1
from probe_ink_sensor_and_genuine import machine

ROOT = Path(__file__).resolve().parent


def run(module):
    def make():
        m, original = machine()
        m.u.mem_write(0x43b00000, module)
        m.u.mem_write(0x43e00000, original[0x2454e8:0x2764ac])
        m.u.mem_write(0, original[0x236590:0x244598])
        m.u.mem_map(0x3fffc000, 0x4000)
        m.u.mem_write(0x3fffc000, original[0x244598:0x2454e8])
        m.u.mem_write(0x7ff029b3, b'\4')
        return m

    service, client = make(), make()
    buffer, allocation = 0x430c0000, 0x430d0000
    completed, errors, requests = [], [], []
    presence = {'absent_fixture': False}

    def complete(u, address, size, context):
        completed.append(bytes(u.mem_read(u.reg_read(UC_ARM_REG_R0), 128)))
        service.return_value(0)

    def service_allocate(u, address, size, context):
        service.write32(u.reg_read(UC_ARM_REG_R1), allocation)
        u.mem_write(allocation, bytes(1024))
        service.return_value(0)

    def service_send(u, address, size, context):
        # Status notifications are deliberately not delivered to JCT in this probe.
        service.return_value(0)

    def presence_hook(u, address, size, context):
        if presence['absent_fixture']:
            u.mem_write(u.reg_read(UC_ARM_REG_R0), bytes(20))
            service.return_value(1)

    for pc, hook in [
        (0x43ba50c0, complete), (0x43b0e1fc, service_allocate),
        (0x43b0e214, service_send),
        (0x43b0e204, lambda u, a, n, x: service.return_value(0)),
        (0x43b2dab4, lambda u, a, n, x: service.return_value(0)),
        (0x43b18a74, lambda u, a, n, x: service.return_value(0)),
        (0x43b1b328, presence_hook),
    ]:
        service.u.hook_add(UC_HOOK_CODE, hook, begin=pc, end=pc)
    # Actual patched ink/maintenance power functions; full startup is not executed.
    assert service.call(0x43b1ce48) == 1
    assert service.call(0x43b1c230, 0) == 1
    assert service.call(0x43b1c230, 1) == 1

    def allocate(u, address, size, context):
        client.write32(u.reg_read(UC_ARM_REG_R1), buffer)
        u.mem_write(buffer, bytes(1024))
        client.return_value(0)

    def send(u, address, size, context):
        request = bytes(u.mem_read(u.reg_read(UC_ARM_REG_R1), 128))
        command = struct.unpack_from('<I', request, 0x14)[0]
        handler = {0xbc000013: 0x43b15a60, 0xbc000014: 0x43b158a4}[command]
        service.u.mem_write(buffer, request)
        completed.clear()
        service.call(handler, buffer, count=100000)
        assert len(completed) == 1
        reply = completed[0]
        requests.append({'command': hex(command), 'completion_count': len(completed),
                         'flags': list(struct.unpack_from(
                             '<12H' if command == 0xbc000013 else '<10H', reply, 0x20))})
        u.mem_write(buffer, reply)
        client.return_value(0)

    def receive(u, address, size, context):
        client.write32(u.reg_read(UC_ARM_REG_R1), buffer)
        client.return_value(0)

    def error(u, address, size, context):
        errors.append(u.reg_read(UC_ARM_REG_R0))
        client.return_value(0)

    for pc, hook in [
        (0x43b0e1fc, allocate), (0x43b0e214, send), (0x43b0e28c, receive),
        (0x43b0e204, lambda u, a, n, x: client.return_value(0)),
        (0x43c33948, lambda u, a, n, x: client.return_value(0)),
        (0x43bb62d0, error),
    ]:
        client.u.hook_add(UC_HOOK_CODE, hook, begin=pc, end=pc)
    # Explicit substitute for IKS initialization: all slots selected, identity map.
    for slot in range(10):
        client.write32(0x43e7b09c + 24 * slot + 12, 0x43050000 + slot)
        client.write32(0x43e7b18c + 4 * slot, 0x43051000 + 4 * slot)
        client.write32(0x43051000 + 4 * slot, slot)
    client.u.mem_write(0x43050000, bytes([1] * 10))
    cases = []
    for counter in range(6):
        for absent in [False, True]:
            presence['absent_fixture'] = absent
            errors.clear()
            requests.clear()
            client.u.mem_write(0x7ff029c2, bytes([counter]))
            client.call(0x43c2ff58, 0x43060000, count=100000)
            allowed = struct.unpack('<H', client.u.mem_read(0x43060028, 2))[0]
            assert allowed == int(counter == 0 or absent)
            assert errors == ([] if allowed else [0x23, 0x23])
            assert requests[0]['flags'] == [1] * 12
            if counter:
                assert requests[1]['flags'] == [0 if absent else 1] * 10
            cases.append({'cleaning_discharge_counter_fixture': counter,
                          'presence_response': 'all_absent_fixture' if absent else 'unaltered_V4.5',
                          'operation_allowed': allowed, 'error_sink_values': list(errors),
                          'requests': list(requests)})
    return {'module_sha256': hashlib.sha256(module).hexdigest(), 'cases': cases,
            'fixtures': ['Two CPU instances with original main scatter-copy data/code',
                         'RTOS allocation/send/receive/free/completion replaced synchronously',
                         'NV/date housekeeping at 0x43b2dab4 and 0x43b18a74 stubbed',
                         'JCT status notifications and final IKS reply delivery not executed',
                         'Explicit selected-slot pointers and identity slot mapping',
                         'Counter injected at 0x7ff029c2; real printer value unknown',
                         'Absent cases replace only presence query with ten zeros'],
            'not_a_V2_vs_V4_full_printer_comparison': True,
            'does_not_identify_actual_regression_root_cause': True,
            'physical_printer_or_pump_not_tested': True}


if __name__ == '__main__':
    report = run((ROOT / 'build/ils-diagnostic-module.bin').read_bytes())
    destination = ROOT / 'validation/ink-operation-bridge.json'
    destination.write_text(json.dumps(report, indent=2) + '\n')
    print(f'12 native response/API/IKS cases passed; report: {destination}')
