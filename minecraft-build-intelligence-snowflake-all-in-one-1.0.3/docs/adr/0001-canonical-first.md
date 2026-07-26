# ADR 0001: Canonical-first architecture

**Status:** accepted.

All source formats convert to one exact canonical representation before rendering, analysis, patches, AI context, or export. This prevents UI/render/agent code from accumulating format-specific coordinate and palette behavior.
