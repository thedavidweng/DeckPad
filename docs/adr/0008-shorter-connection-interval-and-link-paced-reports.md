# Ask Hosts for a 15-20 ms connection interval and pace Gamepad Reports from the live interval

On the tested Deck, an LE link carries about one GATT notification per connection event. BlueZ queues any notifications beyond that without limit, so a report sent faster than the link can carry it adds latency that never goes away. The tested Host (a Linux laptop) picks a 48.75 ms interval. At that interval, 25 reports/s already drifted by about 1.5 s over two minutes, and 60 reports/s delivered about 21/s with more than a second of backlog.

While Controller Mode is on and Pairing Mode is not accepting new Hosts, DeckPad asks Hosts for a 15-20 ms interval. It does this by setting the adapter's default LE connection interval range to 12-16 (in 1.25 ms units) with the MGMT Set Default System Configuration command (TLVs `0x0017`/`0x0018`, root only). When a Host connects with an interval outside that range, the kernel sends it an L2CAP Connection Parameter Update Request for the range (`l2cap_le_conn_ready`). The tested Host accepted every request and moved to 18.75 ms. At that interval it received 42-45 reports/s with no backlog over 60 s. The previous range is saved to a file in the plugin's runtime directory before it is changed. It is put back when Pairing Mode opens, when Controller Mode stops, or when the plugin unloads, and also on the next start if DeckPad was killed first. The request is dropped before the pairing advertisement goes up and returns once Pairing Mode closes. A Host that pairs therefore keeps its own interval for that first connection, paced to it, and gets the shorter interval when it next reconnects.

The Host picks the interval and may refuse the request. BlueZ's D-Bus API does not expose the interval either. DeckPad therefore reads it from the controller's HCI events (LE Connection Complete, Enhanced Connection Complete, Connection Update Complete, and Disconnect Complete) on a raw HCI socket filtered to those events. It sends at most one Gamepad Report per connection event of the slowest connected Host, plus a 15% margin. Until an interval is known, it sends at most one report every 60 ms.

## Transaction safety

The interval change is a recoverable transaction. `storage.save` atomically replaces and syncs the
original-value record before MGMT is allowed to change the adapter. A successful set reply is followed
by a readback. Lost replies and verification failures trigger restoration; if that fails, the record
survives, including during uninstall. Restoration first reads the current range: an already-restored
range is accepted, DeckPad's requested range may be restored, and any other range is left untouched
with its recovery record retained. New requests cannot replace an unresolved record. MGMT packets
must match their declared lengths, successful command completion, and well-formed, unique TLVs;
interval values and persisted adapter addresses are validated before use. The recovery record saves
the controller's public address, not its transient `hciN` index. MGMT Read Controller Index List and
Read Controller Information resolve that address uniquely before restoration; identity is checked
again around the configuration read/write. A reset can renumber the same controller. A missing or
ambiguous controller retains the record, and an index-only old record requires manual identity and
range verification rather than guessing which adapter to write. This follows the
[BlueZ management protocol](https://github.com/bluez/bluez/blob/master/doc/mgmt-protocol.rst).

## Considered options

- **Keep the Host's interval (no request).** Robust, but it limits throughput to about 18 reports/s with roughly 55 ms between reports.
- **8.75-11.25 ms (range 7-9).** The Host accepted it (11.25 ms) and 100 reports/s were delivered on time. But 3 of 7 updates were followed by a Connection Timeout drop, and a fresh pairing failed. Rejected.
- **15-20 ms (range 12-16), also while pairing.** The first version. Only about 4 of 9 fresh pairings succeeded, because the switch happened in the middle of SMP pairing. Rejected.
- **15-20 ms (range 12-16), except while Pairing Mode accepts Hosts.** Chosen. It carries about 45 reports/s, which is enough for a gamepad whose state changes are coalesced (latest state wins).

## Consequences

- On the tested Host, 3 of 13 updates to 18.75 ms were followed by a Connection Timeout drop exactly one supervision timeout (420 ms) after the update instant. Links that survived the instant stayed up for minutes. A drop during a reconnect recovered within about 3 s, because the Host reconnected by itself. A drop during a fresh pairing would cancel the pairing (`AuthenticationCanceled`), which is why the request is held off while Pairing Mode is open. With that change, every pairing whose connection reached the Deck succeeded (3 of 3; one more attempt failed on the laptop before it connected). The supervision timeout in the request is the one the Host chose, so the Deck's own `le_supv_timeout` default does not change it. If other Hosts show the same drops on reconnect, the next steps are to have the Peripheral send HCI LE Connection Update itself once the link is up, or to stop requesting the shorter interval.
- The default range is adapter-wide. It also applies to Steam's own LE connections, but only while Controller Mode is on.
- Without root, both features are skipped and DeckPad paces at the fallback 60 ms.
- Decky's bundled Python has no Bluetooth support in `socket`. Both sockets are created by address-family number and bound through libc with a packed `sockaddr_hci`.
