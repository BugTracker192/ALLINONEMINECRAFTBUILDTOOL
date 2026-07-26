from __future__ import annotations

from mbi.export import export_litematic, export_sponge_v3, verify_round_trip


def test_sponge_round_trip(sample_document) -> None:
    data = export_sponge_v3(sample_document)
    report = verify_round_trip(sample_document, data, "fixture.schem")
    assert report.valid, report.messages


def test_litematic_round_trip(sample_document) -> None:
    data = export_litematic(sample_document)
    report = verify_round_trip(sample_document, data, "fixture.litematic")
    assert report.valid, report.messages


def test_sponge_round_trip_preserves_entities_and_block_entities(sample_document) -> None:
    from mbi.canonical import CanonicalBlockEntity, CanonicalEntity, IntVector3

    sample_document.block_entities.append(
        CanonicalBlockEntity(
            position=IntVector3(0, 1, 0),
            namespaced_id="minecraft:chest",
            data={
                "CustomName": '{"text":"Archive"}',
                "Items": [{"Slot": 0, "id": "minecraft:book", "count": 1}],
                "Lock": "test-key",
            },
            region_name="Main",
        )
    )
    sample_document.entities.append(
        CanonicalEntity(
            namespaced_id="minecraft:armor_stand",
            position=(0.5, 1.0, 0.5),
            data={
                "Invisible": 1,
                "Tags": ["mbi-test"],
                "Pose": {"Head": [0.0, 15.0, 0.0]},
            },
            region_name="Main",
        )
    )
    sample_document.content_hash = sample_document.compute_content_hash()

    data = export_sponge_v3(sample_document)
    report = verify_round_trip(sample_document, data, "entities.schem")
    assert report.valid, report.messages
