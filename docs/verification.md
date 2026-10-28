# Verification status

What has been checked on real hardware, and what is still open, so a decision record can point at one
place.

## Current reliability audit — updated 2026-10-09

Every code change was committed independently after relevant tests passed. No commit was pushed.

| Check | Result |
|---|---|
| Full Python behavior suite, Linux Python 3.11.7 container | 334 tests passed, including adapter-identity regressions |
| Full Python behavior suite, Linux Python 3.12.3 (`orca`) | 334 tests passed, including Disconnect write-result and adapter-identity regressions |
| Frontend behavior tests, local Node 24.21.0 | 14 tests passed |
| TypeScript 7 typecheck and official Rollup preset build | Passed with frozen dependency installation |
| Ruff 0.15.0 (`F`, `E9`), Python compilation, whitespace checks | Passed; D-Bus signature annotations suppress only their exact false-positive lines |
| Actual official Decky CLI 0.0.7 ZIP | Final revision: 81 files verified, including backend bytes, API/root metadata and vendored licenses |
| GitHub Actions | Workflow configured for Python 3.11/3.12, frontend checks, static checks and official packaging; not run remotely because nothing was pushed |
| Decky embedded Python 3.11.7 | Current archive loaded on LCD, Decky 3.2.10; dbus-fast 5.2.0, real GATT registration, hidraw input reader and MGMT calls succeeded |
| Steam Deck LCD: startup, pairing, controls, reconnect, exit, uninstall | Fresh Mac pairing, core buttons, axes, triggers, L3/R3/Share, retained-bond reconnection, Quit Combo exit and connected-Host official uninstall verified below; Guide encoded on transport but no Mac application callback; repeated manual Connect failures and active-input recovery remain open |
| Gaming Mode QAM, focus capture, Steam/QAM buttons, all menu restoration paths, diagnostics copy | Real panel and Controller Screen inspected; user confirms focus behavior and Quit Combo menu restoration; copied diagnostics match saved contents; Close, Quit Combo disabled, reload/unload and chord routes remain open |
| Official Plugin Store testing and review | Not submitted or approved; third-party Stable/Beta reports and code-provenance eligibility remain open |

