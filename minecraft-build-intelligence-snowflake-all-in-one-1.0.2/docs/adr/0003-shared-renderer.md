# ADR 0003: Shared browser/headless renderer

**Status:** accepted.

The renderer-service loads the same web renderer with Playwright instead of maintaining a second visual implementation. Snapshot manifests include renderer and asset hashes to expose drift.
