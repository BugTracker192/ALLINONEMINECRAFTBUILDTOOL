from __future__ import annotations

from .components import component_report
from .consistency import interior_exterior_report
from .facade import facade_report
from .lighting import lighting_report
from .materials import material_report
from .navigation import navigation_graph
from .rooms import classify_air_volumes, room_report
from .support import support_report
from .surfaces import surface_report
from .symmetry import reflection_symmetry


def analyze_document(document):
    air_volumes = classify_air_volumes(document)
    return {
        "materials": material_report(document),
        "surfaces": surface_report(document),
        "components": component_report(document),
        "support": support_report(document),
        "rooms": room_report(document, volumes=air_volumes),
        "navigation": navigation_graph(document),
        "lighting": lighting_report(document),
        "facade": facade_report(document),
        "interiorExterior": interior_exterior_report(document, volumes=air_volumes),
        "symmetry": reflection_symmetry(document),
    }


__all__ = [
    "analyze_document",
    "component_report",
    "facade_report",
    "interior_exterior_report",
    "lighting_report",
    "material_report",
    "navigation_graph",
    "reflection_symmetry",
    "room_report",
    "support_report",
    "surface_report",
]
