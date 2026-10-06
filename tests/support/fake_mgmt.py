"""The kernel's Bluetooth management (MGMT) control channel, as seen through a socket.

Models only Read/Set Default System Configuration (opcodes 0x004B/0x004C, BlueZ doc/mgmt-api.txt) for
one controller index, plus unrelated events that every control socket also receives.
"""

import collections
import struct

READ_DEF_SYSTEM_CONFIG = 0x004B
SET_DEF_SYSTEM_CONFIG = 0x004C
EV_CMD_COMPLETE = 0x0001
EV_CMD_STATUS = 0x0002
EV_DEVICE_FOUND = 0x0012
STATUS_INVALID_INDEX = 0x11

LE_MIN_CONN_INTERVAL = 0x0017
LE_MAX_CONN_INTERVAL = 0x0018


class FakeMgmtKernel:
    def __init__(self, index=0, conn_interval=(24, 40)):
        self.index = index
        # TLV type -> u16 value. A few other parameters, as the kernel returns ~30 of them.
        self.config = {0x0000: 0, 0x000A: 0x0800, LE_MIN_CONN_INTERVAL: conn_interval[0],
                       LE_MAX_CONN_INTERVAL: conn_interval[1], 0x0019: 0, 0x001A: 42}
        self.sockets_opened = 0
        self.refuse = False

    @property
    def conn_interval(self):
        return (self.config[LE_MIN_CONN_INTERVAL], self.config[LE_MAX_CONN_INTERVAL])

    def open_socket(self):
        if self.refuse:
            raise PermissionError(1, "Operation not permitted")
        self.sockets_opened += 1
        return _ControlSocket(self)

    def handle(self, opcode, index, params):
        if index != self.index:
            return _event(EV_CMD_STATUS, index, struct.pack("<HB", opcode, STATUS_INVALID_INDEX))
        if opcode == READ_DEF_SYSTEM_CONFIG:
            tlvs = b"".join(struct.pack("<HBH", t, 2, v) for t, v in sorted(self.config.items()))
            return _event(EV_CMD_COMPLETE, index, struct.pack("<HB", opcode, 0) + tlvs)
        if opcode == SET_DEF_SYSTEM_CONFIG:
            offset = 0
            while offset + 3 <= len(params):
                t, length = struct.unpack_from("<HB", params, offset)
                (value,) = struct.unpack_from("<H", params, offset + 3)
                self.config[t] = value
                offset += 3 + length
            return _event(EV_CMD_COMPLETE, index, struct.pack("<HB", opcode, 0))
        return _event(EV_CMD_STATUS, index, struct.pack("<HB", opcode, 0x01))


def _event(code, index, params):
    return struct.pack("<HHH", code, index, len(params)) + params


class _ControlSocket:
    def __init__(self, kernel):
        self._kernel = kernel
        self._inbox = collections.deque()
        self.closed = False

    def settimeout(self, timeout):
        pass

    def send(self, data):
        opcode, index, length = struct.unpack_from("<HHH", data)
        # Control sockets also see events nobody asked for, e.g. a scan result from Steam's discovery.
        self._inbox.append(_event(EV_DEVICE_FOUND, self._kernel.index, bytes(14)))
        self._inbox.append(self._kernel.handle(opcode, index, data[6 : 6 + length]))
        return len(data)

    def recv(self, size):
        if not self._inbox:
            raise TimeoutError("timed out")
        return self._inbox.popleft()[:size]

    def close(self):
        self.closed = True
