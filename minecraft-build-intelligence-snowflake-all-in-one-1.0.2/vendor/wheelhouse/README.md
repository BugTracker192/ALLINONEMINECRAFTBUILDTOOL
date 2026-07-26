# Optional offline wheelhouse

The mandatory Snowflake/CoCo contract provides `pip` access, so this directory may be empty.
`BOOTSTRAP_SNOWFLAKE.py` uses compatible local wheels here first and falls back to PyPI only
when NumPy or Pillow is absent. The private Minecraft asset bundle is already embedded in
`app/bundled_assets/minecraft.zip` and requires no download.
