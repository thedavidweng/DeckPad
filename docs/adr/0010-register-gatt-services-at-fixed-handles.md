# Register DeckPad's GATT services at fixed handles

DeckPad sets the `Handle` property of each `GattService1` it registers: the HID service at `0x0200`, Battery at `0x0230` and Device Information at `0x0240`. bluetoothd places the characteristics of each service in order after it, so a Paired Host sees the same attribute layout in every Controller Mode session. If another application already holds that range, `RegisterApplication` fails, and DeckPad registers again with `Handle` 0 so bluetoothd picks the handles (and logs a warning).

Without fixed handles, a Paired Host got no input after Controller Mode was turned off and on. Two BlueZ 5.83 behaviours combine:

1. bluetoothd gives a service without a requested handle `last_handle + 1`, and `last_handle` never goes down. Each registration moved DeckPad's 23 attributes up by 23 (on the Deck the HID service went `0x071c`, `0x0733`, `0x074a` over three cycles).
2. bluetoothd computes the Database Hash with a single `writev` that has one iovec per handle. Linux rejects more than 1024 iovecs (`UIO_MAXIOV`) with `EINVAL`, so once handles pass 1023 the hash stops changing.

On reconnect, bluetoothd sent Service Changed before the Host's GATT client was listening for it, so the indication was lost. The Host then read the Database Hash, found it equal to its cached one, skipped discovery, and kept reading handles that no longer existed (Invalid Handle). It never subscribed to the input report, so DeckPad sent nothing. All handles chosen here stay below 1024, which also keeps the hash computable on a freshly started bluetoothd.

## Considered Options

- **Let bluetoothd pick the handles** (the earlier behaviour). Rejected: it is the cause above.
- **Rely on Service Changed.** Rejected: bluetoothd sends it too early for the Host to receive it, and DeckPad cannot change that timing.
- **Restart bluetoothd to reset `last_handle` and the hash.** Rejected: it drops the user's headphones and other devices each time.

## Consequences

- Verified on the Deck with the Linux Host: across three Controller Mode off/on cycles the Host reconnected by itself, subscribed, and received input each time, with the HID service at `0x0200-0x020f` in every session.
- A Host that bonded with a DeckPad build from before this change, on a bluetoothd whose hash had already frozen, keeps its stale cache. It must remove the Deck and pair again once; restarting Bluetooth on the Deck also clears the frozen hash. The README lists this as a known limitation.
- The fallback (`Handle` 0) brings the original problem back for that session. It only happens if another GATT application on the Deck claims the same handles.
- Adding attributes to the HID service must keep it inside `0x0200-0x022f`, below the Battery service.
