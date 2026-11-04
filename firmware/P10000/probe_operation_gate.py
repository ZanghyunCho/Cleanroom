"""Execute the native operation gate with explicit controller-state fixtures.

This tests the consumer of availability state, not its real RTOS producer or pump.
"""
from pathlib import Path
import hashlib
import json
import struct
from native import UC_HOOK_CODE, UC_ARM_REG_R0
from probe_ink_sensor_and_genuine import machine

ROOT = Path(__file__).resolve().parent
GATE = 0x43c28f98


def run(module):
    m, original = machine()
    m.u.mem_write(0x43b00000, module)
    # Main startup scatter-copy: initialized data, not zero-filled substitutes.
    data = original[0x2454e8:0x2454e8 + 0x30fc4]
    assert len(data) == 0x30fc4
    m.u.mem_write(0x43e00000, data)
    # Fixture: all ten slots selected; mode byte zero. No pump hardware modeled.
    for slot in range(10):
        m.write32(0x43e7b09c + 24 * slot + 12, 0x43050000 + slot)
    m.u.mem_write(0x43050000, bytes([1] * 10))
    m.u.mem_write(0x7ff029c2, b'\0')
    errors = []

    def error(u, address, size, context):
        errors.append(u.reg_read(UC_ARM_REG_R0))
        m.return_value(0)

    m.u.hook_add(UC_HOOK_CODE, error, begin=0x43bb62d0, end=0x43bb62d0)
    cases = []
    for bad in [-1] + list(range(12)):
        for slot in range(10):
            m.u.mem_write(0x43e7b09c + 24 * slot + 16,
                          struct.pack('<H', int(slot != bad)))
        m.u.mem_write(0x43e7b098,
                      struct.pack('<HH', int(bad != 10), int(bad != 11)))
        errors.clear()
        result = m.call(GATE, 0x43060000, count=100000)
        allowed = struct.unpack('<H', m.u.mem_read(0x43060000, 2))[0]
        expected_errors = [] if bad == -1 else ([19, 19] if bad < 10 else [23])
        assert result == 1 and allowed == int(bad == -1)
        assert errors == expected_errors
        cases.append({'unavailable_slot': None if bad == -1 else bad,
                      'call_success': result, 'operation_allowed': allowed,
                      'error_sink_values': list(errors)})
    return {'module_sha256': hashlib.sha256(module).hexdigest(), 'cases': cases}


if __name__ == '__main__':
    paths = {'original': ROOT / 'inputs/main-block-3.bin',
             'V2': ROOT / 'build/region-maintenance-module.bin',
             'V4.5': ROOT / 'build/ils-diagnostic-module.bin'}
    results = {name: run(path.read_bytes()) for name, path in paths.items()}
    assert results['original']['cases'] == results['V2']['cases'] == results['V4.5']['cases']
    report = {'gate_address': hex(GATE), 'results': results,
              'identical_results_for_identical_state': True,
              'fixtures': ['Original initialized .data copied from main-module scatter source',
                           'All ten slots selected; mode byte zero',
                           'Availability state injected directly, not obtained from RTOS',
                           'Logging and error sink intercepted'],
              'does_not_identify_real_printer_state_or_root_cause': True,
              'pump_hardware_or_full_job_not_emulated': True}
    destination = ROOT / 'validation/operation-gate-fixtures.json'
    destination.write_text(json.dumps(report, indent=2) + '\n')
    print(f'39 native gate cases passed; report: {destination}')
