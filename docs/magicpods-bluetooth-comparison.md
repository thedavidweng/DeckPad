# MagicPods Bluetooth comparison — 2026-10-09

This comparison reads MagicPodsDecky commit
[`ada6e98`](https://github.com/steam3d/MagicPodsDecky/tree/ada6e98a62a881cfd6ba6070b4a58c6a323c8cc2)
and its pinned MagicPodsCore submodule
[`d799715`](https://github.com/steam3d/MagicPodsCore/tree/d7997154d57bd952bd3772ddcddb2116b102d394).
Neither project was built, installed or run for this comparison.

## Different Bluetooth roles

| Responsibility | MagicPods | DeckPad |
|---|---|---|
| Connection direction | Deck connects to headphones through BlueZ `Device1.Connect` | Mac connects to Deck's connectable BLE advertisement |
| Services | Existing headphone/audio services and optional L2CAP/RFCOMM control sockets | Plugin-owned HID GATT application, report subscription and notification delivery |
| BLE advertisements | Receives headphone manufacturer data through discovery | Publishes HID UUID, gamepad appearance and name |
| Connection status | Reads BlueZ `Connected` and reacts to property changes | Also reads BlueZ `Connected`; actual HID readiness additionally requires report subscription |
| Bluetooth power recovery | Restarts desired discovery after `Powered=true` | Discards the lost peripheral session and rebuilds it after Bluetooth returns |
| Device identity | Uses the headphone's identity | Overrides bluetoothd's built-in Device Information identity to match the gamepad |
| Process architecture | Decky Python starts a compiled C++ backend with a separate WebSocket API | Official Decky Python process, asyncio and Decky RPC/events |

The current MagicPodsCore constructor selects `DBusBasedBleAdvertisingService`.
Despite the class name, its `StartScan` calls `SetDiscoveryFilter` and `StartDiscovery`;
it does not register a local advertisement or GATT application. Its alternate passive HCI
implementation also receives advertisements. These paths cannot establish the reliability
of DeckPad's peripheral role.

Sources: [device connection](https://github.com/steam3d/MagicPodsCore/blob/d7997154d57bd952bd3772ddcddb2116b102d394/src/dbus/DBusDeviceInfo.cpp),
[selected BLE implementation](https://github.com/steam3d/MagicPodsCore/blob/d7997154d57bd952bd3772ddcddb2116b102d394/src/DevicesInfoFetcher.cpp),
[discovery and power recovery](https://github.com/steam3d/MagicPodsCore/blob/d7997154d57bd952bd3772ddcddb2116b102d394/src/ble_ads/DBusBasedBleAdvertisingService.cpp),
[backend lifecycle](https://github.com/steam3d/MagicPodsDecky/blob/ada6e98a62a881cfd6ba6070b4a58c6a323c8cc2/main.py).

## What its disconnect fix actually does

MagicPods' `fix_disconnects` setting calls its Python `play` method when headphones
are present. `Player.start` runs `ffplay` in a loop on `silence.mp3`, keeping audio active
to prevent headphone standby. This does not repair BLE link establishment or HID pairing.

The frontend's four-second reconnect loop reconnects its WebSocket to the C++ backend,
not the headphone's radio connection. The control socket has an attempt loop, but its
current `CONNECTION_TO_SOCKET_ATTEMPTS_NUMBER` is **1**. There is no evidence here that
an aggressive radio retry policy explains MagicPods' perceived stability.

Sources: [setting and playback triggers](https://github.com/steam3d/MagicPodsDecky/blob/ada6e98a62a881cfd6ba6070b4a58c6a323c8cc2/src/player.tsx),
[silent playback](https://github.com/steam3d/MagicPodsDecky/blob/ada6e98a62a881cfd6ba6070b4a58c6a323c8cc2/py_modules/mp/player.py),
[WebSocket reconnect](https://github.com/steam3d/MagicPodsDecky/blob/ada6e98a62a881cfd6ba6070b4a58c6a323c8cc2/src/backend.tsx),
[socket attempt count](https://github.com/steam3d/MagicPodsCore/blob/d7997154d57bd952bd3772ddcddb2116b102d394/src/client/Client.h).

## Relevant limits and lessons

Both projects use BlueZ property events rather than treating a successful Connect request
as the full application-level result. DeckPad already watches adapter removal, power loss,
BlueZ service ownership loss and its watch-bus disconnection. MagicPods' inspected adapter
proxy is hard-coded to `/org/bluez/hci0`; this Deck currently uses `hci1`. Copying that
selection would regress the adapter-identity work already verified in DeckPad.

Neither inspected implementation has an explicit logind `PrepareForSleep` handler.
DeckPad's watch cannot detect a sleep/resume cycle that leaves its observed D-Bus service,
adapter object and `Powered` property intact. That is a lifecycle coverage gap, not yet
proof that it causes this connection failure. A controlled before/after suspend test must
establish which registration or controller state changes before choosing a repair.

For UI accuracy, `Device1.Connected` proves a Bluetooth link, while a subscribed HID report
characteristic proves that a Host has requested gamepad notifications. DeckPad's diagnostics
already expose report delivery separately, but its connection badge derives only from the
BlueZ link. This explains how the Deck can say connected before the Mac has a usable gamepad;
it does not explain why a link fails to establish.

Sources: [MagicPods adapter selection](https://github.com/steam3d/MagicPodsCore/blob/d7997154d57bd952bd3772ddcddb2116b102d394/src/dbus/DBusService.cpp),
DeckPad `bluetooth_watch.py`, `controller_mode.py`, `connections.py` and `peripheral.py`.

## Today's device evidence

- Two fresh pairing attempts on the rewrite failed: first with the previous day's session,
  then after a complete Controller Mode OFF/ON cycle. Mac GameController observers found
  zero controllers. The complete Deck HCI captures contain no LE connection-established,
  SMP pairing or ATT exchange events during those attempts.
- The first Mac log reports a brief LE connection, then remote-version retrieval fails
  with Apple's status 762 and the link disconnects about 0.2 seconds later. The numeric
  Apple status is not assigned a Bluetooth-spec meaning without an authoritative mapping.
- The unmodified original v0.0.1 also failed in the same environment today. All 80 original
  release files were verified against release ZIP SHA-256
  `b39980b57649eb500053674b9500b7b296910b65d9257e4ce0beb488b652b182` before loading it.
  This contradicts a rewrite-only explanation for today's failure; it does not dismiss
  earlier successful original-release tests or prove that both versions have identical bugs.
- The Deck kernel records suspend/resume at 13:28:52 local time, before the attempts,
  and unexpected advertising-set-terminated events at pairing timeout. Temporal proximity
  is evidence for a controlled suspend comparison, not causation.
- Restored the rewrite and verified all 81 archive files. With Controller Mode OFF,
  BlueZ's official power interface successfully changed the adapter from false to true.
  The user initially reported a persistent connection, then corrected that observation:
  it had not connected. Independent readback showed zero Hosts and zero native Mac
  controllers. A subsequent readback reached
  `pairing_timed_out` with zero Hosts; the completed 240-second Deck capture contains no
  LE connection-established, SMP or ATT exchange events. Successful HID pairing/input
  failed; the native observer completed with zero controllers. The adapter power cycle
  did not fix this attempt.

Local evidence: `/tmp/deckpad-fresh-pair-20261009.txt`,
`/tmp/deckpad-clean-session-pair-20261009.txt`,
`/tmp/deckpad-mac-fresh-pair-20261009-bluetooth.log`,
`/tmp/deckpad-original-fresh-pair-20261009-diagnostics.json`,
`/tmp/deckpad-adapter-cycle-pair-20261009-result.json` and the corresponding bounded
Mac observer logs and Deck btsnoop captures. These are diagnostic artifacts outside the
repository, not a substitute for reproducible acceptance.

No silent-audio workaround, custom backend, global auto-reset, speculative retry policy
or production code change was introduced. The next useful evidence is matching Mac HID
attachment and a press/release with the Deck link, followed by a controlled suspend test.
