"""GameCube REL module parser (header, sections, imports, relocations)."""
import struct

R_NAMES = {0: 'NONE', 1: 'ADDR32', 2: 'ADDR24', 3: 'ADDR16', 4: 'ADDR16_LO', 5: 'ADDR16_HI', 6: 'ADDR16_HA',
           7: 'ADDR14', 10: 'REL24', 11: 'REL14', 201: 'NOP', 202: 'SECTION', 203: 'END'}


class Rel:
    def __init__(self, data: bytes):
        self.data = data
        (self.id, _n, _p, self.nsec, self.secoff, self.nameoff, self.namesize, self.version,
         self.bss, self.reloff, self.impoff, self.impsize) = struct.unpack_from('>12I', data, 0)
        self.sections = []
        for i in range(self.nsec):
            off, size = struct.unpack_from('>II', data, self.secoff + 8 * i)
            self.sections.append((off & ~1, size, off & 1))
        self.imports = []
        for i in range(self.impsize // 8):
            mod, off = struct.unpack_from('>II', data, self.impoff + 8 * i)
            self.imports.append((mod, off))

    def relocs(self, with_pos=False):
        """Yield (module, section, offset_in_section, type, target_section, addend[, entry_file_offset])."""
        for mod, off in self.imports:
            sec = None
            pos = 0
            while True:
                o, t, s, a = struct.unpack_from('>HBBI', self.data, off)
                off += 8
                if t == 203:
                    break
                if t == 202:
                    sec = s; pos = 0
                    continue
                pos += o
                if t == 201:
                    continue
                if with_pos:
                    yield mod, sec, pos, t, s, a, off - 8
                else:
                    yield mod, sec, pos, t, s, a
