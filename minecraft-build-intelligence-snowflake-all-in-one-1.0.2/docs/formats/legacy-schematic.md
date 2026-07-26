# Legacy `.schematic`

Index order is `y*width*length + z*width + x`. `Blocks` supplies low eight ID bits; `AddBlocks` supplies the low nibble for even voxel indexes and high nibble for odd indexes; `Data` supplies metadata. Only explicit version-safe mappings resolve automatically. Unknown `(numeric ID, metadata)` pairs become `legacy:numeric_<id>[data=<n>]` with source fields and diagnostics, never silent air.
