"""Controller Identity (ADR-0002): Xbox Wireless Controller, model 1914, BLE firmware."""

import struct

VENDOR_ID_SOURCE_USB = 0x02
VENDOR_ID = 0x045E
PRODUCT_ID = 0x0B13
PRODUCT_VERSION = 0x0509

PNP_ID = struct.pack("<BHHH", VENDOR_ID_SOURCE_USB, VENDOR_ID, PRODUCT_ID, PRODUCT_VERSION)
