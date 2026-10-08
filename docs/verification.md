# Verification status

What has been checked on real hardware, and what is still open, so a decision record can point at one
place.

## Current reliability audit — 2026-10-07

Every code change was committed independently after relevant tests passed. No commit was pushed.

| Check | Result |
|---|---|
| Full Python behavior suite, Linux Python 3.11.7 container | 325 tests passed |
| Full Python behavior suite, Linux Python 3.12.3 (`orca`) | 325 tests passed |
| Frontend behavior tests, local Node 24.21.0 | 14 tests passed |
| TypeScript 7 typecheck and official Rollup preset build | Passed with frozen dependency installation |
| Ruff 0.15.0 (`F`, `E9`), Python compilation, whitespace checks | Passed; D-Bus signature annotations suppress only their exact false-positive lines |
| Actual official Decky CLI 0.0.7 ZIP | Final revision: 81 files verified, including backend bytes, API/root metadata and vendored licenses |
| GitHub Actions | Workflow configured for Python 3.11/3.12, frontend checks, static checks and official packaging; not run remotely because nothing was pushed |
| Decky embedded Python 3.11.7 | Current archive loaded on LCD, Decky 3.2.10; dbus-fast 5.2.0, real GATT registration, hidraw input reader and MGMT calls succeeded |
| Steam Deck LCD: startup, pairing, every Host-side control, disconnect/reconnect, exit, uninstall | Fresh run pending |
| Gaming Mode QAM, focus capture, Steam/QAM buttons, all menu restoration paths, diagnostics copy | Fresh run pending |
| Official Plugin Store testing and review | Not submitted or approved; third-party Stable/Beta reports and code-provenance eligibility remain open |

