"""Every table, imported here so Alembic can see it.

what  : Imports each model module and re-exports `Base`, so `Base.metadata` is fully populated by importing
        this one package.
where : `migrations/env.py` imports `Base` from here and nothing else. This file is therefore load-bearing
        in an unusual way: **a model module that is not imported here is invisible to autogenerate**, and its
        table silently never gets created. That failure looks like a missing table at runtime, hours later,
        which is why the import list is explicit rather than a directory scan.
how   : `__all__` names them so a linter does not remove the imports as unused - they exist for their import
        side effect of registering with the declarative registry.
"""

from app.db.models.base import Base
from app.db.models.claim import Claim
from app.db.models.evidence import Evidence
from app.db.models.investigation import Investigation, InvestigationScene
from app.db.models.mission import Mission
from app.db.models.run import Run
from app.db.models.scene import Scene
from app.db.models.trace_step import TraceStep

__all__ = [
    "Base",
    "Claim",
    "Evidence",
    "Investigation",
    "InvestigationScene",
    "Mission",
    "Run",
    "Scene",
    "TraceStep",
]
