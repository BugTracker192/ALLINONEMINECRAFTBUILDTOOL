from __future__ import annotations

import importlib.metadata

import BOOTSTRAP_SNOWFLAKE as bootstrap


def test_bootstrap_accepts_declared_dependency_ranges(monkeypatch) -> None:
    assert bootstrap._version_tuple("12.3.0") == (12, 3, 0)
    assert bootstrap._version_tuple("2.0.0+vendor.1") == (2, 0, 0)
    versions = {"numpy": "2.3.5", "Pillow": "12.3.0"}
    monkeypatch.setattr(bootstrap.importlib.metadata, "version", versions.__getitem__)
    assert bootstrap.dependency_issues() == []


def test_bootstrap_rejects_present_but_out_of_range_dependency(monkeypatch) -> None:
    actual = importlib.metadata.version

    def version(name: str) -> str:
        return "12.2.0" if name == "Pillow" else actual(name)

    monkeypatch.setattr(bootstrap.importlib.metadata, "version", version)
    assert "Pillow>=12.3,<13" in bootstrap.dependency_issues()
