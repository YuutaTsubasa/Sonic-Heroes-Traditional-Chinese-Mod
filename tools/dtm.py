"""Write a Dolphin input movie (.dtm) for GameCube port 1, to drive the game for screenshots/testing.

  python tools/dtm.py out.dtm "start@200x8 a@400x8 ... wait@3000"
Each step: <buttons>@<record index>x<length>; buttons joined by '+': start a b x y z up down left right l r.
Analog sticks stay centred. One record is one controller poll (the game may poll more than once a frame).
"""
import struct
import sys

BITS = {'start': 0, 'a': 1, 'b': 2, 'x': 3, 'y': 4, 'z': 5, 'up': 6, 'down': 7,
        'left': 8, 'right': 9, 'l': 10, 'r': 11}
CONNECTED = 1 << 14  # bit 15 is get_origin


def state(buttons):
    v = CONNECTED
    for b in buttons:
        v |= 1 << BITS[b]
    trig_l = 255 if 'l' in buttons else 0
    trig_r = 255 if 'r' in buttons else 0
    return struct.pack('<HBBBBBB', v, trig_l, trig_r, 128, 128, 128, 128)


def build(steps, total, game_id=b'G9SJ8P'):
    recs = [state([])] * total
    for buttons, start, length in steps:
        for i in range(start, min(start + length, total)):
            recs[i] = state(buttons)
    head = bytearray(256)
    head[0:4] = b'DTM\x1a'
    head[4:10] = game_id
    head[0x0A] = 0          # GameCube
    head[0x0B] = 1          # port 1 connected
    struct.pack_into('<QQ', head, 0x0D, total, total)  # frame count (approx), input count
    head[0x31:0x31 + 6] = b'claude'
    head[0x97] = 1          # memory card in slot A
    head[0xA3] = 1          # SYSCONF country: Japan
    struct.pack_into('<Q', head, 0xED, 486000000 * 3600)  # tick budget: playback ends once exceeded
    return bytes(head) + b''.join(recs)


def parse(spec):
    steps, total = [], 0
    for tok in spec.split():
        if tok.startswith('wait@'):
            total = int(tok[5:])
            continue
        btn, rest = tok.split('@')
        at, ln = rest.split('x')
        steps.append((btn.split('+'), int(at), int(ln)))
        total = max(total, int(at) + int(ln))
    return steps, total


if __name__ == '__main__':
    steps, total = parse(sys.argv[2])
    open(sys.argv[1], 'wb').write(build(steps, total))
    print(sys.argv[1], total, 'records')
