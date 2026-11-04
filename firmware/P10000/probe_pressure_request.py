"""Trace native supply-driver dispatch, with motion and CSIC reply fixtures.

Motor requests are intercepted: passing this probe is not physical pump testing.
"""
from pathlib import Path
import hashlib
import json
import struct
from native import UC_HOOK_CODE, UC_ARM_REG_R0
from probe_ink_sensor_and_genuine import machine

ROOT = Path(__file__).resolve().parent
ENTRY = 0x43b9af90
CONTROL = 0x43ea0e08
STOP_FLAGS = 0x43e86018


def run(module):
    m, original = machine()
    assert module[0x9af90:0x9b2e4] == original[0x9af90:0x9b2e4]
    m.u.mem_write(0x43b00000, module)
    callback, selected = 0x430f0000, 0x43050000
    events = []
    fixture = {'end': 0}

    def motion_hook(name):
        def hook(u, address, size, context):
            events.append({'event': name, 'r0': u.reg_read(UC_ARM_REG_R0)})
            m.return_value(0)
        return hook

    for pc, name in [(callback, 'callback'), (0x43b96764, 'motion_dispatch'),
                     (0x43b934a0, 'motion_wait')]:
        m.u.hook_add(UC_HOOK_CODE, motion_hook(name), begin=pc, end=pc)

    def detect(u, address, size, context):
        events.append({'event': 'CSIC_end_query', 'fixture_value': fixture['end']})
        u.mem_write(u.reg_read(UC_ARM_REG_R0) + 20,
                    struct.pack('<10H', *([fixture['end']] * 10)))
        m.return_value(1)

    m.u.hook_add(UC_HOOK_CODE, detect, begin=0x43b33e48, end=0x43b33e48)
    cases = []
    for count in [0, 1, 2]:
        for stopped in [False, True]:
            for end in [0, 1]:
                m.u.mem_write(CONTROL, bytes(0x90))
                m.write32(CONTROL + 0x38, callback)
                m.write32(STOP_FLAGS, 0x100 if stopped else 0)
                m.u.mem_write(selected, struct.pack('<10H', *([1] * 10)))
                fixture['end'] = end
                events.clear()
                # r0: enable post-motion end detection; r2: repetition count;
                # r3: product-operation branch. All are explicit test inputs.
                m.call(ENTRY, 1, selected, count, 0, count=100000)
                moving = count > 0 and not stopped
                repetitions = (1 if end else count) if moving else 0
                assert sum(e['event'] == 'motion_dispatch' for e in events) == 2 * repetitions
                assert sum(e['event'] == 'CSIC_end_query' for e in events) == repetitions
                if moving:
                    first_motion = next(i for i, e in enumerate(events)
                                        if e['event'] == 'motion_dispatch')
                    first_query = next(i for i, e in enumerate(events)
                                       if e['event'] == 'CSIC_end_query')
                    assert first_motion < first_query
                else:
                    assert not events
                cases.append({'requested_repetitions': count, 'stop_bit_0x100': stopped,
                              'CSIC_end_reply_fixture': end, 'events': list(events)})
    return {'module_sha256': hashlib.sha256(module).hexdigest(),
            'driver_matches_original': True, 'cases': cases}


if __name__ == '__main__':
    sources = {'original': ROOT / 'inputs/main-block-3.bin',
               'V2': ROOT / 'build/region-maintenance-module.bin',
               'V4.5': ROOT / 'build/ils-diagnostic-module.bin'}
    results = {name: run(path.read_bytes()) for name, path in sources.items()}
    assert results['original']['cases'] == results['V2']['cases'] == results['V4.5']['cases']
    report = {'entry': hex(ENTRY), 'results': results,
              'observed_first_motion_precedes_CSIC_end_query': True,
              'zero_count_or_stop_bit_prevents_motion_dispatch_in_this_path': True,
              'fixtures': ['Selected mask contains ten ones; driver mode input is zero',
                           'Driver control structure cleared and callback pointer supplied',
                           'Repetition count and subsystem stop word set explicitly',
                           'Motion dispatch/wait and callback intercepted, returning zero',
                           'CSIC API reply replaced by explicit all-zero/all-one end flags'],
              'actual_request_arguments_and_stop_word_unknown': True,
              'not_a_complete_print_cleaning_or_pump_hardware_test': True,
              'does_not_identify_regression_root_cause': True}
    destination = ROOT / 'validation/pressure-request-trace.json'
    destination.write_text(json.dumps(report, indent=2) + '\n')
    print(f'36 native pressure-driver trace cases passed; report: {destination}')
