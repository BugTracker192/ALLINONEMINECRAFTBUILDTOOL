# Security architecture

All inputs are untrusted. Compressed and decompressed byte limits, NBT depth/count/array/string limits, checked volumes, strict varints, ZIP traversal/duplicate/file limits, model-parent limits, upload hashing, isolated workers, and server-side tool validation are mandatory. Production must add per-project authorization, rate limits, encrypted credentials, signed artifacts, OTel redaction, and sandbox profiles.
