# DeckPad package audit

Measured 2026-10-14 on macOS with Python 3.14.8 and pnpm 12.11.0, from PR #20 (`b4fbc341a3f3aa483d8b4cc253c4aa9cfa9b166a`). This is a partial audit for #14, not release or hardware acceptance.

## Build and package

`pnpm install --frozen-lockfile` and `pnpm build` passed. `rollup.config.js` delegates to the official `@decky/rollup` helper; no bundler changes are proposed. No claim that the output is globally optimal or that unused dependencies have been independently eliminated is made.

The inventory follows the README's package inputs: `dist`, `py_modules`, `main.py`, `package.json`, `plugin.json`, `LICENSE` and `README.md`. Python cache directories are excluded. Both variants use Python `zipfile`, ZIP_DEFLATED level 9, a `DeckPad/` prefix and the same file ordering. The candidate omits only `.map` files; it does not change the canonical production package process.

| Variant | Files | ZIP bytes | Extracted bytes |
| --- | ---: | ---: | ---: |
| README inputs | 81 | 190,839 | 670,760 |
| Same inputs without source map | 80 | 179,149 | 621,314 |

The measured difference is **11,690 ZIP bytes**, including the removed ZIP entry metadata. It is not 48 KB. These locally constructed archives are not the published v0.0.1 asset. Docs/screenshots are not README package inputs, so hypothetical archives containing them are not release-size baselines.

Largest compressed entries in the baseline:

| Entry | Extracted bytes | Compressed bytes |
| --- | ---: | ---: |
| `DeckPad/py_modules/_stdlib/xml/etree/ElementTree.py` | 73,808 | 17,683 |
| `DeckPad/dist/index.js.map` | 49,446 | 11,564 |
| `DeckPad/py_modules/dbus_fast/message_bus.py` | 49,260 | 10,004 |
| `DeckPad/py_modules/dbus_fast/_private/unmarshaller.py` | 43,438 | 9,893 |
| `DeckPad/dist/index.js` | 25,872 | 7,282 |
| `DeckPad/py_modules/dbus_fast/aio/message_bus.py` | 25,439 | 6,482 |
| `DeckPad/py_modules/dbus_fast/service.py` | 28,346 | 6,325 |
| `DeckPad/py_modules/dbus_fast/introspection.py` | 31,622 | 6,135 |
| `DeckPad/py_modules/deckpad/controller_mode.py` | 19,695 | 5,029 |
| `DeckPad/py_modules/dbus_fast/proxy_object.py` | 19,296 | 5,004 |

The same emitted `dist/index.js` is 25,872 bytes extracted and 7,282 bytes compressed in both variants. Its map is 49,446 bytes extracted and 11,564 bytes compressed. Removing a debugging map changes debugging support; runtime compatibility still requires installation testing.

## Tests and acceptance

`python3 -m unittest discover -s tests -t . -v` ran 233 tests: **3 failures and 15 errors**, so the suite did not pass on this host. Five errors require Linux `/proc/self/fd`; link-monitor errors and Bluetooth diagnostics failures also require investigation on the supported Linux environment. They are not waived as acceptable hardware failures. No lint or reproducibility gate was run in this audit.

- [x] Frontend install and build.
- [x] Same-input archive comparison and top-entry inventory.
- [ ] Source-map exclusion in the production package process, if selected after validation.
- [ ] Persistent CI/package-summary output for the actual produced ZIP.
- [ ] Passing complete Python suite on supported Linux and documented store/ZIP validation.
- [ ] Install the candidate on a physical Steam Deck with Decky Loader; verify Controller Mode, Pairing Mode, input, reconnect, disconnect, Quit Combo and uninstall/reset.
- [ ] Measure startup/input effects before making performance claims.

The existing `root` flag, metadata, Python backend, vendored dependencies and licenses are unchanged by this documentation PR. Keep #14 open for the outstanding implementation and required hardware acceptance. No production-readiness assertion follows from these measurements.
