from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Vector3Model(BaseModel):
    x: int
    y: int
    z: int


class BoundsModel(BaseModel):
    min: Vector3Model
    max: Vector3Model


class PatchCreate(BaseModel):
    buildVersionId: str
    coordinateSpace: str = "document"
    bounds: BoundsModel
    maxAffectedBlocks: int = Field(gt=0, le=10_000_000)
    operations: list[dict]
    reason: str = Field(min_length=1, max_length=10_000)
    author: str = Field(default="user", max_length=255)
    preconditions: list[dict] = Field(default_factory=list)
    targetRegion: str | None = None


class SnapshotCreate(BaseModel):
    type: Literal["layer_palette", "global"] = "layer_palette"
    y: int | None = None
    direction: Literal["north", "south", "east", "west", "top", "bottom", "isometric_ne", "isometric_nw", "isometric_se", "isometric_sw"] = "north"
    pixelsPerBlock: int = Field(default=4, ge=1, le=64)
    hiddenPaletteIds: list[int] = Field(default_factory=list)


class BlockQuery(BaseModel):
    bounds: BoundsModel
    states: list[str] = Field(default_factory=list)
    includeAir: bool = False
    limit: int = Field(default=10000, ge=1, le=250000)


class ConstructionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    buildType: str = "building"
    style: str = "medieval"
    dimensions: tuple[int, int, int] = (32, 20, 32)
    floors: int = Field(default=2, ge=1, le=32)
    primaryAxis: str = "north_south"
    interiorRequired: bool = True
    symmetry: str = "balanced"
    detailDensity: str = "medium"
    exportFormat: str = "schem"
    palette: dict[str, str] | None = None
    critiqueIterations: int = Field(default=2, ge=0, le=8)


class AIRunCreate(BaseModel):
    provider: Literal["openai", "anthropic", "local"]
    model: str = Field(min_length=1, max_length=255)
    task: str = Field(min_length=1, max_length=50_000)
    maxIterations: int = Field(default=8, ge=1, le=32)
    allowAutoCommit: bool = False
    maxTextTokens: int = Field(default=32_000, ge=1_000, le=1_000_000)
    maxImages: int = Field(default=8, ge=0, le=100)
    maxImagePixels: int = Field(default=16_777_216, ge=0, le=268_435_456)
    reserveOutputTokens: int = Field(default=4_096, ge=256, le=131_072)


class PresentationSnapshotCreate(BaseModel):
    versionId: str | None = None
    camera: Literal["front", "back", "left", "right", "top", "bottom", "isometric_ne", "isometric_nw", "isometric_se", "isometric_sw"] = "isometric_se"
    projection: Literal["orthographic", "perspective"] = "orthographic"
    width: int = Field(default=1536, ge=128, le=4096)
    height: int = Field(default=1536, ge=128, le=4096)
    transparent: bool = False
    quality: Literal["draft", "analysis", "presentation"] = "analysis"