Compared current stable [Decky v3.2.10 with v3.2.9](https://github.com/SteamDeckHomebrew/decky-loader/compare/v3.2.9...v3.2.10): the plugin lifecycle/API code did not change. The PyInstaller spec adds unrelated standard-library imports, not `xml.etree`. The fresh embedded-runtime check below establishes backend startup on 3.2.10; it does not establish every hardware acceptance gate.

The current [Store addition template](https://github.com/SteamDeckHomebrew/decky-plugin-database/blob/main/.github/PULL_REQUEST_TEMPLATE/plugin_addition.md) requires developer verification on Stable and Beta, a third-party report on Stable or Beta for this Python/React architecture, and the declaration: “Generative AI was NOT used to write a majority of the code I am submitting.” This audit used AI assistance and cannot attest to the original code's provenance or the majority criterion. The maintainer must assess this honestly; no declaration or testing checkbox has been submitted. No messages, submission, release or push were made.

The final gates remain open. Use the current audit results together with the historical evidence below;
do not label this revision hardware-verified or Store-approved.

The [MagicPods Bluetooth comparison](magicpods-bluetooth-comparison.md) records the 2026-10-09
fresh-pairing regression: both the rewrite and the byte-verified original release failed today.
The Deck had resumed from suspend before testing. An adapter power cycle also failed: the user
corrected the initial connection-success report, and backend, HCI capture and native Mac observer
agree that no pairing or HID attachment occurred. This is not a verified fix or a rewrite-only failure.

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
reconnect or input test. The later original-release comparison below supersedes the pending fresh
pairing status: the rewritten package now pairs and delivers HID reports on this Mac. Complete
controls, QAM, focus, clipboard and uninstall checks remain open. Bluetooth recovery and abnormal termination were
subsequently checked with the results and limitations recorded below.

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

### Bluetooth service recovery and cancellation

Restarting the actual Bluetooth service while Controller Mode was ON produced one loss notification,
RECOVERING, and a successful new Session with GATT, the input reader, the identity override and
interval request. The first run logged an unobserved dbus-fast send Future error. Review found that
DeckPad's synchronous unload Disconnect ignored its send result. Revision `255b4bc` now reads an
immediate result or attaches a completion callback that records a delayed write error; the existing
Peripheral close caller records immediate failures. This does not suppress dbus-fast's own internal
send failures or prove that every such warning had the same source.

Two regression tests first failed against the old implementation and then passed. The full Linux
Python 3.12 suite passed **327 tests**, the related Bluetooth/lifecycle subset passed 36, and Ruff and
whitespace checks passed. Deployed the changed `bluez.py` on top of the verified archive and reloaded
DeckPad. Subsequently rebuilt and deployed the complete archive as recorded below.

A subsequent real Bluetooth restart recovered to ON with no unobserved-Future warning in that run;
the Host was not HID-subscribed, so this is not proof of cleanup with active input delivery. Separately,
stopping Bluetooth produced RECOVERING; setting Controller Mode OFF canceled recovery. After
Bluetooth started again, DeckPad stayed OFF. Independent reads of the new daemon confirmed BlueZ's
own identity, interval 24–40 and no recovery journal. Pairing records remained present. Active Host
input/reconnect and unrelated peripheral coexistence still require their own acceptance checks.

### Current packaged artifact

Rebuilt clean source revision `e6064bb` with official Decky CLI 0.0.7 and its builder container.
`out/DeckPad.zip` includes the Disconnect write-result and adapter-identity recovery fixes. The 81-file verifier passed, including
byte-for-byte backend and notice comparison, API v1/root metadata, archive integrity and exclusion of
binary extensions and bytecode. SHA-256:
`e869b222a5af9f89f773e6122f600ce91a03116154e1b300a78c07c08fe2e3e2`.

Deployed this complete archive to the existing LCD installation and verified every deployed archive
file. Official individual-plugin reload succeeded; diagnostics from the new embedded Python 3.11.7
process report OFF, no error, BlueZ's own identity and interval 24–40. Quit Combo remains enabled;
the Host list is empty following the authorized fresh-pairing cleanup. The official builder rebuilt
the unchanged frontend successfully; its earlier typecheck and 14 behavior tests remain the frontend
evidence. The revised full Python 3.11.7 suite passes 334 tests in the Linux container. The temporary
build VM was removed and the original Docker context restored. No push or Store submission was performed.

### Fresh Mac pairing attempt

After the user's confirmation, removed only `steamdeck` from the Mac's Bluetooth settings and used
DeckPad's `forget_host` for that Mac. The Mac's other saved devices remained listed; DeckPad's Host
list and BlueZ's device list were empty afterwards. Started Controller Mode and Pairing Mode without
error. The Mac discovered `steamdeck` under Nearby Devices, but no HID subscription or completed
pairing has been observed yet.

The native UI tool can read the Bluetooth window and invoke accessibility buttons, but mouse and
scroll operations repeatedly returned `noWindowsAvailable`. Considered rebinding the app, raising
the window, direct coordinate interaction and a manual Connect action. Rebinding/raising did not
restore mouse control; the user was asked to click Connect as described in
[Apple's Bluetooth instructions](https://support.apple.com/en-nz/guide/mac-help/blth1004/mac).
This is a UI-tool blocker, not evidence that fresh Bluetooth pairing failed. Started a Deck-side
`btmon` capture at `/tmp/deckpad-mac-fresh-pairing.btsnoop` for the actual connection attempt.

The user subsequently clicked Connect, both before and after opening the DeckPad panel, and reported
continuous spinning. macOS 27.0.1's Bluetooth log records two BLE connection requests, each canceled
after about 31 seconds; it reports neither Classic nor LE paired for this device. The completed
200-second Deck capture contains no Connection Complete, SMP or ATT exchange. This establishes a
link-establishment failure, without identifying whether its cause is Host, radio or environment.

The user found DeckPad through the Decky QAM list. A real Steam CEF screenshot of
`QuickAccess_uid2` shows the DeckPad panel with Controller Mode ON, the live pairing countdown,
Cancel Pairing and Quit Combo controls. This verifies the panel's basic rendering; focus, complete
interaction, Controller Screen and clipboard acceptance remain open. A second capture from Session
startup confirms connectable/scannable legacy `ADV_IND`, public address, all three advertising
channels, HID UUID `1812`, Gamepad appearance and successful advertising enable. It still contains
no completed connection. Artifacts: `/tmp/deckpad-mac-pairing-retry.btsnoop` and `.txt` on the Deck.

Considered fresh bonds, reopening discovery, reducing interference/distance, resetting the Deck's
Bluetooth service and comparison with another Host. Fresh bonds and reopened windows did not
establish a link. Restarted only the Deck's Bluetooth service and reopened Pairing Mode; the resulting
195-second `/tmp/deckpad-mac-after-bt-restart.btsnoop` capture also contains no Connection Complete,
SMP or ATT exchange. No retry loop, protocol fallback or permanent system setting was added.

### Original release comparison on the same Mac — 2026-10-08

The user confirmed that v0.0.1 previously connected and delivered input on this same Mac. Downloaded
the original GitHub release ZIP, SHA-256
`b39980b57649eb500053674b9500b7b296910b65d9257e4ce0beb488b652b182`; all 73 packaged Python module
files present in the tag match `0299c0f`, and all 41 dbus-fast files match the current package.
Temporarily deployed the complete original archive after verifying Controller Mode OFF, original
DeviceID and interval 24–40. Preserved the rewritten plugin directory and settings separately.

The original release paired with the Mac successfully. The Deck capture confirms a successful
peripheral LE connection, SMP pairing, a HID Report CCCD subscription and input notifications.
The user confirmed connection success. Comparing the raw HCI command packets with the earlier
rewrite capture finds byte-for-byte identical initial advertising parameters, advertising data,
scan response and advertising enable commands: public address, legacy connectable/scannable
`ADV_IND`, 1280 ms interval, channels 37–39, HID UUID `1812`, appearance `03c4`, flags `06` and
name `steamdeck`. Neither version creates a separate virtual-controller Bluetooth address.

Restored the complete rewritten package and retained the newly established pairing. It briefly
connected and transmitted 845 HID notifications, then disconnected. Subsequent Forget and pairing
window operations appear in the backend log; the user reported spinning/failure. BlueZ logged
`remove_accept_list_complete(): Failed to remove device ... Invalid Parameters (0x0d)` at Forget.
This observation does not establish whether the failure originates in DeckPad, BlueZ or firmware.
The failed subsequent Mac connection attempt did not reach the pairing agent. A brief notification
stream is not evidence of a stable reconnection gate passing.

Completely closed and reopened the rewritten Controller Mode, then opened a fresh Pairing Mode.
The user confirmed successful connection that remained connected. Diagnostics confirm pairing,
HID notifications (7,493 after more than two minutes), active Controller Identity, 15 ms link interval and no
error. A scoped D-Bus monitor records `Agent1.RequestAuthorization`, not `RequestConfirmation`.
BlueZ 5.83's `device_confirm_passkey` routes Just Works (`confirm_hint` set) to authorization;
the original successful pairing also had confirm hint `01`. Therefore the rewritten rejection of
unseen numeric comparison is not implicated by these successful Mac pairing traces.

Mac IORegistry independently identifies `steamdeck` as a Bluetooth Low Energy HID device with
VID `045e`, PID `0b13`, version `0509`, Generic Desktop usage page `01`, Gamepad usage `05`,
and an attached `AppleGCHIDUserEventDriver`. This confirms that the connected device is the
emulated controller. The earlier accessibility text concatenated nearby device names; treating
`Health Scale` as steamdeck's device classification was unsupported and is withdrawn.

Artifacts on the Deck: `/tmp/deckpad-v001-ab.btsnoop`,
`/tmp/deckpad-rewrite-after-v001-bond.btsnoop`, `/tmp/deckpad-rewrite-clean-fresh.btsnoop`,
and the scoped agent captures. Local Mac logs and HID identity are under `/tmp/deckpad-*-ab-*`,
`/tmp/deckpad-rewrite-after-v001-mac-log.txt`, and `/tmp/deckpad-mac-current-hid.txt`.
The rewritten package is restored; the successful new Mac pairing is retained. No product code,
protocol fallback, adapter alias or permanent Bluetooth setting was changed for this comparison.
The cause of the earlier failure and repeatable Forget/re-pair reliability remain open; complete
button/axis mapping and the remaining hardware gates are not established by this comparison.

### Mac control capture — partial input acceptance, 2026-10-08

A temporary native Swift observer using Apple's GameController framework identifies the connected
`steamdeck` as category `Xbox One`. Background event delivery is explicitly enabled through
`GCController.shouldMonitorBackgroundEvents`; this is an observer-process setting, not a system
permission or plugin change. The completed four-minute capture records 193 input callbacks:
A/B/X/Y, LB/RB, View/Menu, all eight D-pad directions and both triggers reaching 1.0 and releasing
to 0.0. Recorded button presses release, and the last callback has no pressed button, neutral D-pad,
neutral sticks and released triggers. Artifact: `/tmp/deckpad-mac-input-v2.log` on the Mac.

Independent Deck HCI input notifications contain hats 0–8 and both trigger ranges 0–1023. Captured
stick values remain near center rather than demonstrating full travel. L3/R3, Guide and Share are
not present in this capture's button bytes. Those controls therefore remain unverified, with a
separate manual capture requested; their absence is not yet evidence of a mapping bug.
Artifact: `/tmp/deckpad-controls-acceptance.btsnoop`. The native observer and capture are temporary,
bounded diagnostic processes, not distributed dependencies or background services.

A real Steam CEF screenshot `/tmp/deckpad-controller-screen-mac.png` verifies the rendered
Controller Screen, connected Mac name, controller outline, trigger bars and Close control.
`SteamUIStore.BHomeAndQuickAccessButtonsEnabled()` returns false while that screen is open.
This proves the menu switch's current state, not that physical presses leave the Steam background
unchanged; that observation still requires the user's response. No automatic test substitutes
for full control mapping, focus isolation or Quit Combo acceptance.

The follow-up native Mac capture `/tmp/deckpad-mac-input-remaining.log` confirms all four stick
axes reaching -1.0 and +1.0 and returning to center, both analog triggers reaching 1.0 and
releasing, and L3/R3 and Share presses and releases. A simultaneous direct hidraw capture of
the Deck's own controller verifies the physical press bits; independent Bluetooth notifications
in `/tmp/deckpad-special-buttons.btsnoop` carry L3/R3/Guide (`70` in the second button byte)
and Share (`01` in the third byte), followed by released reports. The Mac receives L3/R3/Share;
Home/Guide does not appear in its GameController callback. Apple's `buttonHome` documentation
states that the system may consume that event before passing it to an application. Guide's
transport encoding is verified, but its application callback is not claimed as verified.
The user confirmed completing the requested presses with the Deck interface behaving normally.

The user then held Menu + View + L1 + R1 and confirmed exit and normal operation of both Steam
and Quick Access menus. Backend inspection confirms OFF, closed pairing, no advertisement,
inactive DeviceID override, original interval 24–40 and no error; the existing Mac pairing
remains. The Steam menu switch is true again. The Mac's final input callback is neutral,
with no pressed button or D-pad, centered sticks and released triggers. This verifies the
Quit Combo exit path; explicit Close, disabling Quit Combo and reload/unload UI paths remain
separate acceptance gates.

### QAM diagnostic clipboard — verified, 2026-10-08

The user opened Troubleshooting, Show Diagnostics and Copy Diagnostics in the real DeckPad panel
and reported `Copied to the clipboard.`. A read-only inspection of `QuickAccess_uid2` independently
shows the expected diagnostic rows, saved-file path and success message. Reading the actual CEF
clipboard yields a 6,313-character diagnostic report; its SHA-256 is
`0ebe2e6fb602dedf299c1a724657a146a06aaa3d07b763b0812ab479f17935a8`, exactly matching
`/home/deck/homebrew/logs/DeckPad/diagnostics.txt` (6,313 bytes). The report begins with
`DeckPad diagnostics,`. This verifies copied contents as well as the user-visible result, with
Controller Mode OFF and one retained Mac pairing. It does not independently establish which
of the existing copy helper's two write paths succeeded or prove its failure handling.

The subsequent clean reconnection test starts Controller Mode without reopening Pairing Mode or
deleting either pairing. The Mac establishes a subscribed HID link at 15 ms; diagnostics record
2,554 delivered reports with no error and no active advertisement. The user initially reported
that the Deck showed connected while Mac Bluetooth Settings did not. Mac logs independently record
connection retries and later `Device ready`; a subsequent native accessibility inspection shows
`steamdeck Connected - 100%`. The first Mac observer attaches an Xbox One controller but records
no input callbacks before finishing, so the initial link alone does not prove application input.
Artifacts: `/tmp/deckpad-mac-clean-reconnect.btsnoop`,
`/tmp/deckpad-clean-reconnect-diagnostics.json` and `/tmp/deckpad-mac-reconnect-input.log`.

A second native observer, `/tmp/deckpad-mac-reconnect-confirm.log`, subsequently records 242
input callbacks at the inspection point: right-stick movement reaches 1.0 and the right trigger
reaches 1.0 and releases to 0.0. Its last observed callback has neutral controls. This proves
application input after this reconnection, independently of DeckPad's notification counter.
A/B presses are not present in that observation. The initial UI disagreement and connection
retries remain unexplained; repeatable prompt reconnection is not claimed as passed.
Additional artifacts: `/tmp/deckpad-mac-clean-reconnect-log.txt`,
`/tmp/deckpad-reconnect-disagreement.json` and `/tmp/deckpad-reconnect-confirm.btsnoop`.

### Retained-bond automatic reconnect comparison — 2026-10-08

Three rewritten Controller Mode OFF/ON cycles retain the Mac pairing and keep Pairing Mode closed.
No Mac Connect operation is performed in these trials. HCI timestamps measure from
advertising enable to successful LE connection, followed by the Mac writing `0100` to HID CCCD
`020b` in every trial:

| Package / trial | Advertising to LE connection | Independent Mac observation |
| --- | --- | --- |
| Rewrite 1 | 45.055 seconds | Bluetooth Settings eventually shows Connected; the 40-second native observer ends before connection |
| Rewrite 2 | 1.299 seconds | Native GameController observer identifies steamdeck / Xbox One |
| Rewrite 3 | 19.371 seconds | Native GameController observer identifies steamdeck / Xbox One |
| Unmodified v0.0.1, retained bond | 63.037 seconds | Native GameController observer identifies steamdeck / Xbox One |

Before installing the original for this comparison, all 80 release files match its retained directory
byte for byte. The original also produces Mac connection-failed/retry logs before connecting.
Its first HCI advertising-parameter, advertising-data and scan-response commands (`2036`, `2037`,
`2038`) exactly match the rewrite's reconnect commands, including non-discoverable flags `04`.
This establishes delayed automatic reconnection in both packages in the current environment;
it does not identify the retry cause or explain every earlier manual Connect failure.
These trials do not verify physical input and do not substitute for input acceptance.

OFF diagnostics before both package swaps confirm inactive DeviceID override, original adapter
interval 24–40, no advertisement, retained pairing and no error. The rewrite is restored using the
official Loader reload; all 81 deployed files again match the packaged rewrite byte for byte.
Controller Mode is re-enabled with Pairing Mode closed. No product code or persistent Bluetooth
configuration changes are introduced by the comparison.

Artifacts: `/tmp/deckpad-three-reconnects.btsnoop` covers rewrite trials 1 and 2;
`/tmp/deckpad-reconnect-trial3.btsnoop` covers trial 3 until the intentional OFF at 127.353 seconds,
then also captures the original's startup. `/tmp/deckpad-v001-retained-bond-reconnect.btsnoop`
independently covers the original trial. Per-trial Mac logs and diagnostic reports are under
`/tmp/deckpad-reconnect-trial*` and `/tmp/deckpad-v001-retained-bond-reconnect-*`.

### Repeated official backend reload — 2026-10-08

After the Deck became reachable again, three `loader/reload_plugin` calls each stop an ON backend
and create a new OFF backend. The first begins with the Mac connected; the subsequent two begin
while the reconnect advertisement is waiting. Old PIDs `91537`, `93416` and `93578` each disappear
from `/proc`; each successor is the single DeckPad process. Loader remains PID `55562` and
bluetoothd remains PID `67844`. Each new backend reports no error, one retained Mac pairing,
Quit Combo enabled and the Steam menu switch enabled.

Separate read-only scans of bluetoothd's writable image after every reload find exactly one
original DeviceID and zero Xbox replacements. A separate MGMT socket reads adapter index 1 and
the original interval 24–40 every time. After the third reload, backend PID `93685` has no hidraw
file descriptor, no interval recovery journal remains, and BlueZ's `ActiveInstances` is zero.
Artifacts: `/tmp/deckpad-reload-pass{1,2,3}.json` and their `-readback.json` files on the Mac.

Controller Screen was closed before these checks and its menu switch was already enabled.
This verifies repeated backend process shutdown and system restoration; it does not establish
menu restoration from an open Controller Screen, frontend listener/route counts, active physical
input cleanup, forced-kill recovery or uninstall. The third reload returns Controller Mode to OFF.
It is subsequently re-enabled for the pending manual Close acceptance; the Mac pairing remains.

A subsequent read-only inspection of Loader's actual frontend state finds one DeckPad plugin
instance, exactly one `/deckpad/controller` route (including nested route arrays), and an empty
DeckPad event-listener map while Controller Screen is closed. The Steam menu switch is enabled.
Artifact: `/tmp/deckpad-frontend-after-reloads.json`. This verifies the state after the reloads;
it does not establish listener counts while the panel/screen is mounted or after every UI exit.

The real `QuickAccess_uid2` clipboard context is secure, currently unfocused, exposes
`navigator.clipboard`, grants `clipboard-write`, and reports legacy copy support. These read-only
capability checks do not identify the write path used by the successful earlier copy or establish
that either current copy path is redundant. No clipboard branch is removed on that evidence.

### Official uninstall with connected Mac — 2026-10-08

Before uninstall, the rewritten backend is ON, the Mac is connected and HID-subscribed, diagnostics
record 12,123 delivered reports at 15 ms, and Controller Screen is closed. The already verified
archive is staged outside installed plugins for reinstallation. Call `utilities/uninstall_plugin`
with `DeckPad`, the same backend route used by Decky's uninstall modal. Client elapsed time is
2,430.8 ms; the actual Loader journal records the plugin stopped in 2.4 seconds, below its five-second
stop deadline. The journal records backend stop and uninstall, with no forced-kill line in that check.

Independent post-uninstall checks confirm old PID `93685` is gone; the installed plugin directory,
paired-host record, Quit Combo settings, diagnostics file and interval recovery record are absent.
BlueZ no longer exports the Mac's device object and has zero paired devices. Read-only memory scan
finds one original BlueZ DeviceID and zero Xbox replacements; MGMT reads interval 24–40 on index 1,
and BlueZ reports zero advertising instances. Frontend inspection finds zero DeckPad plugin instances,
zero controller routes, no DeckPad event subscriptions and enabled Steam menus.

No unrelated peripheral was paired to the Deck, so real coexistence/isolation remains unverified;
its behavior tests are separate evidence. This successful run does not measure unavailable-Bluetooth
or failed-restoration uninstall timing, or menu restoration from an open Controller Screen.
Artifacts: `/tmp/deckpad-uninstall-before.json`, `/tmp/deckpad-uninstall-result.json`,
`/tmp/deckpad-uninstall-readback.json` and `/tmp/deckpad-uninstall-frontend.json`.

Reinstalled the same archive by moving its verified extracted files into the plugin directory and
using official `utilities/enable_plugin` registration. All 81 deployed files match the archive,
with generated probe bytecode removed before deployment. The embedded Python 3.11.7 backend starts
OFF without error, with inactive override, original interval, zero Hosts and default Quit Combo on;
the frontend again has one instance, one route and enabled menus. Settings and bond keys are not
restored after uninstall. The Mac retains its own stale bond and needs fresh pairing.
Artifact: `/tmp/deckpad-after-uninstall-reinstall.json`. This is local reinstallation of the verified
archive, not a Store installation or third-party approval.

### Uninstall while Bluetooth is unavailable — 2026-10-08

Stopping Bluetooth alone triggers automatic service activation in this environment. The first
attempt therefore uninstalls during RECOVERING with a newly running bluetoothd; its 109.8 ms result
does not verify unavailable-Bluetooth behavior. To establish that condition, temporarily mask only
`bluetooth.service` and its `dbus-org.bluez.service` alias with systemd `--runtime`, then stop the
service. Both runtime masks were absent before the test. `is-active` reports inactive, `MainPID` is
zero, and genuine embedded-runtime diagnostics show RECOVERING and `Bluetooth service: not running`.
Diagnostics generation itself succeeds in that state.

The official uninstall call completes in 109.8 ms; Loader records stop in 0.1 seconds. The plugin
directory, settings/Host records, saved diagnostics and interval journal are absent afterward, while
bluetoothd's PID is still zero. The frontend has zero plugin instances and controller routes and
enabled menus. There were zero Hosts: this verifies bounded uninstall and file/frontend cleanup
without Bluetooth, not removal of an existing inaccessible pairing.

Both temporary masks are removed in the test orchestration's `finally` cleanup, and Bluetooth is
started again. Independent readback confirms an active daemon with one original DeviceID, zero
Xbox overrides, interval 24–40, no runtime masks, and the original enabled service configuration.
Reinstall the identical 81-file package and register through official `utilities/enable_plugin`;
the embedded backend again starts OFF without error or retained Hosts. No permanent service-unit
change is made. Failed-restoration uninstall timing remains unverified on hardware.
Artifacts: `/tmp/deckpad-uninstall-masked-before.json`, `-result.json`, `-readback.json`,
`-restored.json` and `-reinstalled.json`, with the common `/tmp/deckpad-uninstall-masked` prefix.

### Adapter renumbering and interval recovery

After the interrupted run, kernel logs at 23:47:21 record a USB reset and reinitialization of the
Realtek adapter as `hci1`. BlueZ and MGMT both report the same controller address previously recorded
for `hci0`. DeckPad recovered to ON, but the old interval journal referenced index 0. Its restoration
failed with `Incomplete MGMT command write`; the journal remained and blocked new interval requests.
Independent MGMT readback on index 1 found the original range 24–40.

Revision `90ffbf1` saves the controller's public address in the transaction journal and resolves its
unique current index through MGMT Read Controller Index List/Read Controller Information. It checks
identity around interval operations and preserves the journal for missing/ambiguous identities,
external changes or failed readback. Index-only records are not guessed or automatically migrated.
Two tests first failed against the old implementation: restoration after renumbering and refusal to
restore a replacement controller at the old index. The revised 32 interval tests and full 334-test
Linux Python 3.12 suite pass. The updated uninstall fixture's 10 tests, Ruff and whitespace checks pass.

Deployed the revised interval module and reloaded the real embedded Decky process. Archived the old
index-only journal at `/home/deck/DeckPad-interval-index-only-before-90ffbf1.json` only after checking
controller identity and the original range independently. On `hci1`, the new code requests 12–16
while ON, saves an address-based journal, and restores 24–40 while OFF. The journal is then absent;
diagnostics report BlueZ's own identity. Current mode is OFF, with no paired Hosts. Automatic
renumbering recovery of this new revision still needs a separate real reset test. The subsequently
rebuilt and fully deployed ZIP includes this fix, as recorded under Current packaged artifact.

### Real pairing-window timeout — incomplete reconnect gate

On the current complete archive, opened Pairing Mode and allowed the actual 180-second deadline to
expire without accepting a new Host. Snapshots showed discoverable with 180, 109 and 46 seconds
remaining, then failed with `pairing_timed_out`, no candidate and no remaining deadline. During the
window BlueZ reported one LE advertisement, Classic Discoverable stayed false, and MGMT used the
original interval 24–40. The existing Host record remained intact.

At timeout the discoverable advertisement was withdrawn and interval 12–16 requested again, but
registration of the reconnect advertisement failed. DeckPad exposed `reconnect_unavailable`, with
BlueZ ActiveInstances zero. Bluetooth logs reported `Failed to add advertisement: Failed (0x03)`;
kernel logs at the same time reported `Unexpected advertising set terminated event` and opcode
`0x2039` failure `-38`. The link monitor had recorded a peripheral link during the window, while the
persisted Host's Device1 fact remained disconnected. Its identity and relationship to the failed
advertisement are not established.

An immediate ON / open Pairing Mode / close Pairing Mode sequence subsequently succeeded without the
registration error. This does not resolve the failed timeout/reconnect acceptance gate. No delay,
retry, fallback registration or kernel change was added based on an unproven cause. A short btmon
capture of this successful sequence is retained on the Deck at
`/tmp/deckpad-advertising-failure.btsnoop`; it does not capture the initial failure. OFF then restored
the original identity and interval; BlueZ ActiveInstances was zero. Fresh pairing and active Host
input remain pending.

Repeated the complete 180-second window with a 210-second HCI capture
(`/tmp/deckpad-timeout-reproduction.btsnoop` on the Deck). This run contained no Connection Complete
events and no failed MGMT/HCI statuses. At timeout the pairing error was `pairing_timed_out`, the
reconnect advertisement was connectable with BlueZ ActiveInstances one, and interval 12–16 was
restored. OFF then succeeded. This proves the no-new-link timeout path on this setup, not the prior
failure that followed an observed peripheral link. The inconsistent kernel advertising state still
needs a reproduction with the Host connection identified; no production change was justified by the
successful run alone.

## Module review

Reviewed the final responsibilities, callers and cleanup paths. Protocol values and stable external
interfaces stay explicit; no proxy framework, new daemon, compiled backend, state library or UI library
was added. Each row records why the retained mechanism is necessary and the check that constrains it.

| Module | Responsibility and simplest retained mechanism | Evidence / limit |
|---|---|---|
| `device_id.py` | One `/proc` write boundary, exact BlueZ version, unique image match, process/byte checks and verified restore/short-write rollback | Fault injection plus current LCD ON/OFF, reload and manual crash-restoration readbacks; automatic recovery through Loader remains unproven |
| `connection_interval.py` | MGMT range transaction; synced original journal, write/readback, compare before restore, retain failed recovery | Malformed packet/TLV/status and recovery faults; no speculative overwrite |
| `bluez.py` | One bounded message-call entry; remaining functions map directly to BlueZ methods | Bus timeout, loss, transport and cancellation tests; no introspection proxy |
| `hci_socket.py` | One Linux socket/bind boundary with declared libc ABI and six-byte address | ABI/layout and close-on-failure tests; actual embedded runtime opened MGMT/HCI sockets during the LCD checks |
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
| `__init__.py` | Add the vendored XML path only for missing `xml.etree` | Stripped interpreter subprocess and unrelated missing-module test; current archive loaded in Decky's genuine embedded Python 3.11.7 |
| `backend.ts` | Sole RPC/event boundary; live events beat initial query, stale callbacks ignored; preview watcher count owns subscription | Initial/event race, unmount and overlapping watcher tests |
| `controller_screen.tsx` | Official router/navigation/focus; retain the exact private menu switch until restoration succeeds | Partial disable, changed store, failed restore, touch close and dismount tests; hardware menu/chord checks pending |
| `index.tsx` | Render backend facts using official components; one shared request handler | All QAM action paths clear old transport errors; backend errors remain backend-owned |
| `troubleshooting.tsx` | Local expanded state and latest diagnostics request; ignore results after hide/unmount | Overlapping queries and pending failure tests; both existing Clipboard paths retained until CEF measurement |
| `gamepad_outline.tsx` | Steam artwork access stays inside this component, with the existing minimal preview if absent | Reviewed mappings; hardware artwork and Steam version compatibility pending |
| Metadata, dependencies, build | ESM, API v1/root, official `deckyPlugin()`, pinned vendored pure Python with licenses | Frozen lockfile, official archive/content verification; root justified by `/proc` memory, MGMT and HCI access. 2026-10-27: repository metadata assertion tests removed; the archive verifier still checks API version, root flag and packaged contents. |
| `tests/support` | Fake only external D-Bus/controller/MGMT interfaces; shared asynchronous wait functions | Removed migration stubs and duplicate waits; test scenarios reuse existing behavior fixtures |

## Current compatibility boundaries

| Environment / interface | Current status |
|---|---|
| BlueZ 5.83 DeviceID | Explicitly allowed after process/unique-byte checks; current LCD ON/OFF and recovery readbacks verified, with fault-injection tests for safety paths |
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
current LCD checks are recorded above; the remaining HID and UI acceptance gates are still open.

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
| macOS 27.0.1 (same Mac, rewritten package) | Fresh pairing, native core-button/axis/trigger/L3/R3/Share input, Xbox BLE identity and driver verified; three automatic retained-bond reconnects establish HID subscriptions, with variable latency also observed in original v0.0.1; Guide application callback, repeated manual Connect and Forget/re-pair reliability remain open |
| Windows 10/11, iOS/iPadOS, Android, ChromeOS | Untested |
| Game consoles, smart TVs | Untested |
| Steam Deck OLED (as the controller) | Untested |

## Historical findings and open unknowns

| # | Unknown | Status |
|---|---|---|
| U1 | Which Device Information Service PnP ID each Host OS uses. bluetoothd publishes its own DIS (`1D6B:0246`) before DeckPad's, and a Linux Host built its first gamepad from it. | Linux and macOS expose `045E:0B13` with the runtime override ([ADR-0006](adr/0006-override-bluetoothd-deviceid-in-memory.md)). macOS IORegistry confirms version `0509` and its Apple game-controller driver. Windows, iOS and Android remain untested. |
| U2 | Whether a shorter LE connection interval can be requested, and whether Hosts accept it. | The Linux Host settles at 18.75 ms ([ADR-0008](adr/0008-shorter-connection-interval-and-link-paced-reports.md)); 3 of 13 earlier updates were followed by a link drop. The Mac's new successful pairing settles at 15 ms with sustained notifications. Other Hosts remain untested. |
| U3 | Coexistence with Bluetooth headphones, keyboards or controllers paired to the Deck while a Host is connected (audio dropouts, throughput). | Open. Needs real peripherals and a person listening. |
| U4 | Whether Steam's UI on the Deck reacts to presses during Controller Mode, and whether a full-screen route can absorb them. | Mostly resolved on the Deck (SteamOS 3.8.28, Gaming Mode). The Controller Screen ([ADR-0011](adr/0011-controller-screen-route.md)) absorbs the presses: a person pressed every core control and nothing behind it moved. The first build also swallowed the Steam and `…` buttons, so the user could not leave. Now, while the Quit Combo ([ADR-0012](adr/0012-quit-combo.md)) is on, the screen turns those two buttons' menus off with Steam's own switch ([ADR-0014](adr/0014-turn-off-steams-menu-buttons-on-the-controller-screen.md)): pressing them opened nothing, and holding the Quit Combo closed the screen and turned Controller Mode off. **Close** (touch), Controller Mode turning off, and switching the Quit Combo off all turn the menus back on. The screen's drawing of what the Host receives ([ADR-0013](adr/0013-draw-the-host-view-with-steams-controller-outline.md)) lit up correctly for every control. Open: whether Steam's chords on the Steam button (holding it, Steam + B) still work while the screen is open. |
| U5 | Whether dbus-fast loads in Decky's embedded Python. | Resolved: Decky's Python 3.11.7 lacks `xml.etree`, and DeckPad ships CPython's copy as a fallback (`py_modules/_stdlib`). |
| U6 | Rumble from Windows/SDL Hosts, and Deck haptics. | Open, out of scope for now: output reports are accepted and dropped. |
| U7 | Dual-mode Hosts (Android, Windows) deriving a Classic link key and then trying a Classic connection to the Deck. | Open. To be observed during U1 tests. |
| U8 | Suspend and resume with a Host connected. | Open. |
| U9 | Steam Deck OLED (different Bluetooth chip). | Open. No hardware available. |
| U10 | Whether Steam marks every device it pairs as trusted. DeckPad's agent refuses `AuthorizeService` for paired but untrusted devices that are not Paired Hosts while Controller Mode is on ([ADR-0005](adr/0005-borrow-default-pairing-agent.md)). | Open. If Steam leaves some devices untrusted, they cannot use the Deck's services while Controller Mode is on. |
| U11 | Uninstall from Decky's settings removes the Paired Hosts' pairings within Decky's shutdown deadline. | Verified on the Deck through Decky's own uninstall call, with Controller Mode on and the Host connected: the Host was disconnected, its pairing removed, `paired_hosts.json` and `diagnostics.txt` deleted, and the interval restored, in 2.0 s. That other paired devices stay paired is covered by automated tests only, because no other device was paired to the Deck. |
