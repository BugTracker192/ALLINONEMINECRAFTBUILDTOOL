# Canonical model

Source format details terminate at adapters. Canonical coordinates are document-global integers; a cell `(x,y,z)` occupies `[x,x+1] × [y,y+1] × [z,z+1]`. Palette properties are sorted lexicographically for hashing. Unknown valid data is retained in extension containers and unsupported visuals use diagnostics rather than data deletion.

Sparse `BuildDocument.blocks` is the in-process reference model. Storage is 16³ immutable chunk blobs with deterministic encoding selection and hashes. Production manifests map an immutable build version to chunk hashes; databases do not store one row per block.
