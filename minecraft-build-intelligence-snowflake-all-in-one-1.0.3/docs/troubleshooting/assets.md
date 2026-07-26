# Resource-pack troubleshooting

`ASSET_PACK_NOT_CONFIGURED` means the API does not point at the indexed directory. Run the asset index script and set `MBI_ASSET_PACK_PATH` to the directory containing `minecraft/blockstates`, `minecraft/models`, and `minecraft/textures`. Missing models/textures are rendered as visible deterministic fallbacks and reported in the inspector.
