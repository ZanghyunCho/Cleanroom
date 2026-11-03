"""Strict reader for the P7500 dump's CROM Huffman/LZ frames.

No undefined Huffman symbols, out-of-window references or truncated literals
are repaired. Decoding must consume all literal bytes and end on a sentinel.
"""
from pathlib import Path
import hashlib
import json
import struct

class FormatError(ValueError):
    pass

class Bits:
    def __init__(self, data):
        self.data, self.pos = data, 0

    def symbol(self, table):
        code = 0
        for n in range(1, 17):
            if self.pos >= len(self.data) * 8:
                raise FormatError('Truncated Huffman stream')
            code = code * 2 + ((self.data[self.pos // 8] >> (7 - self.pos % 8)) & 1)
            self.pos += 1
            if (n, code) in table:
                return table[n, code]
        raise FormatError('Undefined Huffman code')

def decode_frame(data, start):
    if data[start:start+2] != b'\xff\xd8':
        raise FormatError('Missing frame marker')
    length = int.from_bytes(data[start+2:start+6], 'big')
    end = start + length
    if length < 6 or end > len(data):
        raise FormatError('Invalid frame length')
    p = start + 6
    tables, packed, literals, count = {}, None, None, None
    while p < end:
        marker = data[p:p+2]
        size = int.from_bytes(data[p+2:p+4], 'big')
        if size < 2 or p+2+size > end:
            raise FormatError('Invalid marker length')
        header = data[p+4:p+2+size]
        p += 2 + size
        if marker == b'\xff\xc4':
            q = 0
            while q < len(header):
                if q+17 > len(header):
                    raise FormatError('Truncated Huffman table')
                tid = header[q]
                counts = header[q+1:q+17]
                n = sum(counts)
                symbols = header[q+17:q+17+n]
                if len(symbols) != n or len(set(symbols)) != n or tid in tables:
                    raise FormatError('Invalid Huffman symbols')
                table, code, k = {}, 0, 0
                for bits, frequency in enumerate(counts, 1):
                    for _ in range(frequency):
                        if code >= 1 << bits:
                            raise FormatError('Oversubscribed Huffman tree')
                        table[bits, code] = symbols[k]
                        code += 1
                        k += 1
                    code <<= 1
                tables[tid] = table
                q += 17+n
        elif marker == b'\xff\xb1':
            if len(header) < 13 or header[0] != 3 or header[10:13] != b'\x00\x10\x20' or packed is not None:
                raise FormatError('Unsupported scan header')
            size, count = struct.unpack_from('>II', header, 1)
            if header[9] != (-count) % 16 or any(header[13:]) or size % 16:
                raise FormatError('Invalid scan padding metadata')
            if p+size > end:
                raise FormatError('Scan outside frame')
            packed = data[p:p+size]
            p += size
        elif marker == b'\xff\xb2':
            if len(header) != 4 or literals is not None:
                raise FormatError('Invalid literal header')
            size = int.from_bytes(header, 'big')
            if p+size > end:
                raise FormatError('Literals outside frame')
            literals = data[p:p+size]
            p += size
        else:
            raise FormatError(f'Unknown marker {marker.hex()}')
    if packed is None or literals is None or set(tables) != {0xf0, 0xf1, 0xf2}:
        raise FormatError('Incomplete frame')
    bits, output, literal_pos = Bits(packed), bytearray(), 0
    tokens = bytearray()
    for index in range(count):
        length, lo, hi = [bits.symbol(tables[t]) for t in (0xf0, 0xf1, 0xf2)]
        tokens.extend((length, lo, hi))
        distance = lo | (hi << 8)
        if distance:
            if distance > len(output):
                raise FormatError('Back-reference before output')
            for _ in range(length+2):
                output.append(output[-distance])
        elif length == 255:
            if index != count-1 or literal_pos != len(literals):
                raise FormatError('Early sentinel or leftover literals')
            break
        else:
            n = length+1
            if literal_pos+n > len(literals):
                raise FormatError('Truncated literal run')
            output.extend(literals[literal_pos:literal_pos+n])
            literal_pos += n
        if len(output) > 128*1024*1024:
            raise FormatError('Decoded frame exceeds physical dump size')
    else:
        raise FormatError('Missing sentinel')
    remaining_bits = len(packed)*8-bits.pos
    if remaining_bits > 256:
        raise FormatError('Excessive trailing scan padding')
    for bit in range(bits.pos, len(packed)*8):
        if (packed[bit//8] >> (7-bit%8)) & 1:
            raise FormatError('Nonzero trailing scan padding')
    return bytes(output), end, bytes(tokens), {
        'start': hex(start), 'end': hex(end), 'output_bytes': len(output),
        'token_count': count, 'literal_bytes': len(literals),
        'scan_bits_consumed': bits.pos, 'scan_padding_bits': remaining_bits,
        'sha256': hashlib.sha256(output).hexdigest(),
    }

def extract(path, dest):
    data = Path(path).read_bytes()
    dest = Path(dest)
    dest.mkdir(exist_ok=True)
    manifest, p = [], 0
    while (p := data.find(b'CROM\xff\xd8', p)) >= 0:
        base, q, frames = p, p+4, []
        while data[q:q+2] == b'\xff\xd8':
            output, q, tokens, info = decode_frame(data, q)
            name = f'crom-{base:08x}-{len(frames)}'
            (dest/(name+'.bin')).write_bytes(output)
            (dest/(name+'.tokens')).write_bytes(tokens)
            info['file'] = name+'.bin'
            frames.append(info)
        manifest.append({'crom_offset': hex(base), 'frames': frames})
        p = q
    (dest/'manifest.json').write_text(json.dumps(manifest, indent=2))
    return manifest

def frame_parts(data, start):
    """Return original headers, strict codebooks and scan/literal bytes."""
    _, end, tokens, info = decode_frame(data, start)
    p = start+6
    parts = []
    codebooks = {}
    while p < end:
        marker = data[p:p+2]
        n = int.from_bytes(data[p+2:p+4], 'big')
        header = data[p+4:p+2+n]
        p += 2+n
        payload = b''
        if marker == b'\xff\xc4':
            q = 0
            while q < len(header):
                tid, counts = header[q], header[q+1:q+17]
                syms = header[q+17:q+17+sum(counts)]
                code, k, book = 0, 0, {}
                for bits, freq in enumerate(counts, 1):
                    for _ in range(freq):
                        book[syms[k]] = bits, code
                        k += 1
                        code += 1
                    code <<= 1
                codebooks[tid] = book
                q += 17+sum(counts)
        elif marker == b'\xff\xb1':
            n = int.from_bytes(header[1:5], 'big')
            payload = data[p:p+n]
            p += n
        elif marker == b'\xff\xb2':
            n = int.from_bytes(header, 'big')
            payload = data[p:p+n]
            p += n
        parts.append((marker, header, payload))
    return parts, codebooks, tokens, info

def pack_tokens(tokens, books, target_length=None):
    if len(tokens) % 3:
        raise FormatError('Incomplete token triple')
    source = tokens
    accumulator, available, output = 0, 0, bytearray()
    for i, symbol in enumerate(source):
        n, code = books[0xf0+i%3][symbol]
        accumulator = (accumulator << n) | code
        available += n
        while available >= 8:
            available -= 8
            output.append((accumulator >> available) & 255)
        accumulator &= (1 << available)-1
    if available:
        output.append(accumulator << (8-available))
    if target_length is None:
        # Reserve a complete extra 128-bit read block for the hardware reader.
        target_length = ((len(output)+15)//16+1)*16
    if len(output) > target_length:
        raise FormatError('Encoded scan exceeds requested allocation')
    output.extend(bytes(target_length-len(output)))
    return bytes(output)

def patch_frame(original, start, desired):
    """Rebuild a frame while preserving every valid original LZ reference.

    Any original reference that would propagate an edit into unrelated bytes
    becomes an explicit literal run. No new Huffman symbols are invented.
    This function returns a frame, not a complete flash image.
    """
    parts, books, old_tokens, info = frame_parts(original, start)
    if len(desired) < info['output_bytes']:
        raise FormatError('Shrinking modules is not supported')
    tokens, literals, offset, broken = bytearray(), bytearray(), 0, 0
    allowed = sorted((v+1 for v in books[0xf0] if v < 255), reverse=True)
    if 1 not in allowed or 0 not in books[0xf1] or 0 not in books[0xf2]:
        raise FormatError('Codebooks cannot represent arbitrary literal bytes')

    def literal(data):
        p = 0
        while p < len(data):
            n = next(n for n in allowed if n <= len(data)-p)
            tokens.extend((n-1, 0, 0))
            literals.extend(data[p:p+n])
            p += n

    for index in range(0, len(old_tokens), 3):
        n, lo, hi = old_tokens[index:index+3]
        distance = lo | (hi << 8)
        if not distance and n == 255:
            break
        count = n+2 if distance else n+1
        target = desired[offset:offset+count]
        if len(target) != count:
            raise FormatError('Desired module truncated')
        if distance and target == desired[offset-distance:offset-distance+count]:
            tokens.extend((n, lo, hi))
        else:
            literal(target)
            if distance:
                broken += 1
        offset += count
    if offset != info['output_bytes']:
        raise FormatError('Original token replay length mismatch')
    literal(desired[offset:])
    tokens.extend((255, 0, 0))
    packed = pack_tokens(tokens, books)
    payload = bytearray()
    for marker, header, _ in parts:
        if marker == b'\xff\xb1':
            header = bytearray(header)
            struct.pack_into('>II', header, 1, len(packed), len(tokens)//3)
            header[9] = (-(len(tokens)//3)) % 16
            body = packed
        elif marker == b'\xff\xb2':
            header = struct.pack('>I', len(literals))
            body = literals
        else:
            body = b''
        payload.extend(marker + struct.pack('>H', len(header)+2) + header + body)
    frame = b'\xff\xd8' + struct.pack('>I', 6+len(payload)) + payload
    decoded, end, _, check = decode_frame(frame, 0)
    if decoded != desired or end != len(frame):
        raise FormatError('Rebuilt frame failed exact decoded-byte comparison')
    check['references_converted_to_literals'] = broken
    return frame, check

if __name__ == '__main__':
    import sys
    print(json.dumps(extract(sys.argv[1], sys.argv[2]), indent=2))
