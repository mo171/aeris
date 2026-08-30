"""Every lifecycle state the frontend renders differently. Statuses are UI states, so they are the frontend's.

what  : `RunStatus`, `InvestigationStatus`, `TraceStepState`, `SceneProcessingState`,
        `AssistantMessageStatus`, `MissionStatus`, `ModelHealth`.
where : Read by the run loop, the stream events, the mission service and `GET /models/status`. Transcribed
        from the frontend's investigation, assistant, mission and model schemas.
how   : Grouped in one module because they are one concern - "what state is this thing in, and what does the
        interface show for it" - and splitting five short enums across five files would obscure that they
        share a rule: **a status is never inferred by the client.** The backend states it.

        Two distinctions worth not collapsing:

        `RunStatus.CANCELLED` is not `FAILED`. Barge-in cancels a run mid-flight (`api-contract.md` §5), and
        an operator interrupting on purpose must not appear in the interface as an error they need to
        investigate.

        `ModelHealth.WARMING` is not `OFFLINE`. A cold model that will answer in thirty seconds and a model
        that will never answer produce opposite decisions - wait, or route elsewhere - and an operator
        reading "offline" would give up on a working system.
"""

from enum import StrEnum


class RunStatus(StrEnum):
    """The state of one analysis run."""

    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class InvestigationStatus(StrEnum):
    """The state of an investigation, which outlives the runs inside it."""

    DRAFT = "draft"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"


class TraceStepState(StrEnum):
    """The state of one S1-S20 step inside a run.

    `SKIPPED` is not `COMPLETE`. Most runs do not execute all twenty stages - a single-image query never
    co-registers - and the execution spine draws a skipped stage differently from one that ran. Collapsing
    the two would make a pipeline that quietly did less look identical to one that did the work.

    Every step is emitted at least twice: `RUNNING`, then `COMPLETE` with a `durationMs`. That transition is
    the execution-trace UI (`api-contract.md` §3.1).
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class SceneProcessingState(StrEnum):
    """How far a scene has got through ingest, from the catalogue's point of view.

    Named for the scene rather than for the job, because it is what the imagery catalogue renders per row.
    `READY` is the only state from which a scene may be analysed: everything else means the raster has not
    been validated, and `architecture-context.md` §8 forbids a model reading an unvalidated input.
    """

    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class AssistantMessageStatus(StrEnum):
    """The state of one assistant message. `STREAMING` is a message whose tokens are still arriving."""

    STREAMING = "streaming"
    COMPLETE = "complete"
    FAILED = "failed"


class MissionStatus(StrEnum):
    """The state of a saved, re-runnable mission. Drives the server-side ordering of `GET /missions`."""

    ACTIVE = "active"
    MONITORING = "monitoring"
    ALERT = "alert"
    ARCHIVED = "archived"


class ModelHealth(StrEnum):
    """Whether a model can serve a request now."""

    ONLINE = "online"
    WARMING = "warming"
    DEGRADED = "degraded"
    OFFLINE = "offline"
