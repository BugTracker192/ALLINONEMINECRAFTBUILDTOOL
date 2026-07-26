# Chunk storage

Chunk coordinates use floor division, including negative coordinates. Local index is `x + z*16 + y*256`. Encodings are single-value, sparse `(uint16 index,uint32 palette)`, uint8/16/32 dense, or deterministic RLE. The shortest byte representation wins with a stable encoding-name tie break. Blob hash includes encoding name and bytes.
