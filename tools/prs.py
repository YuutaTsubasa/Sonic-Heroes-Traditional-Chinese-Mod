"""SEGA PRS compression (decompress + compress) as used by SA2 PC."""


def decompress(data: bytes) -> bytes:
    out = bytearray()
    pos = 0
    bitpos = 0
    ctrl = 0

    def bit():
        nonlocal pos, bitpos, ctrl
        if bitpos == 0:
            ctrl = data[pos]
            pos += 1
            bitpos = 8
        b = ctrl & 1
        ctrl >>= 1
        bitpos -= 1
        return b

    while True:
        if bit():
            out.append(data[pos])
            pos += 1
            continue
        if bit():
            v = data[pos] | (data[pos + 1] << 8)
            pos += 2
            if v == 0:
                break
            size = v & 7
            off = (v >> 3) - 0x2000
            if size == 0:
                size = data[pos] + 1
                pos += 1
            else:
                size += 2
        else:
            size = (bit() << 1 | bit()) + 2
            off = data[pos] - 0x100
            pos += 1
        start = len(out) + off
        for i in range(size):
            out.append(out[start + i])
    return bytes(out)


def compress(data: bytes) -> bytes:
    """LZ77 PRS compressor: hash chains (window 0x1FF0, length <= 256), two-byte short matches, and lazy
    matching by bit cost (literal 9 bits, short copy 12, long copy 18 / 26)."""
    n = len(data)
    head = {}
    prev = [-1] * n
    inserted = 0

    def insert_upto(p):
        nonlocal inserted
        while inserted <= p and inserted + 3 <= n:
            k = data[inserted:inserted + 3]
            prev[inserted] = head.get(k, -1)
            head[k] = inserted
            inserted += 1

    def cost(length, off):
        if length <= 5 and off <= 0x100:
            return 12
        return 18 if length <= 9 else 26

    def find(i):
        """Best (gain, length, off) at i."""
        best = (0, 0, 0)
        if i + 2 > n:
            return best
        maxlen = min(256, n - i)
        if i + 3 <= n:
            insert_upto(i - 1)
            cand = head.get(data[i:i + 3], -1)
            tries = 0
            while cand >= 0 and i - cand <= 0x1FF0 and tries < 512:
                if cand < i:
                    l = 3
                    while l < maxlen and data[cand + l] == data[i + l]:
                        l += 1
                    off = i - cand
                    g = 9 * l - cost(l, off)
                    if g > best[0]:
                        best = (g, l, off)
                        if l == maxlen:
                            break
                cand = prev[cand]
                tries += 1
        if best[1] < 3:
            lo = max(0, i - 0x100)
            k = data.rfind(data[i:i + 2], lo, i + 1)
            if 0 <= k < i:
                best = max(best, (18 - 12, 2, i - k))
        return best

    stream = []
    i = 0
    nxt = find(0)
    while i < n:
        g, l, off = nxt
        if l >= 2 and i + 1 < n:
            nxt1 = find(i + 1)
            if nxt1[0] > g + 1:  # a literal now buys a better match next
                stream.append(('lit', data[i]))
                i += 1
                nxt = nxt1
                continue
        if l >= 2 and g > 0:
            stream.append(('copy', l, off))
            i += l
        else:
            stream.append(('lit', data[i]))
            i += 1
        nxt = find(i) if i < n else (0, 0, 0)

    out = bytearray()
    ctrl_pos = 0
    ctrl_bit = 8

    def bit(v):
        nonlocal ctrl_pos, ctrl_bit
        if ctrl_bit == 8:
            ctrl_pos = len(out)
            out.append(0)
            ctrl_bit = 0
        out[ctrl_pos] |= v << ctrl_bit
        ctrl_bit += 1

    for e in stream:
        if e[0] == 'lit':
            bit(1); out.append(e[1])
            continue
        _, l, off = e
        if l <= 5 and off <= 0x100:
            s_ = l - 2
            bit(0); bit(0); bit((s_ >> 1) & 1); bit(s_ & 1)
            out.append((0x100 - off) & 0xFF)
        else:
            o = (0x2000 - off) & 0x1FFF
            bit(0); bit(1)
            if l <= 9:
                v = (o << 3) | (l - 2)
                out += bytes([v & 0xFF, v >> 8])
            else:
                v = o << 3
                out += bytes([v & 0xFF, v >> 8, l - 1])
    bit(0); bit(1)
    out += bytes(2)
    return bytes(out)


if __name__ == '__main__':
    import sys
    for p in sys.argv[1:]:
        raw = open(p, 'rb').read()
        d = decompress(raw)
        c = compress(d)
        assert decompress(c) == d, p
        print(p, len(raw), len(d), len(c))
