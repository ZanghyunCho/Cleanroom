"""Verify the supplied chips and reconstruct the unmodified two-byte-lane image."""
import hashlib
import json
from pathlib import Path
import zipfile
import sys

ROOT = Path(__file__).resolve().parent
EXPECTED = {
    'IC3.BIN': '894056f5b002e75c26d636b269910a8f48eb1a95762e849f8fda7339e08914ed',
    'IC4.BIN': '4403822b3eb8e7a2fafb71bbc1f989377908334f81a0e02c70532a1c4ccf8b7e',
}

def main(archive):
    parts = []
    with zipfile.ZipFile(archive) as z:
        for name, expected in EXPECTED.items():
            data = z.read(name)  # ZIP CRC is checked by ZipFile.
            if len(data) != 64 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != expected:
                raise ValueError(f'Original integrity check failed: {name}')
            parts.append(data)
    merged = bytearray(128 * 1024 * 1024)
    for chip, start in zip(parts, (0, 2)):
        merged[start::4] = chip[0::2]
        merged[start + 1::4] = chip[1::2]
    for chip, start in zip(parts, (0, 2)):
        recovered = bytearray(len(chip))
        recovered[0::2] = merged[start::4]
        recovered[1::2] = merged[start + 1::4]
        if recovered != chip:
            raise ValueError('Lane round trip failed')
    original = ROOT / 'original'
    original.mkdir(exist_ok=True)
    for name, data in [*zip(EXPECTED, parts), ('merged.bin', merged)]:
        path = original / name
        if path.exists() and path.read_bytes() != data:
            raise ValueError(f'Refusing to overwrite different data: {path}')
        if not path.exists():
            path.write_bytes(data)
    print(json.dumps({'original_sha256': EXPECTED, 'merged_sha256': hashlib.sha256(merged).hexdigest(),
                      'lane_round_trip': True, 'firmware_modified': False}, indent=2))

if __name__ == '__main__':
    main(sys.argv[1])
