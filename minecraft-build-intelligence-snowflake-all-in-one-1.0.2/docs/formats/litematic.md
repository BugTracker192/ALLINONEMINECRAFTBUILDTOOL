# `.litematic`

Regions remain first-class. Signed size normalization per axis:

- positive: `min=position`, `max=position+size-1`
- negative: `min=position+size+1`, `max=position`

Bits per entry are `max(2, ceil(log2(max(1,paletteSize))))`. NBT signed longs are masked to unsigned 64-bit words before extraction. Cross-word values combine the low shifted first word and high shifted second word. Asymmetric and bit-boundary tests prevent axis and packing regressions.

The flattened view currently applies sorted-region-name last-write and reports overlaps while retaining source region metadata. The exporter currently emits one deterministic region; preserved multi-region export remains a release gate.
