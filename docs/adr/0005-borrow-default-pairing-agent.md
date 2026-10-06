# Borrow the default pairing agent only while Controller Mode is on

While Controller Mode is on, DeckPad registers its own `NoInputNoOutput` BlueZ agent and calls `RequestDefaultAgent`. It unregisters the agent when Controller Mode stops. Pairing that a Host initiates is always routed to the default agent. Steam already registers one with display capability, so without ours, pairing on hardware either showed numeric-comparison prompts or stalled and timed out. BlueZ 5.83 keeps default agents on a stack (`default_agents` queue in `src/agent.c`), so removing ours restores Steam's agent. We never edit Steam's agent or any system configuration to achieve this.

## Consequences

- While Controller Mode is on, any device pairing with the Deck goes through DeckPad's agent. This includes a user who opens Steam's Bluetooth settings at the same time. The agent must only auto-accept while Pairing Mode is active, and reject otherwise.
- The same applies to `AuthorizeService`, which bluetoothd sends to the default agent before a paired but untrusted device may use a local service. DeckPad's agent allows it only while Pairing Mode accepts new Hosts, or for a Host in DeckPad's Paired Host record, and rejects it otherwise. Trusted devices are never asked about. Whether Steam marks every device it pairs as trusted has not been checked on hardware (U10 in [Verification status](../verification.md)); a paired device that Steam left untrusted would be refused while Controller Mode is on, and turning Controller Mode off hands the question back to Steam's agent.
- "Just Works" LE pairing is unauthenticated (no MITM protection). That is normal for game controllers, but it is why Pairing Mode should be explicit and time-limited.
