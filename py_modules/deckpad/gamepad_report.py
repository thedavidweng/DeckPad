"""Mapping from a Deck State Report (ADR-0003) to the Controller Identity's Gamepad Report (ADR-0002).

The Gamepad Report is the Xbox Wireless Controller 1914's BLE input report 0x01 without its report ID:
four u16 stick axes centred at 0x8000 with Y pointing down, two 10-bit triggers, a hat (0 neutral,
1 = up, clockwise to 8 = up-left), and the button bytes. Rear buttons, trackpads and the triggers'
digital clicks have no place in it and are dropped.
"""

import struct

DECK_STATE_REPORT_SIZE = 64
_DECK_STATE_REPORT_TYPE = 0x09

_TRIGGER_MAX = 1023

# (Deck State Report byte, bit) -> (Gamepad Report button byte index 0..2, mask)
_BUTTONS = (
    ((8, 7), (0, 0x01)),  # A
    ((8, 5), (0, 0x02)),  # B
    ((8, 6), (0, 0x08)),  # X
    ((8, 4), (0, 0x10)),  # Y
    ((8, 3), (0, 0x40)),  # LB
    ((8, 2), (0, 0x80)),  # RB
    ((9, 4), (1, 0x04)),  # View
    ((9, 6), (1, 0x08)),  # Menu
    ((9, 5), (1, 0x10)),  # Steam -> Guide
    ((10, 6), (1, 0x20)),  # L3
    ((11, 2), (1, 0x40)),  # R3
    ((14, 2), (2, 0x01)),  # Quick Access -> Share
)

# Hat positions indexed by (vertical, horizontal), each -1, 0 or 1 (up/right positive).
_HAT = {
    (1, 0): 1,
    (1, 1): 2,
    (0, 1): 3,
    (-1, 1): 4,
    (-1, 0): 5,
    (-1, -1): 6,
    (0, -1): 7,
    (1, -1): 8,
}


def gamepad_report(deck_state):
    """The 16-byte Gamepad Report for one Deck State Report, or None if `deck_state` is another kind of report."""
    if len(deck_state) < DECK_STATE_REPORT_SIZE or deck_state[0] != 0x01 or deck_state[2] != _DECK_STATE_REPORT_TYPE:
        return None
    lt, rt, lx, ly, rx, ry = struct.unpack_from("<hhhhhh", deck_state, 44)

    buttons = [0, 0, 0]
    for (offset, bit), (index, mask) in _BUTTONS:
        if deck_state[offset] & (1 << bit):
            buttons[index] |= mask

    dpad = deck_state[9]
    vertical = bool(dpad & 0x01) - bool(dpad & 0x08)
    horizontal = bool(dpad & 0x02) - bool(dpad & 0x04)

    return struct.pack(
        "<HHHHHHBBBB",
        _axis(lx),
        _inverted_axis(ly),
        _axis(rx),
        _inverted_axis(ry),
        _trigger(lt),
        _trigger(rt),
        _HAT.get((vertical, horizontal), 0),
        *buttons,
    )


def _axis(value):
    return min(max(value + 0x8000, 0), 0xFFFF)


def _inverted_axis(value):
    # The Deck's s16 goes one step further down (-32768) than up (32767). Shifting the upward half by
    # one keeps rest at exactly 0x8000 while full up still reaches 0.
    return _axis(-value - (value > 0))


def _trigger(value):
    return max(value, 0) * _TRIGGER_MAX // 0x7FFF
