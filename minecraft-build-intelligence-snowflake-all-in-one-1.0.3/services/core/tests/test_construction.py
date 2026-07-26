from __future__ import annotations

from mbi.ai import AutonomousConstructionExecutor, ConstructionBrief, ConstructionStage
from mbi.export.sponge import export_sponge_v3
from mbi.export.verify import verify_round_trip


def test_autonomous_construction_stages_and_export() -> None:
    brief = ConstructionBrief(name="Test Hall", dimensions=(14, 12, 14), floors=2, detail_density="low")
    executor = AutonomousConstructionExecutor(brief)
    run = executor.execute(critique_iterations=1)
    assert run.stage == ConstructionStage.COMPLETE
    assert len(run.version_ids) >= 5
    assert executor.document.blocks
    assert run.final_analysis is not None
    exported = export_sponge_v3(executor.document)
    report = verify_round_trip(executor.document, exported, "generated.schem")
    assert report.valid, report.messages
