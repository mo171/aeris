"""The names of the events AERIS puts on the Inngest bus, and the convention every future one follows.

what  : `EventName`, and the naming rule it is built on. Today it holds one member - the connectivity probe -
        because that is the only event this backend actually sends.
where : Read by `app/lib/inngest.py`. Phase 2.5 adds the real ones and `app/inngest/functions/` subscribes to
        them (ADR-002); nothing between here and there emits an event.
how   : **An event name is the hardest string in the system to change.** It is written into a durable
        execution history, matched by function triggers that may be deployed separately, and replayed months
        later from the Inngest dashboard against records that still carry the old name. Renaming one is not a
        refactor - it is a migration with in-flight runs in the middle of it. So the convention is fixed here
        before there is anything to name, rather than inferred later from whatever the first three happened
        to look like.

        The convention is `aeris/<domain>.<action>`, past tense where the event reports something that has
        already happened:

            aeris/scene.uploaded          a thing happened, and something may want to react
            aeris/investigation.requested a thing is being asked for

        Past tense matters because it is the difference between an event and a command. `aeris/scene.ingest`
        would name an instruction to one specific consumer, which is a queue message wearing an event's
        clothes; `aeris/scene.uploaded` states a fact that any number of consumers may act on, which is what
        makes adding the second consumer free.

        **This module deliberately does not list the Phase 2.5 events.** Writing `SCENE_INGEST_REQUESTED`
        today would be a claim that something sends it - and per `config.py`'s own rule, a declaration
        nothing reads is a claim about the system that nothing verifies.
"""

from enum import StrEnum
from typing import Final

# The prefix every event carries, matching the Inngest convention of `<app>/<event>`. Named once so that a
# deployment sharing an Inngest account with another project stays filterable in the dashboard.
EVENT_NAME_PREFIX: Final[str] = "aeris"


class EventName(StrEnum):
    """Every event this backend sends. One, for now, and it is real rather than illustrative."""

    # Sent by `app/lib/inngest.py`'s connectivity check and by `aeris doctor`. It has no consumer and is not
    # supposed to have one: its whole job is to prove the round trip - the event bus accepted something and
    # can hand it back - without any function existing to run. That is the Phase 0.5 gate.
    HEALTH_PROBE = "aeris/system.health-probed"
