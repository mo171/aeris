"""What kind of imagery a scene is, and what job it does in an investigation.

what  : `SceneModality`, `SceneRole`, `TemporalRole`, `Polarisation`.
where : Read by ingest, by the catalogue search, and by every stage that must know whether it is looking at
        reflectance or at backscatter. Transcribed from the frontend's imagery and investigation schemas.
how   : `SceneModality` is a property of the data. `SceneRole` is a property of the *investigation* - the
        same Sentinel-2 scene is `T0` in one investigation and `T1` in another, so the role is stored on the
        link between investigation and scene, never on the scene.

        Why both `SceneRole` and `TemporalRole` exist rather than one enum: `SceneRole` answers "what slot
        does this fill in this investigation" and includes the non-temporal slots `SAR` and `AUX`;
        `TemporalRole` answers "where does this sit in time" and includes `SINGLE` for a one-scene analysis.
        A cross-modal investigation has a SAR scene at T1, so the two are genuinely independent and folding
        them together would make that case unrepresentable.

        Optical and SAR are not interchangeable anywhere downstream: SAR carries no cloud cover
        (`cloudCoverPercentage` is `None`, never `0` - `api-contract.md` §1 rule 3) and is rendered through
        a dB stretch rather than a reflectance one.
"""

from enum import StrEnum


class SceneModality(StrEnum):
    """The sensor family a scene came from."""

    OPTICAL = "optical"
    SAR = "sar"
    MULTISPECTRAL = "multispectral"
    HYPERSPECTRAL = "hyperspectral"


class SceneRole(StrEnum):
    """The slot a scene fills in one investigation. Stored on the link, not on the scene."""

    T0 = "t0"
    T1 = "t1"
    SAR = "sar"
    AUX = "aux"


class TemporalRole(StrEnum):
    """Where a scene sits in time for the analysis being run."""

    SINGLE = "single"
    T0 = "t0"
    T1 = "t1"


class Polarisation(StrEnum):
    """Which transmit/receive polarisation a SAR measurement was made in.

    **Upper case, and that is not a style choice.** The frontend's `polarisationSchema` is
    `["VV", "VH", "ratio"]`, and `api-contract.md` §0 makes its Zod authoritative. `BandRole` already
    carries lower-case `vv`/`vh` for the *band-selection* job it does inside `math/`, and the two are
    deliberately not the same enum: one addresses a band in a file, the other is a value on the wire.
    Reusing `BandRole` here would emit `"vv"`, the Zod parse would throw at the boundary, and the operator
    would get a blank radar panel rather than an error naming the field.

    `RATIO` is not a measurement. It is VV/VH computed from the two, and it is in the vocabulary because
    the frontend offers it as a display choice - so anything reading this enum must not assume a file
    exists for every member.
    """

    VV = "VV"
    VH = "VH"
    RATIO = "ratio"
