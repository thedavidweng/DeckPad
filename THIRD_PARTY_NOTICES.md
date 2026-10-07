# Third-party notices

DeckPad includes the following third-party software. Full license texts ship next to each copy.

- **dbus-fast** 5.2.0, MIT License. Copyright (c) 2022 Bluetooth Devices Authors.
  `py_modules/dbus_fast/` (license: `py_modules/dbus_fast/LICENSE`).
- **CPython `xml.etree`** 3.11.7, Python Software Foundation License.
  Copyright (c) 2001 Python Software Foundation; portions Copyright (c) 1999-2008 by Fredrik Lundh (license text in the file headers).
  `py_modules/_stdlib/xml/etree/` (license: `py_modules/_stdlib/LICENSE`).
- **ESP32-BLE-CompositeHID** (`XboxOneS_1914_HIDDescriptor` from `XboxDescriptors.h`), MIT License.
  Copyright (c) 2021 lemmingDev. The HID report descriptor bytes in `py_modules/deckpad/identity.py`
  (license: `py_modules/deckpad/ESP32-BLE-CompositeHID.LICENSE`, also reproduced below).
- **decky-plugin-template**, BSD 3-Clause License. See the bottom of `LICENSE`.

The Decky Plugin Store zip contains `LICENSE`, `README.md`, `main.py`, `package.json`, `plugin.json`,
`dist/`, and `py_modules/`, but not this file, so every license text above also ships inside
`py_modules/` next to the code it covers. `tests/test_store_package.py` checks that.

DeckPad does not include code from the projects credited as prior art in the README (DeckJoy,
DeckControllerOS, the Linux `hid-steam` driver, SDL). They were used as references for the design and
for facts such as report offsets and button layouts.

## ESP32-BLE-CompositeHID license

```
Software License Agreement (MIT License)

Copyright (c) 2021 lemmingDev - https://github.com/lemmingDev

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