Compared current stable [Decky v3.2.10 with v3.2.9](https://github.com/SteamDeckHomebrew/decky-loader/compare/v3.2.9...v3.2.10): the plugin lifecycle/API code did not change. The PyInstaller spec adds unrelated standard-library imports, not `xml.etree`. The fresh embedded-runtime check below establishes backend startup on 3.2.10; it does not establish every hardware acceptance gate.

The current [Store addition template](https://github.com/SteamDeckHomebrew/decky-plugin-database/blob/main/.github/PULL_REQUEST_TEMPLATE/plugin_addition.md) requires developer verification on Stable and Beta, a third-party report on Stable or Beta for this Python/React architecture, and the declaration: “Generative AI was NOT used to write a majority of the code I am submitting.” This audit used AI assistance and cannot attest to the original code's provenance or the majority criterion. The maintainer must assess this honestly; no declaration or testing checkbox has been submitted. No messages, submission, release or push were made.

The final gates remain open. Use the current audit results together with the historical evidence below;
do not label this revision hardware-verified or Store-approved.

### Fresh LCD checks — 2026-10-07, Stable

Deployed the official CLI archive for code revision `72f3b69` (SHA-256
`123e351e562cd52142aee046580fb4a08df12ea75027850c47c3351a8818e396`) to the
existing DeckPad installation. All deployed package files match the archive; no extra source files
were present. The previous installation is preserved at
`/home/deck/DeckPad-before-audit-72f3b69`. No settings, paired-host records, unrelated plugins or
Bluetooth configuration files were replaced.

Setup: LCD, SteamOS 3.8.28 Stable build 20260922.1, kernel
`6.18.50-valve2-1-neptune-618-gc7289a96b14d`, BlueZ 5.83, Decky 3.2.10 and its
actual embedded Python 3.11.7. The Mac Host already had a DeckPad bond.

- Startup succeeds with the vendored dbus-fast 5.2.0 and embedded XML support. Controller Mode
  registers GATT, reads `/dev/hidraw2`, applies the identity override and requests interval 12–16.
- Three consecutive ON/OFF cycles return the expected state without a reported backend error.
- Independent read-only inspection after OFF finds exactly one original BlueZ identity and zero
  Xbox identity matches in the daemon's writable image; MGMT reads interval 24–40 (30–50 ms).
- Reload while ON restores DeviceID and interval, stops the backend, and loads a new backend OFF.
  Diagnostics confirm the original interval and inactive override; the existing Host and Quit Combo
  setting survive. No interval recovery journal remains in Decky's plugin runtime directory.
- Diagnostics work both ON and OFF. Current text uses Host labels rather than exposing MAC addresses
  in its structured summary.

These checks used official Decky backend routes through the running Steam CEF, not QAM interactions.
The existing Mac bond reaches BlueZ `Connected: yes`, but macOS displays the gamepad as not connected;
DeckPad records **zero delivered reports / no Host subscribed**. This is not a successful HID
reconnect or input test. A fresh pairing is pending user confirmation, followed by actual controls,
QAM, focus, clipboard, Bluetooth recovery, abnormal termination and uninstall checks.

Observed limitations: startup cleanup's `Device1.Disconnect` reaches its three-second timeout for this
old Mac connection. Repeated loader reloads also print pending `WSRouter._call_route` task warnings
in the newly created plugin process, before `DeckPad backend started`. Decky's
[process creation](https://github.com/SteamDeckHomebrew/decky-loader/blob/v3.2.10/backend/decky_loader/plugin/plugin.py)
and [new event loop initialization](https://github.com/SteamDeckHomebrew/decky-loader/blob/v3.2.10/backend/decky_loader/plugin/sandboxed_plugin.py)
show that these are loader coroutines, not DeckPad task names. No loader patch or warning suppression
was added; complete resource-leak acceptance remains open.

For the repeated connection failure, considered a native Host reconnect, fresh pairing, selecting the
LE bearer, and restarting Bluetooth. The Host's Connect action did not produce a HID subscription;
fresh pairing is the next scoped check. Bearer changes or a service restart would affect broader
Bluetooth state and were not used to hide the failure. BlueZ documents that
[Device1 connection success may mean only one profile connected](https://github.com/bluez/bluez/blob/5.83/doc/org.bluez.Device.rst),
so it cannot prove HID readiness.

### Forced-termination check and Loader limitation

With Controller Mode ON, an independent read confirmed exactly one Xbox identity, no original BlueZ
identity, interval 12–16, and a durable journal containing original interval 24–40. Sent SIGKILL only
to the verified DeckPad process. The subsequent official Loader reload request did not return within
30 seconds. Decky 3.2.10's socket reader returns an empty string on EOF while its response listener
continues parsing in a loop, swallowing the parse exception without closing the socket. This source
path is consistent with the observed unresponsive Loader; it is not a passing automatic crash-recovery
test.

Invoking the deployed DeckPad `device_id.restore_leftover` and
`connection_interval.restore_leftover` directly, once, returned true for both. Independent readback
confirmed identity `bluez`, interval 24–40, the same bluetoothd PID, and no interval journal. These are
the same functions used at plugin startup, but manual invocation does not prove automatic startup
recovery through an unresponsive Loader.

A service restart initially failed because the installed unit uses `KillMode=process`: the old Loader
and inherited listening sockets in child processes survived and held port 1337. Considered terminating
the verified stale service processes, changing KillMode, changing the port, and rebooting the Deck.
Used the existing systemd service's process scope: stop, SIGTERM to its members, SIGKILL only to the
verified unresponsive old Loader, then start after the group and port were empty. This restarts other
Decky plugins as part of Loader recovery; no Bluetooth service restart or permanent unit change was
made. See the official
[socket implementation](https://github.com/SteamDeckHomebrew/decky-loader/blob/v3.2.10/backend/decky_loader/localplatform/localsocket.py)
and [systemd kill semantics](https://github.com/systemd/systemd/blob/main/man/systemd.kill.xml).

## Module review

Reviewed the final responsibilities, callers and cleanup paths. Protocol values and stable external
interfaces stay explicit; no proxy framework, new daemon, compiled backend, state library or UI library
was added. Each row records why the retained mechanism is necessary and the check that constrains it.

| Module | Responsibility and simplest retained mechanism | Evidence / limit |
|---|---|---|
| `device_id.py` | One `/proc` write boundary, exact BlueZ version, unique image match, process/byte checks and verified restore/short-write rollback | Fault injection; actual daemon writes still need fresh LCD verification |
| `connection_interval.py` | MGMT range transaction; synced original journal, write/readback, compare before restore, retain failed recovery | Malformed packet/TLV/status and recovery faults; no speculative overwrite |
| `bluez.py` | One bounded message-call entry; remaining functions map directly to BlueZ methods | Bus timeout, loss, transport and cancellation tests; no introspection proxy |
| `hci_socket.py` | One Linux socket/bind boundary with declared libc ABI and six-byte address | ABI/layout and close-on-failure tests; embedded interpreter still pending |
| `link_monitor.py` | Own one socket/reader; parse only connection/update/disconnect events; forget pacing on loss | Exact lengths, handles, roles, intervals and EOF/error tests; 60 ms is the measured conservative rate, not a universal guarantee |
| `bluetooth_watch.py` | Independent owned bus, notify loss once; recovery belongs to ControllerMode | Connect cancellation, disconnect and repeated signal tests |
| `peripheral.py` | Session bus owns registrations; reverse cleanup plus connection close; fixed handles fail visibly | Registration/cancellation/teardown tests; public GATT reads cannot claim unrelated devices |
| `gatt.py` | Only the services and value formats DeckPad uses; validate permissions, offsets, lengths, protocol and subscriptions | Actual D-Bus plus direct boundary tests; no generic GATT framework |
| `agent.py` | Just Works candidate authorization; reject confirmation methods; derive allowed UUIDs from the actual application | Candidate identity, unrelated service and numeric/passkey rejection tests; Steam untrusted-device coexistence remains U10 |
| `identity.py` | Static Xbox identity and HID bytes | Golden byte/layout tests; dynamic generation would add a second source of truth |
| `advertisement.py` | Minimal LE advertisement; no Classic settings writes | GATT/advertisement lifecycle tests; session owns registration |
| `controller_mode.py` | Only Session coordinator; common synchronous cleanup, one cancellable recovery task and one uninstall deadline | Repeated toggles, interrupted publication/start/pairing, recovery, unload and uninstall tests; cancellation publishes OFF through an owned task |
| `connections.py` | Derive connections from Device1; persist ownership in PairedHosts; one intentional pause flag | Disconnect failure/cancellation, takeover, stale link and serialized advertising tests; uninstall worker does not rewrite files |
| `pairing.py` | One candidate path, one timer; serialize advertisement policy with reconnect decisions | Timeout, competition, delayed reply, detach and cancellation tests |
| `errors.py` | Stable codes, actionable messages, diagnostic detail | Existing operation failures plus settings failure/retry; no exception framework |
| `tasks.py` | Owned task set; completion observes exceptions; synchronous repeated cancellation | Exception-observation and cancellation tests |
| `deck_controls.py` | Read-only hidraw FD and its reader loop; locate again on reset, send neutral and re-arm Quit Combo | FIFO loss/reopen, pending report release and stop outside active-loop tests |
| `gamepad_report.py` | Pure conversion and preview decoding using one button table and neutral report | Button/direction/axis/trigger boundaries and golden reports |
| `report_pacer.py` | One pending latest report; reset recipient state on connection/subscription changes | Rate/dedup/reset tests and actual D-Bus resubscribe/reconnect tests |
| `gamepad_preview.py` | One timer and publication task only while watched | Rate, duplicate subscription, cancellation and late publication tests |
| `main.py` | Decky lifecycle/RPC/events and official per-plugin directories | Entry/unload/uninstall tests; pinned `py_modules` precedence retained; unused migration removed |
| `hosts.py` | Canonical validated MAC/name ownership records; no persisted connection state | Bad records, reload and unrelated-device tests; failed save is logged while runtime ownership is retained after an irreversible bond change |
| `settings.py`, `storage.py` | One strict boolean preference; synced atomic JSON replacement and temporary-file cleanup | Invalid types, failed writes, original-file preservation and actionable retry tests |
| `diagnostics.py` | One read-only collection feeds summary/text; bounded bus calls and off-loop privileged reads; label addresses | No Bluetooth, denied access, thread ownership and redaction tests; inspect arbitrary external log text before sharing |
| `__init__.py` | Add the vendored XML path only for missing `xml.etree` | Stripped interpreter subprocess and unrelated missing-module test; genuine embedded process pending |
| `backend.ts` | Sole RPC/event boundary; live events beat initial query, stale callbacks ignored; preview watcher count owns subscription | Initial/event race, unmount and overlapping watcher tests |
| `controller_screen.tsx` | Official router/navigation/focus; retain the exact private menu switch until restoration succeeds | Partial disable, changed store, failed restore, touch close and dismount tests; hardware menu/chord checks pending |
| `index.tsx` | Render backend facts using official components; one shared request handler | All QAM action paths clear old transport errors; backend errors remain backend-owned |
| `troubleshooting.tsx` | Local expanded state and latest diagnostics request; ignore results after hide/unmount | Overlapping queries and pending failure tests; both existing Clipboard paths retained until CEF measurement |
| `gamepad_outline.tsx` | Steam artwork access stays inside this component, with the existing minimal preview if absent | Reviewed mappings; hardware artwork and Steam version compatibility pending |
| Metadata, dependencies, build | ESM, API v1/root, official `deckyPlugin()`, pinned vendored pure Python with licenses | Metadata tests, frozen lockfile, official archive/content verification; root justified by `/proc` memory, MGMT and HCI access |
| `tests/support` | Fake only external D-Bus/controller/MGMT interfaces; shared asynchronous wait functions | Removed migration stubs and duplicate waits; test scenarios reuse existing behavior fixtures |

## Current compatibility boundaries

| Environment / interface | Current status |
|---|---|
| BlueZ 5.83 DeviceID | Explicitly allowed after process/unique-byte checks; historical hardware evidence, new safety paths tested with faults |
| Other BlueZ versions / unverified executable | No memory write; Hosts may read the daemon's generic identity; overall pairing/input compatibility unverified |
| Fixed GATT Handle conflict | Startup error and Session rollback; no dynamic-handle retry based on ambiguous `Failed` |
| Steam private menu switch absent | Menus remain enabled; official focus handling still applies |
| Steam menu restoration throws | Ownership retained for another attempt; no claim that a broken Steam API can be forced to restore |
| Steam private controller artwork absent | Existing simple preview remains available |
| Missing `xml.etree` only | Vendored CPython 3.11.7 implementation; other import errors propagate |
| Linux CPython / fake BlueZ | Automated development evidence; not a real radio or Decky shutdown deadline measurement |
| Steam Deck OLED / other Host operating systems | Unverified |

## Historical hardware baseline (before the reliability audit)

The hardware results below describe the earlier implementation on this setup. They explain the
protocol and private-interface decisions; they do **not** validate the revised implementation. The
current LCD Deck is unavailable over SSH, so a fresh acceptance run is pending.

| | Version |
|---|---|
| Steam Deck | LCD model (Realtek RTL8822CE Bluetooth), SteamOS 3.8.28 Stable (build 20260922.1), kernel 6.18, BlueZ 5.83 |
| Decky Loader | v3.2.9 (embedded Python 3.11.7) |
| Host | Arch Linux laptop, BlueZ 5.87, paired with `bluetoothctl` |

## Historical results

| Area | Existing automated coverage | Historical real Deck / Linux Host result |
|---|---|---|
| Controller Mode on/off, Decky reload and restart | Yes | Yes, including 16 and 10 on/off cycles; nothing left registered afterwards |
| Pairing from the Host's normal Bluetooth flow | Yes | Yes; the Host builds a `045E:0B13` gamepad bound to the `hid-microsoft` driver |
| Pairing timeout, cancel, and stale-pairing error | Yes | Timeout and stale-pairing error, yes |
| Reconnect without re-pairing after Controller Mode off/on | Yes | Yes; the Host reconnected by itself in about 2-11 s and kept receiving input |
| Disconnect, Allow Reconnecting, Forget | Yes | Yes |
| Deck controls to Gamepad Reports (mapping, send-on-change, pacing) | Yes | Report path yes; the Host's capabilities match the README's controls table. A person pressed every core control with the Controller Screen open, and each lit up correctly there; a button-by-button check on the Host's side has not been done |
| Report rate and latency | Pacing logic only | About 42-45 reports/s with no backlog once the 18.75 ms interval is in place; about 18-25 reports/s at the Host's initial 48.75 ms |
| Bluetooth restart, adapter off and on | Yes | Yes; Controller Mode resumed and the Host reconnected |
| Troubleshooting diagnostics | Yes | Collected and saved; the copy button in Gaming Mode has not been checked |
| Backend loading inside Decky's Python | Yes (reproduces the missing `xml.etree`) | Yes |
| Store package (metadata, licenses, files the store CI zips) | Yes | The store-shaped zip was installed and smoke-tested |
| Uninstall from Decky's settings | Yes | Yes, with a Host connected: its pairing was removed and DeckPad's files deleted |

Not yet checked on hardware: how the QAM panel looks (agents drove it through the plugin API only), the
copy button in Troubleshooting, and the open unknowns below.

## Historical Host coverage

| Host | Status |
|---|---|
| Linux with BlueZ (Arch Linux, BlueZ 5.87) | Tested: pairs, reconnects, receives input as an Xbox controller |
| Windows 10/11, macOS, iOS/iPadOS, Android, ChromeOS | Untested |
| Game consoles, smart TVs | Untested |
| Steam Deck OLED (as the controller) | Untested |

## Historical findings and open unknowns

| # | Unknown | Status |
|---|---|---|
| U1 | Which Device Information Service PnP ID each Host OS uses. bluetoothd publishes its own DIS (`1D6B:0246`) before DeckPad's, and a Linux Host built its first gamepad from it. | Resolved for Linux by overriding bluetoothd's DeviceID while Controller Mode is on ([ADR-0006](adr/0006-override-bluetoothd-deviceid-in-memory.md)): the Host reads `045E:0B13` on its first pairing. Windows, macOS, iOS and Android are untested. |
| U2 | Whether a shorter LE connection interval can be requested, and whether Hosts accept it. | Resolved for the Linux Host ([ADR-0008](adr/0008-shorter-connection-interval-and-link-paced-reports.md)): it settles at 18.75 ms. 3 of 13 interval updates were followed by a link drop. Other Hosts are untested. |
| U3 | Coexistence with Bluetooth headphones, keyboards or controllers paired to the Deck while a Host is connected (audio dropouts, throughput). | Open. Needs real peripherals and a person listening. |
| U4 | Whether Steam's UI on the Deck reacts to presses during Controller Mode, and whether a full-screen route can absorb them. | Mostly resolved on the Deck (SteamOS 3.8.28, Gaming Mode). The Controller Screen ([ADR-0011](adr/0011-controller-screen-route.md)) absorbs the presses: a person pressed every core control and nothing behind it moved. The first build also swallowed the Steam and `…` buttons, so the user could not leave. Now, while the Quit Combo ([ADR-0012](adr/0012-quit-combo.md)) is on, the screen turns those two buttons' menus off with Steam's own switch ([ADR-0014](adr/0014-turn-off-steams-menu-buttons-on-the-controller-screen.md)): pressing them opened nothing, and holding the Quit Combo closed the screen and turned Controller Mode off. **Close** (touch), Controller Mode turning off, and switching the Quit Combo off all turn the menus back on. The screen's drawing of what the Host receives ([ADR-0013](adr/0013-draw-the-host-view-with-steams-controller-outline.md)) lit up correctly for every control. Open: whether Steam's chords on the Steam button (holding it, Steam + B) still work while the screen is open. |
| U5 | Whether dbus-fast loads in Decky's embedded Python. | Resolved: Decky's Python 3.11.7 lacks `xml.etree`, and DeckPad ships CPython's copy as a fallback (`py_modules/_stdlib`). |
| U6 | Rumble from Windows/SDL Hosts, and Deck haptics. | Open, out of scope for now: output reports are accepted and dropped. |
| U7 | Dual-mode Hosts (Android, Windows) deriving a Classic link key and then trying a Classic connection to the Deck. | Open. To be observed during U1 tests. |
| U8 | Suspend and resume with a Host connected. | Open. |
| U9 | Steam Deck OLED (different Bluetooth chip). | Open. No hardware available. |
| U10 | Whether Steam marks every device it pairs as trusted. DeckPad's agent refuses `AuthorizeService` for paired but untrusted devices that are not Paired Hosts while Controller Mode is on ([ADR-0005](adr/0005-borrow-default-pairing-agent.md)). | Open. If Steam leaves some devices untrusted, they cannot use the Deck's services while Controller Mode is on. |
| U11 | Uninstall from Decky's settings removes the Paired Hosts' pairings within Decky's shutdown deadline. | Verified on the Deck through Decky's own uninstall call, with Controller Mode on and the Host connected: the Host was disconnected, its pairing removed, `paired_hosts.json` and `diagnostics.txt` deleted, and the interval restored, in 2.0 s. That other paired devices stay paired is covered by automated tests only, because no other device was paired to the Deck. |
