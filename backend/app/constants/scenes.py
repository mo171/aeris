"""What kind of imagery a scene is, and what job it does in an investigation.

what  : `SceneModality`, `SceneRole`, `TemporalRole`.
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
