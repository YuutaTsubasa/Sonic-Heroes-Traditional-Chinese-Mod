"""Sonic Heroes .one archive (GameCube, little-endian RenderWare-style chunks, PRS-compressed entries)."""
import struct
import prs

RWVER = 0x1400FFFF


def parse(data: bytes):
    """Return (rwver, [(name, compressed_bytes)])."""
    _, size, ver = struct.unpack_from('<III', data, 0)
    t, nsize, _ = struct.unpack_from('<III', data, 12)
    assert t == 1, t
    names = [data[24 + 64 * i:24 + 64 * (i + 1)].split(b'\0')[0].decode('latin-1') for i in range(nsize // 64)]
    pos = 24 + nsize
    out = []
    while pos + 12 <= len(data):
        idx, csize, v = struct.unpack_from('<III', data, pos)
        out.append((names[idx], data[pos + 12:pos + 12 + csize]))
        pos += 12 + csize
    return ver, names, out


def files(data: bytes):
    ver, names, ents = parse(data)
    return [(n, prs.decompress(c)) for n, c in ents]


def build(ver, names, ents):
    """ents: [(name, compressed_bytes)] in order. Names table is kept as given."""
    nt = b''.join(n.encode('latin-1').ljust(64, b'\0') for n in names)
    body = bytearray()
    body += struct.pack('<III', 1, len(nt), ver) + nt
    for n, c in ents:
        body += struct.pack('<III', names.index(n), len(c), ver) + c
    return struct.pack('<III', 0, len(body), ver) + bytes(body)
