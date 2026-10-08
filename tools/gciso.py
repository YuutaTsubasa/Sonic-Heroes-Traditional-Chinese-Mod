"""GameCube disc image: read the FST and write a patched copy.

patch(src_iso, dst_iso, changes) where changes = {"path/in/files": bytes | None}. Unchanged files keep their
bytes and offsets, so an empty `changes` gives a byte-identical copy. A changed file is written over its old
place when it fits, otherwise into free space between files (Sonic Heroes has a ~175 MB gap after the FST,
since its data sits at the outer edge); new files are added to their directory; None removes the entry. The
FST is rewritten in place (growing into the free space right after it if needed) and boot.bin's FST size
fields (0x428/0x42C) are updated.
"""
import shutil
import struct

ALIGN = 0x8000


class Node:
    def __init__(self, name, is_dir, offset=0, size=0):
        self.name, self.is_dir, self.offset, self.size = name, is_dir, offset, size
        self.children = []
        self.data = None  # new bytes, if changed


def read_fst(f):
    f.seek(0x424)
    fst_off, fst_size, fst_max = struct.unpack('>III', f.read(12))
    f.seek(fst_off)
    fst = f.read(fst_size)
    n = struct.unpack_from('>I', fst, 8)[0]
    strtab = n * 12

    def name_at(o):
        e = fst.index(b'\0', strtab + o)
        return fst[strtab + o:e].decode('cp932')

    root = Node('', True)

    def walk(i, end, node):
        while i < end:
            w0, w1, w2 = struct.unpack_from('>III', fst, i * 12)
            nm = name_at(w0 & 0xFFFFFF)
            if w0 >> 24:
                d = Node(nm, True)
                node.children.append(d)
                walk(i + 1, w2, d)
                i = w2
            else:
                node.children.append(Node(nm, False, w1, w2))
                i += 1

    walk(1, n, root)
    return root, fst_off, fst_size, fst_max


def iter_files(node, prefix=''):
    for c in node.children:
        p = prefix + c.name
        if c.is_dir:
            yield from iter_files(c, p + '/')
        else:
            yield p, c


def find(root, path, create=False):
    parts = path.split('/')
    node = root
    for k, part in enumerate(parts):
        last = k == len(parts) - 1
        hit = next((c for c in node.children if c.name.lower() == part.lower()), None)
        if hit is None:
            if not create:
                return None, node
            hit = Node(part, not last)
            node.children.append(hit)
            node.children.sort(key=lambda c: c.name.lower())
        node = hit
    return node, None


def build_fst(root):
    entries = []
    names = bytearray()

    def add_name(nm):
        o = len(names)
        names.extend(nm.encode('cp932') + b'\0')
        return o

    entries.append([0x01000000, 0, 0])

    def walk(node, parent_idx):
        for c in node.children:
            idx = len(entries)
            if c.is_dir:
                entries.append([0x01000000 | add_name(c.name), parent_idx, 0])
                walk(c, idx)
                entries[idx][2] = len(entries)
            else:
                entries.append([add_name(c.name), c.offset, c.size])

    walk(root, 0)
    entries[0][2] = len(entries)
    return b''.join(struct.pack('>III', *e) for e in entries) + bytes(names)


def free_space(root, fst_off, disc_size):
    used = sorted((n.offset, n.offset + n.size) for _, n in iter_files(root) if n.size)
    gaps = []
    prev = fst_off
    for a, b in used:
        if a > prev:
            gaps.append([prev, a])
        prev = max(prev, b)
    if disc_size > prev:
        gaps.append([prev, disc_size])
    return gaps


def alloc(gaps, size, align=ALIGN):
    for g in gaps:
        start = (g[0] + align - 1) // align * align
        if start + size <= g[1]:
            g[0] = start + size
            return start
    raise ValueError(f'no free space for {size} bytes')


def patch(src, dst, changes):
    with open(src, 'rb') as f:
        root, fst_off, fst_size, fst_max = read_fst(f)
        f.seek(0, 2)
        disc_size = f.tell()
    # the FST may grow by up to 64 KiB into the space after it
    gaps = free_space(root, fst_off, disc_size)
    assert gaps and gaps[0][0] == fst_off and gaps[0][1] - fst_off > fst_size + 0x10000, 'no room after FST'
    gaps[0][0] = fst_off + fst_size + 0x10000
    for path, data in sorted(changes.items()):
        node, parent = find(root, path, create=data is not None)
        if data is None:
            if node is not None:
                dirnode = find(root, path.rsplit('/', 1)[0])[0] if '/' in path else root
                dirnode.children.remove(node)
            continue
        node.data = data
        if node.size and len(data) <= node.size:
            node.size = len(data)
        else:
            node.offset, node.size = alloc(gaps, len(data)), len(data)
    fst = build_fst(root)
    if len(fst) > fst_size + 0x10000:
        raise ValueError('FST grew too much')
    shutil.copyfile(src, dst)
    with open(dst, 'r+b') as f:
        for _, n in iter_files(root):
            if n.data is not None:
                f.seek(n.offset)
                f.write(n.data)
        f.seek(fst_off)
        f.write(fst)
        f.seek(0x428)
        f.write(struct.pack('>II', len(fst), max(len(fst), fst_max)))
    return {'fst_size': len(fst), 'fst_growth': len(fst) - fst_size}
