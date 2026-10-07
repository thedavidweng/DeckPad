# Vendored Python modules

Decky Loader runs plugin backends in its own frozen Python 3.11 (PyInstaller), which cannot import
SteamOS's system packages. Everything the backend imports beyond that interpreter lives here, pinned.
Decky appends this directory to `sys.path`; `main.py` also puts it first.

| Path | What | Version | Source | License |
|---|---|---|---|---|
| `deckpad/` | DeckPad's own backend package | - | this repo | see `/LICENSE`; the Xbox 1914 descriptor in `identity.py` is MIT, `deckpad/ESP32-BLE-CompositeHID.LICENSE` |
| `dbus_fast/` | dbus-fast, pure-Python (no compiled extensions) | 5.2.0 | PyPI sdist `dbus_fast-5.2.0.tar.gz`, sha256 `a4a5dddc04b1ade5eb7650d791e2f6fb7c1334595593473914e78a2526ecddda`, `src/dbus_fast/` copied unmodified | MIT, `dbus_fast/LICENSE` |
| `_stdlib/xml/etree/` | CPython's `xml.etree`, used only when the interpreter lacks it | 3.11.7 | `Lib/xml/etree/` at CPython tag `v3.11.7`, unmodified | PSF License, `_stdlib/LICENSE` |

Decky Loader v3.2.9's interpreter (Python 3.11.7) ships `xml` and `pyexpat` but not `xml.etree`,
which dbus-fast imports at module level. `deckpad/__init__.py` adds `_stdlib/xml` to the `xml`
package path only when `xml.etree` is missing.

To update dbus-fast, replace `dbus_fast/` with `src/dbus_fast/` from the new sdist, keep its LICENSE,
update this table, and run `pnpm test` under Python 3.11 (`mise x python@3.11 -- pnpm test`).
