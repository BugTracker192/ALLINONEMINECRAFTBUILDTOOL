# Offline CLI

Run `python -m app.cli --help` for the complete command tree. Stable exit-code families:

- `0`: success.
- `2`: invalid command/request.
- `10–12`: format, NBT or safety-limit failure.
- `20`: canonicalization/query failure.
- `30–31`: render or strict-asset failure.
- `40–41`: patch validation or stale-precondition failure.
- `50–51`: export or exact round-trip mismatch.
- `60`: optional provider failure.
