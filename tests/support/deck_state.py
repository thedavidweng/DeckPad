"""Deck input reports as the Deck's built-in controller sends them on its hidraw node.

Offsets and bits follow the controller's 64-byte 0x09 report, as documented by the kernel's hid-steam
driver: buttons in bytes 8-14, then signed 16-bit triggers and sticks from byte 44, with the stick Y
axes pointing up.
"""

import struct

_BUTTON_BITS = {
    "R2": (8, 0),
    "L2": (8, 1),
    "RB": (8, 2),
    "LB": (8, 3),
    "Y": (8, 4),
    "B": (8, 5),
    "X": (8, 6),
    "A": (8, 7),
    "UP": (9, 0),
    "RIGHT": (9, 1),
    "LEFT": (9, 2),
    "DOWN": (9, 3),
    "VIEW": (9, 4),
    "STEAM": (9, 5),
    "MENU": (9, 6),
    "L5": (9, 7),
    "R5": (10, 0),
    "LEFT_PAD_CLICK": (10, 1),
    "RIGHT_PAD_CLICK": (10, 2),
    "L3": (10, 6),
    "R3": (11, 2),
    "L4": (13, 1),
    "R4": (13, 2),
    "QAM": (14, 2),
}


def deck_state_report(*buttons, lt=0, rt=0, lx=0, ly=0, rx=0, ry=0, seq=0):
    """A Deck input report with these buttons held. Stick Y is positive when pushed up, as on the Deck."""
    data = bytearray(64)
    data[0] = 0x01
    data[2] = 0x09
    data[3] = 0x40
    struct.pack_into("<I", data, 4, seq)
    for name in buttons:
        offset, bit = _BUTTON_BITS[name]
        data[offset] |= 1 << bit
    struct.pack_into("<hhhhhh", data, 44, lt, rt, lx, ly, rx, ry)
    return bytes(data)
