# Contributing

1. Read `docs/architecture/overview.md` and the relevant ADRs.
2. Add tests beside every parser, coordinate transform, patch operation, or renderer change.
3. Run `make test`, `make lint`, and `make typecheck`.
4. Never commit proprietary Minecraft assets, user schematics, secrets, or model payloads.
5. Preserve unknown NBT and report compatibility gaps with a fixture and diagnostic.
