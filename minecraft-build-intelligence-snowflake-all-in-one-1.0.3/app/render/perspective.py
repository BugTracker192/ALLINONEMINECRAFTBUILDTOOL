from __future__ import annotations

from .software import SoftwareRenderer
from .perspective_primitives import PerspectiveCameraSpec, PerspectiveTransform, clip_triangle_to_depth, perspective_transform
from .perspective_triangles import PerspectiveTriangleMixin
from .perspective_raster import PerspectiveRasterMixin
from .perspective_output import PerspectiveOutputMixin


class PerspectiveRenderer(PerspectiveOutputMixin, PerspectiveTriangleMixin, PerspectiveRasterMixin, SoftwareRenderer):
    """Deterministic CPU perspective renderer preserving exact semantic maps."""


__all__ = [
    "PerspectiveCameraSpec", "PerspectiveTransform", "PerspectiveRenderer",
    "clip_triangle_to_depth", "perspective_transform",
]
