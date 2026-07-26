from __future__ import annotations

from mbi.ai.tools import BuildToolExecutor
from mbi.canonical import IntVector3
from mbi.patch import PatchEngine


def test_material_chunk_and_axis_slice_tools(sample_document) -> None:
    engine = PatchEngine(sample_document)
    tools = BuildToolExecutor(lambda: engine.active.document, engine)

    materials = tools.execute("get_material_histogram", {})
    assert materials["result"]["totalNonAir"] == len(sample_document.blocks)

    point = next(iter(sample_document.blocks))
    chunk = [point.x // 16, point.y // 16, point.z // 16]
    result = tools.execute("get_chunk", {"chunk": chunk})
    assert result["metadata"]["nonAirCount"] >= 1
    assert any(tuple(item["position"]) == point.as_tuple() for item in result["blocks"])

    x_slice = tools.execute("get_slice", {"axis": "x", "index": point.x})
    assert x_slice["axis"] == "x"
    assert any(item["position"][0] == point.x for item in x_slice["items"])
