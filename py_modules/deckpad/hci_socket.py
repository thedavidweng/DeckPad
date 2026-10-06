"""Raw Bluetooth HCI sockets without the socket module's Bluetooth support.

Decky's bundled Python is built without it: `socket.AF_BLUETOOTH` does not exist and `bind` cannot
parse an HCI address. The kernel does not care, so the socket is created by number and bound through
libc with a hand-packed `struct sockaddr_hci`.
"""

import os
import socket
import struct

AF_BLUETOOTH = 31
BTPROTO_HCI = 1
HCI_DEV_NONE = 0xFFFF
HCI_CHANNEL_RAW = 0
HCI_CHANNEL_CONTROL = 3


def open_hci_socket(index, channel):
    import ctypes

    sock = socket.socket(AF_BLUETOOTH, socket.SOCK_RAW | socket.SOCK_CLOEXEC, BTPROTO_HCI)
    try:
        address = struct.pack("<HHH", AF_BLUETOOTH, index, channel)
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.bind(sock.fileno(), ctypes.create_string_buffer(address, len(address)), len(address)) != 0:
            errno = ctypes.get_errno()
            raise OSError(errno, os.strerror(errno))
    except BaseException:
        sock.close()
        raise
    return sock
