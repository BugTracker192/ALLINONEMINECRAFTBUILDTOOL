# Private bundled Minecraft assets

This private all-in-one delivery embeds the exact user-supplied `minecraft.zip` at:

`app/bundled_assets/minecraft.zip`

The CLI, Python renderer, AI tool bridge, autonomous build loop, patch previews, and snapshot
workflows auto-select it when no explicit resource-pack path is supplied. Resolution order is:

1. Explicit `--resource-pack` / Python argument.
2. `MBI_RESOURCE_PACK` environment variable.
3. The bundled archive.
4. A nearby `minecraft.zip` or `resourcepack.zip`.

Set `MBI_DISABLE_BUNDLED_ASSETS=1`, or pass `--resource-pack none`, only when deterministic flat
rendering is intentionally required.

The archive is read directly and never extracted. Existing traversal, symlink, duplicate-entry,
encryption, member-count, decompression-size, compression-ratio, JSON, model-depth, and texture-size
limits remain active.

These user-supplied proprietary assets are included only in this private deliverable. Do not publish
or redistribute this archive without authorization from the relevant rights holder.
