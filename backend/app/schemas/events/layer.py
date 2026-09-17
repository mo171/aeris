"""Carries a drawable layer and the evidence it draws to the operator the moment it exists - the single most important line in the analysis contract.

what  : `LayerReadyEvent`, `EvidenceLayer`, `EvidenceFeature` and its geometry union, `LayerProvenance`,
        and `EvidenceItem`, the record a claim points at.
where : Emitted by the S12 and S15 nodes through `services/evidence/builder.py`; consumed by the journal
        in Phase 1 and by the frontend's layer stack in Phase 2. Mirrors `layer.schema.ts` and the evidence
        half of `evidence.schema.ts`, field for field.
how   : The frontend's own note on `layer-ready`: the viewer draws a layer the moment it exists rather than
        after the run finishes, and *that difference is what separates a workspace that feels alive from
        one that feels like a form submission*. So the event carries the layer **and** the evidence records
        it draws, delivered together so nothing ever renders unattributed.

        Three rules the models enforce rather than leave to a caller:

        - **Every feature carries `magnitude`, `confidence`, `areaHectares`, `value` and `classId`.** The
          frontend's reasoning: magnitude drives extrusion, confidence drives the muted rendering of
          uncertain regions, area is what the answer panel quotes, value is what the instrument read.
          Geometry without them can be drawn but cannot be argued with.
        - **Provenance sits on the layer.** A layer that cannot say which model version and which stage
          produced it has no business being presented as evidence.
        - **Geometry is WGS 84 degrees** (`schemas/geo.py`). A projected coordinate fails the bounds.

        `value` and `magnitude` are deliberately different fields. Magnitude is normalised significance -
        "how much does this matter" - and value is the reading in the layer's own units - "what does the
        instrument say". A feature with only magnitude can be ranked but never read.
"""

from typing import Annotated, Literal

from pydantic import Field

from app.constants.color_ramps import ColorRampId
from app.constants.events import AnalysisEventType
from app.constants.evidence import EvidenceKind
from app.constants.layers import ComparatorSide, LayerKind, LayerRenderMode
from app.lib.responses import CamelCaseModel
from app.schemas.events.base import StreamEvent
from app.schemas.geo import GeoBoundingBox, GeoPoint


class PolygonGeometry(CamelCaseModel):
    """A closed ring of at least three positions. Holes are not carried; the frontend draws outer rings."""

    type: Literal["polygon"] = "polygon"
    ring: list[GeoPoint] = Field(min_length=3)


class PointGeometry(CamelCaseModel):
    type: Literal["point"] = "point"
    position: GeoPoint


class BoundingBoxGeometry(CamelCaseModel):
    type: Literal["bbox"] = "bbox"
    bounds: GeoBoundingBox


type FeatureGeometry = Annotated[
    PolygonGeometry | PointGeometry | BoundingBoxGeometry, Field(discriminator="type")
]


class EvidenceFeature(CamelCaseModel):
    """One georeferenced thing on a layer: a region, a detection, a point."""

    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    geometry: FeatureGeometry
    # Zero to one significance. Drives extrusion height and the order evidence blooms in.
    magnitude: float = Field(ge=0.0, le=1.0)
    # `None` where the model declines to assert one. Never coerced to zero.
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    area_hectares: float | None = Field(default=None, ge=0.0)
    # The reading in the layer's own units - NDVI 0.62, height 34 m. `None` where the product has no scalar.
    value: float | None = None
    # A class id for categorical products, never a colour: the frontend owns the palette.
    class_id: str | None = None
    
    # Phase 2 Evidence properties
    model_id: str | None = None
    model_version: str | None = None
    trace_step_id: str | None = None


class LayerProvenance(CamelCaseModel):
    """Which model, which version, which stage. Required on every layer."""

    model_id: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    trace_step_id: str = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class ValueDomain(CamelCaseModel):
    minimum: float
    maximum: float


class EvidenceLayer(CamelCaseModel):
    """A renderable layer descriptor. Data, not a component: a new product is one more of these."""

    id: str = Field(min_length=1)
    kind: LayerKind
    render_mode: LayerRenderMode
    title: str = Field(min_length=1)
    # A key into the frontend's overlay catalogue - the field that carries *meaning*. An index layer sends
    # its index id (`ndvi`); a mask sends `mask-cloud`. `None` for a product the catalogue has no entry for,
    # which the frontend renders from the title and a neutral palette rather than refusing.
    overlay_id: str | None = None
    # The range actually observed in this scene, when narrower than the product's theoretical domain.
    value_domain: ValueDomain | None = None
    color_ramp_id: ColorRampId
    opacity: float = Field(ge=0.0, le=1.0)
    is_visible: bool = True
    comparator_side: ComparatorSide = ComparatorSide.BOTH
    # Raster layers only: an XYZ template with `{z}`, `{x}` and `{y}` placeholders.
    tile_url_template: str | None = None
    attribution: str | None = None
    # Coverage. Without it Cesium requests tiles across the whole planet (`api-contract.md` §8 rule 4).
    bounds: GeoBoundingBox | None = None
    minimum_zoom: int | None = Field(default=None, ge=0)
    maximum_zoom: int | None = Field(default=None, ge=0)
    features: list[EvidenceFeature] = Field(default_factory=list)
    provenance: LayerProvenance


class EvidenceItem(CamelCaseModel):
    """A record a claim points at: the layer that draws it and the features the spotlight raises."""

    id: str = Field(min_length=1)
    kind: EvidenceKind
    title: str = Field(min_length=1)
    # `None` only for a `statistic`, which is a number rather than a place.
    layer_id: str | None = None
    feature_ids: list[str] = Field(default_factory=list)
    area_hectares: float | None = Field(default=None, ge=0.0)
    magnitude: float = Field(ge=0.0, le=1.0)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source_scene_ids: list[str] = Field(default_factory=list)


class LayerReadyEvent(StreamEvent):
    """`layer-ready`. The layer, and the evidence records it draws, in one event."""

    type: Literal[AnalysisEventType.LAYER_READY] = AnalysisEventType.LAYER_READY
    run_id: str
    layer: EvidenceLayer
    evidence: list[EvidenceItem] = Field(default_factory=list)
