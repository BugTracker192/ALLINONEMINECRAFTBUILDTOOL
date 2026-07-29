# Optional offline wheelhouse

This directory is intentionally optional and may be empty. It is an offline
dependency source only when compatible NumPy and Pillow wheels are actually
present.

`BOOTSTRAP_SNOWFLAKE.py` uses compatible local wheels first. Otherwise configure
pip credentials or pass an explicit `--index-url`; some Snowflake artifact
repository URLs return 401 without session credentials. Public PyPI is not
assumed to be reachable. The private Minecraft asset is delivered separately
through hash-locked ordinary-Git parts and needs no package-index download.
