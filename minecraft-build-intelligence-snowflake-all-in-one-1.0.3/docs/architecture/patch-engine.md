# Patch engine

Patches declare parent version, coordinate space, intended bounds, maximum changes, operations, author, and reason. Validation simulates operations, rejects stale parents/out-of-bounds/oversized changes, and captures exact old/new values. Commit creates an immutable version. Undo changes the active pointer to an exact parent rather than recomputing inverse geometry.
