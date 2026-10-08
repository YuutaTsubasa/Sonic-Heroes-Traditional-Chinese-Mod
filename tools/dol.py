"""GameCube DOL helpers: address <-> file offset, PowerPC disassembly, reference search."""
import struct
import capstone


class Dol:
    def __init__(self, data: bytes):
        self.data = data
        offs = struct.unpack_from('>18I', data, 0)
        addrs = struct.unpack_from('>18I', data, 0x48)
        sizes = struct.unpack_from('>18I', data, 0x90)
        self.secs = [(i, offs[i], addrs[i], sizes[i]) for i in range(18) if sizes[i]]
        self.md = capstone.Cs(capstone.CS_ARCH_PPC, capstone.CS_MODE_32 | capstone.CS_MODE_BIG_ENDIAN)

    def off(self, addr):
        for i, o, a, s in self.secs:
            if a <= addr < a + s:
                return o + addr - a
        return None

    def addr(self, off):
        for i, o, a, s in self.secs:
            if o <= off < o + s:
                return a + off - o
        return None

    def code_secs(self):
        return [x for x in self.secs if x[0] < 7]

    def u32(self, addr):
        return struct.unpack_from('>I', self.data, self.off(addr))[0]

    def dis(self, addr, n=40):
        o = self.off(addr)
        return list(self.md.disasm(self.data[o:o + 4 * n], addr))

    def refs(self, target):
        """Find lis/addi (or lis/ori, lis/lwz-style) pairs that build `target`."""
        hi = (target >> 16) & 0xffff
        lo = target & 0xffff
        ha = ((target + 0x8000) >> 16) & 0xffff
        out = []
        for i, o, a, s in self.code_secs():
            for k in range(0, s, 4):
                w = struct.unpack_from('>I', self.data, o + k)[0]
                if (w >> 26) == 15 and ((w >> 16) & 31) == 0 and (w & 0xffff) in (hi, ha):
                    rd = (w >> 21) & 31
                    for j in range(1, 24):
                        if k + 4 * j >= s:
                            break
                        w2 = struct.unpack_from('>I', self.data, o + k + 4 * j)[0]
                        op = w2 >> 26
                        if ((w2 >> 16) & 31) == rd and (w2 & 0xffff) == lo and op in (14, 24, 32, 34, 36, 38, 40, 44, 48, 50, 52):
                            out.append(a + k + 4 * j)
                            break
        return out
