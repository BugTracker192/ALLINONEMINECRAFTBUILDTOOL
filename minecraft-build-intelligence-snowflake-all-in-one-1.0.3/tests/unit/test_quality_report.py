from __future__ import annotations

from pathlib import Path

from mbi.importer import import_build

from app.project import initialize_layout, save_document
from app.quality_report import quality_report


def test_quality_scorecard_joins_every_required_dimension(
    reference_schem: Path,
    tmp_path: Path,
) -> None:
    document = import_build(reference_schem.read_bytes(), reference_schem.name)
    run = tmp_path / "run"
    initialize_layout(run)
    save_document(run, document)

    report = quality_report(run)

    assert report["schema"] == "mbi.quality-scorecard.v1"
    assert 0.0 <= report["overall_score"] <= 100.0
    assert set(report["dimensions"]) == {
        "lighting",
        "interior_coverage",
        "furnishing",
        "facade",
        "structural",
        "circulation",
        "palette_balance",
        "symmetry",
    }
    assert "floating_component_count" in report["dimensions"]["structural"]
    assert "unreachable_node_count" in report["dimensions"]["circulation"]
    assert (run / "quality_report.json").is_file()
