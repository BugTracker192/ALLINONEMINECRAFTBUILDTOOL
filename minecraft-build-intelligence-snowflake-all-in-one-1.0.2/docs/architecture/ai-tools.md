# Grounded AI Tools

The provider-independent tool layer exposes exact reads, structural analyses, render requests, planning artifacts, bounded geometry operations, transaction controls and verified export.

Live provider requests include literal PNG data and exact tools. A requested render is attached to the next turn. Patch previews attach before/after crops, and committed patches attach a changed-area render.

The JSON CLI bridge accepts either one operation:

```json
{"tool":"get_block","arguments":{"position":[10,25,-4]}}
```

or a batch:

```json
{
  "requests": [
    {"tool":"begin_patch","arguments":{}},
    {"tool":"preview_patch","arguments":{"patchId":"$last_patch_id"}},
    {"tool":"commit_patch","arguments":{"patchId":"$last_patch_id"}}
  ]
}
```

Model output is never executed as code. All paths, bounds, counts, states, preconditions and NBT edits are validated server-side/in-process.
