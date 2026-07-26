# Semantic Maps and Pixel Grounding

Each snapshot uses one raster pass for color and semantic evidence. Sidecar arrays are raw little-endian data with a deterministic JSON header.

Maps:

- `coordinate`: `int32[height,width,3]`; sentinel is minimum signed int.
- `palette`: `uint32[height,width]`; sentinel is maximum unsigned int.
- `region`: `uint16[height,width]`; sentinel is maximum unsigned int.
- `depth`: `float32[height,width]`.
- `normal`: `int8[height,width,3]`, normalized by 127.
- `occupancy`, `changed`, `issue`: `uint8[height,width]`.

`pixel_to_block` returns only canonical coordinates stored in this map. It never infers identity from RGB. `block_to_pixel` returns all frontmost pixel projections for an exact coordinate.
