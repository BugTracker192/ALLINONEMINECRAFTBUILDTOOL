# Resource Packs

The reader accepts a directory, ZIP, JAR or equivalent legal asset archive. Archive members are read directly rather than extracted.

Rejected conditions include traversal, absolute paths, symlinks, duplicates, encryption, excessive member count, decompressed-size excess, suspicious compression ratios, oversized JSON, model-parent cycles, excessive multipart branches and oversized/malformed PNGs.

The resolver supports both the standard `assets/<namespace>/...` layout and namespace-root archives such as `<namespace>/blockstates/...`. Modern texture objects containing `sprite` and `force_translucent` are supported.
