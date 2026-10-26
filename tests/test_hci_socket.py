"""The Linux sockaddr_hci ABI and socket ownership at the libc bind boundary."""

import ctypes
import errno
import unittest
from unittest.mock import Mock, patch

from deckpad import hci_socket


class HciSocketBoundary(unittest.TestCase):
    def test_bind_uses_the_linux_address_layout_and_declared_abi(self):
        sock = Mock()
        sock.fileno.return_value = 42
        libc = Mock()
        addresses = []

        def bind(fd, address, size):
            self.assertEqual(fd, 42)
            addresses.append(ctypes.string_at(address, size))
            return 0

        libc.bind.side_effect = bind
        with patch("socket.socket", return_value=sock), patch("ctypes.CDLL", return_value=libc):
            self.assertIs(hci_socket.open_hci_socket(0x1234, 3), sock)
        self.assertEqual(addresses, [bytes.fromhex("1f0034120300")])
        self.assertEqual(libc.bind.argtypes, [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint])
        self.assertIs(libc.bind.restype, ctypes.c_int)
        sock.close.assert_not_called()

    def test_a_failed_bind_releases_the_socket_and_preserves_errno(self):
        sock = Mock()
        sock.fileno.return_value = 42
        libc = Mock()
        libc.bind.return_value = -1
        with patch("socket.socket", return_value=sock), patch("ctypes.CDLL", return_value=libc), \
             patch("ctypes.get_errno", return_value=errno.EPERM):
            with self.assertRaises(OSError) as failure:
                hci_socket.open_hci_socket(0, 3)
        self.assertEqual(failure.exception.errno, errno.EPERM)
        sock.close.assert_called_once()
