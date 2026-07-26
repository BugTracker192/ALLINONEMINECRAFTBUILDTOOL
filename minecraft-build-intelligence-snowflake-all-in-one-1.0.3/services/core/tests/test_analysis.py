from __future__ import annotations

from mbi.analysis import analyze_document


def test_analysis_reports_materials_and_components(sample_document) -> None:
    report = analyze_document(sample_document)
    assert report["materials"]["totalNonAir"] == len(sample_document.blocks)
    assert report["components"]["count"] >= 1
