"""Build non-flashable V2-based modules for hardware regression isolation.

These retain physical ink handling. They do NOT implement cartridge absence
emulation, and they are not verified fixes. No EFU is produced by this script.
"""
from pathlib import Path
import hashlib
import json
import os
import struct
import subprocess
from probe_ink_sensor_and_genuine import machine

ROOT = Path(__file__).resolve().parent
RANGES = {'.ink_info': (0x1fef4, 0x1ffe4), '.ink_status': (0x20014, 0x200b0)}


def sections():
    env = os.environ.copy()
    env['ZIG_GLOBAL_CACHE_DIR'] = str(ROOT / 'build/zig-global-cache')
    env['ZIG_LOCAL_CACHE_DIR'] = str(ROOT / 'build/zig-local-cache')
    command = [str(ROOT.parent / 'P7500/tools/ziglang/zig'), 'cc',
               '-target', 'arm-freestanding-eabi', '-mcpu=arm926ej_s',
               '-mfloat-abi=soft', '-marm', '-Os', '-ffreestanding', '-fno-builtin',
               '-fno-stack-protector', '-fno-unwind-tables',
               '-fno-asynchronous-unwind-tables', '-nostdlib',
               '-Wl,-T,patches/ink_normalizers_diagnostic.ld',
               '-Wl,--entry=ink_status', '-Wl,--build-id=none',
               'patches/ink_virtual.c', '-o', 'build/ink-normalizers-diagnostic.elf']
    subprocess.run(command, cwd=ROOT, env=env, check=True)
    raw = (ROOT / 'build/ink-normalizers-diagnostic.elf').read_bytes()
    offset = struct.unpack_from('<I', raw, 32)[0]
    size, count, string_table = struct.unpack_from('<HHH', raw, 46)
    headers = [struct.unpack_from('<10I', raw, offset + i * size) for i in range(count)]
    h = headers[string_table]
    names = raw[h[4]:h[4] + h[5]]
    result = {}
    for h in headers:
        if not h[2] & 2 or not h[5]:
            continue
        name = names[h[0]:names.find(b'\0', h[0])].decode()
        assert name in RANGES, name
        lo, hi = RANGES[name]
        assert h[3] == 0x43b00000 + lo and h[5] <= hi - lo
        result[name] = raw[h[4]:h[4] + h[5]]
    assert set(result) == set(RANGES)
    return result


def runtime(module, status_normalized, info_normalized):
    m, _ = machine()
    m.u.mem_write(0x43b00000, module)
    status_address, info_address = 0x43010000, 0x43011000
    checks = []
    # Exercise normal, absent, end and other native status values. This tests the
    # cache contract; it does not model transport, the RTOS or supply mechanics.
    for state in [0, 1, 2, 4, 5, 6, 12]:
        status = bytearray(120)
        info = bytearray(160)
        for slot in range(10):
            struct.pack_into('<BB2xIH', status, 12 * slot, state, 37, 123456789, 1)
            struct.pack_into('<5H5B', info, 16 * slot,
                             700, 1, 1, 1, 1, 3, 4, 5, 6, 7)
        m.u.mem_write(status_address, bytes(status))
        m.u.mem_write(info_address, bytes(info))
        m.u.mem_write(0x43e5d514, bytes(120))
        m.u.mem_write(0x43e5d58c, bytes(160))
        m.call(0x43b20014, status_address)
        m.call(0x43b1fef4, info_address)
        for slot in range(10):
            observed = struct.unpack('<BB2xIH', m.u.mem_read(0x43e5d514 + 12 * slot, 10))
            expected = (0, 100, 680000000, 0) if status_normalized else (state, 37, 123456789, 1)
            assert observed == expected, (slot, observed, expected)
            observed_info = bytes(m.u.mem_read(0x43e5d58c + 16 * slot, 15))
            expected_info = bytearray(info[16 * slot:16 * slot + 15])
            if info_normalized:
                for i in [4, 5, 6, 7, 10]:
                    expected_info[i] = 0
            assert observed_info == expected_info
        assert bytes(m.u.mem_read(status_address, 120)) == status
        assert bytes(m.u.mem_read(info_address, 160)) == info
        checks.append({'input_state': state, 'slots_checked': 10,
                       'status_normalized': status_normalized,
                       'info_normalized': info_normalized, 'input_buffers_preserved': True})
    return checks


def build():
    baseline = (ROOT / 'build/region-maintenance-module.bin').read_bytes()
    anchor = json.loads((ROOT / 'validation/region-maintenance-patches.json').read_text())
    assert hashlib.sha256(baseline).hexdigest() == anchor['patched_sha256']
    compiled = sections()
    variants = {'V2_BASELINE': [], 'V2_STATUS_ONLY': ['.ink_status'],
                'V2_INFO_ONLY': ['.ink_info'],
                'V2_STATUS_AND_INFO': ['.ink_status', '.ink_info']}
    report = {'classification': 'LOCAL NON-FLASHABLE DIAGNOSTIC MODULES; NOT VERIFIED FIXES',
              'baseline_sha256': hashlib.sha256(baseline).hexdigest(), 'variants': {},
              'physical_ink_presence_and_transport_retained': True,
              'ILS_getter_retained_from_V2': True,
              'all_V2_bytes_except_selected_two_cache_setters_retained': True,
              'normalizers_affect_internal_caches_not_just_display': True,
              'no_forced_motor_or_stop_bit_changes': True,
              'full_print_or_physical_printer_not_tested': True,
              'EFU_not_created': True}
    for name, selected in variants.items():
        out = bytearray(baseline)
        edits = []
        for section in selected:
            lo, hi = RANGES[section]
            data = compiled[section]
            out[lo:lo + len(data)] = data
            edits.append({'section': section, 'offset': hex(lo), 'bytes': len(data)})
        # Prove all bytes outside the selected normalizer functions equal V2.
        cursor = 0
        for lo, hi in sorted(RANGES[s] for s in selected):
            assert out[cursor:lo] == baseline[cursor:lo]
            cursor = hi
        assert out[cursor:] == baseline[cursor:]
        assert len(out) == len(baseline)
        checks = runtime(bytes(out), '.ink_status' in selected, '.ink_info' in selected)
        filename = ROOT / 'build' / (name + '_MODULE_NOT_FLASHABLE.bin')
        filename.write_bytes(out)
        report['variants'][name] = {'file': filename.name,
                                    'sha256': hashlib.sha256(out).hexdigest(),
                                    'changes': edits, 'native_ARM_cases': checks,
                                    'other_bytes_identical_to_V2': True}
    destination = ROOT / 'validation/control-isolation-build.json'
    destination.write_text(json.dumps(report, indent=2) + '\n')
    print(f'Built 3 diagnostic variants plus baseline; 280 slot cases passed: {destination}')
    return report


if __name__ == '__main__':
    build()
