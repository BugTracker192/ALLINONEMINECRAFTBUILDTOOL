# Sponge `.schem`

Adapters are version-specific. Version 3 reads the nested `Schematic` compound, unsigned 16-bit dimensions, `Offset`, `Blocks.Palette`, varint `Blocks.Data`, block entities, entities, metadata, and extension fields. Linear index is `x + z*Width + y*Width*Length`. Strict decoding requires exactly `Width*Height*Length` values and rejects overflow, unterminated values, extra values, gaps, duplicates, or out-of-range palette IDs.

Export writes deterministic Sponge v3, contiguous lexically ordered states with air first, stable gzip timestamp zero, then re-imports and compares every relative coordinate/state.
