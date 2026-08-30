"""Proves the backend has not invented a vocabulary the frontend owns, and that no vocabulary on either side is unclassified.

what  : Tests over `bcontext/contracts/schemas.json` and every `StrEnum` in `app/constants/`.
where : `tests/contracts/`. Needs no infrastructure - the contracts are a committed artefact - so these run
        on any machine, including one with no Docker.
how   : `api-contract.md` §7 names four vocabularies the backend may not invent, and warns that the
        `changeformer` / `mdl_changeformer` mistake **has already been made once on the frontend**. It is a
        bug no review catches: both files read correctly on their own, and the damage only appears when
        someone tries to join a claim to the model that produced it.

        So the check is mechanical, and it runs in both directions.

        The direction that matters most is not "do the paired ones match" - it is
        `test_every_backend_enum_is_classified`. A vocabulary that nobody classified is one nobody checks,
        and the way this suite would rot is by someone adding an enum and no test noticing. Adding one now
        fails until it is either paired with a frontend schema or declared backend-only **with a reason**.

        These tests read the vendored file and never run the exporter. The backend suite must not need Node
        installed; keeping the export a separate, committed step is what makes the contract a reviewable
        artefact rather than something regenerated at test time - and a test that regenerates its own
        fixtures proves nothing about the thing it is fixed against.
"""

import importlib
import json
import pkgutil
from enum import StrEnum
from typing import Any

import pytest

import app.constants as constants_package
from app.constants.contracts import (
    BACKEND_ONLY_VOCABULARIES,
    CONTRACT_SCHEMAS_FILE,
    FRONTEND_ONLY_VOCABULARIES,
    SHARED_VOCABULARIES,
    SHARED_VOCABULARY_ALIASES,
)

REGENERATE = "Run `pnpm run contracts:export` in frontend/ after changing a Zod schema."


def load_contracts() -> dict[str, dict[str, Any]]:
    """The vendored document. Sync, because it is module-level test data rather than application code."""
    assert CONTRACT_SCHEMAS_FILE.exists(), (
        f"No vendored contracts at {CONTRACT_SCHEMAS_FILE}. {REGENERATE}"
    )
    return json.loads(CONTRACT_SCHEMAS_FILE.read_text(encoding="utf-8"))


def discover_backend_enums() -> dict[str, type[StrEnum]]:
    """Every `StrEnum` defined in `app/constants/`, keyed `module.ClassName`.

    Discovered by walking the package rather than from a list, for the same reason the exporter scans the
    frontend: a list is a second thing to maintain, and the mistake it invites - a vocabulary nobody
    registered - is invisible.
    """
    discovered: dict[str, type[StrEnum]] = {}
    for module_info in pkgutil.iter_modules(constants_package.__path__):
        module = importlib.import_module(f"app.constants.{module_info.name}")
        for attribute_name in dir(module):
            attribute = getattr(module, attribute_name)
            if (
                isinstance(attribute, type)
                and issubclass(attribute, StrEnum)
                and attribute is not StrEnum
                # Defined here, not imported into it - otherwise one enum is discovered under every module
                # that imports it.
                and attribute.__module__ == module.__name__
            ):
                discovered[f"{module_info.name}.{attribute_name}"] = attribute
    return discovered


CONTRACTS = load_contracts()
BACKEND_ENUMS = discover_backend_enums()

# Every frontend schema that is a plain string enum - the only shape a backend `StrEnum` can be compared to.
FRONTEND_STRING_ENUMS: dict[str, tuple[str, ...]] = {
    name: tuple(schema["enum"])
    for schemas in CONTRACTS.values()
    for name, schema in schemas.items()
    if isinstance(schema, dict) and schema.get("type") == "string" and "enum" in schema
}


async def test_the_contracts_were_actually_exported() -> None:
    """A missing or empty artefact must fail loudly rather than making every test below vacuously pass."""
    assert CONTRACTS, f"The vendored contracts are empty. {REGENERATE}"
    assert len(CONTRACTS) >= 14, f"Only {len(CONTRACTS)} schema modules were exported. {REGENERATE}"


@pytest.mark.parametrize("enum_name", sorted(SHARED_VOCABULARIES))
async def test_a_shared_vocabulary_matches_the_frontend_exactly(enum_name: str) -> None:
    """The backend's values must equal the frontend's - not overlap, not be a subset.

    A missing value is a payload the frontend rejects wholesale. An *extra* value is worse: the backend emits
    something the frontend has never heard of, the Zod parse throws at the boundary, and the operator sees a
    blank surface rather than an error naming the field.
    """
    module_key, schema_name = SHARED_VOCABULARIES[enum_name]

    assert module_key in CONTRACTS, f"{module_key} is not in the vendored contracts. {REGENERATE}"
    assert schema_name in CONTRACTS[module_key], (
        f"{schema_name} is gone from {module_key} - the frontend renamed or removed it. {REGENERATE}"
    )

    frontend_values = set(CONTRACTS[module_key][schema_name]["enum"])
    backend_values = {member.value for member in BACKEND_ENUMS[enum_name]}

    assert backend_values == frontend_values, (
        f"{enum_name} disagrees with {schema_name}.\n"
        f"  only in the backend:  {sorted(backend_values - frontend_values)}\n"
        f"  only in the frontend: {sorted(frontend_values - backend_values)}\n"
        "The frontend's Zod is authoritative (api-contract.md §0). Change the backend, or change both."
    )


@pytest.mark.parametrize("enum_name", sorted(SHARED_VOCABULARY_ALIASES))
async def test_a_second_frontend_name_for_the_same_vocabulary_also_matches(enum_name: str) -> None:
    """Two frontend schemas mean the same thing; both are checked, so they cannot drift apart unnoticed."""
    module_key, schema_name = SHARED_VOCABULARY_ALIASES[enum_name]

    frontend_values = set(CONTRACTS[module_key][schema_name]["enum"])
    backend_values = {member.value for member in BACKEND_ENUMS[enum_name]}

    assert backend_values == frontend_values, (
        f"{enum_name} matches its primary frontend schema but not the alias {schema_name}. "
        "The two frontend schemas have drifted apart from each other."
    )


async def test_every_backend_enum_is_classified() -> None:
    """**The test that keeps the rest honest.** No vocabulary may exist without a decision about it.

    Not a bookkeeping exercise. The way a contract suite rots is that someone adds an enum, no test mentions
    it, and a year later it turns out the frontend spelled it differently all along. Failing here forces the
    question at the only cheap moment: is this the frontend's vocabulary, or ours?
    """
    classified = set(SHARED_VOCABULARIES) | set(BACKEND_ONLY_VOCABULARIES)
    unclassified = sorted(set(BACKEND_ENUMS) - classified)

    assert not unclassified, (
        f"These backend enums are in neither map: {unclassified}. Add each to `SHARED_VOCABULARIES` with "
        "the frontend schema it mirrors, or to `BACKEND_ONLY_VOCABULARIES` with the reason it has none."
    )

    # And the reverse: a map entry naming an enum that no longer exists is a check silently doing nothing.
    stale = sorted(classified - set(BACKEND_ENUMS))
    assert not stale, f"These are classified in `constants/contracts.py` but no longer exist: {stale}."


async def test_every_frontend_vocabulary_is_classified() -> None:
    """The same rule pointed outward: a frontend enum is either met or explicitly still owed.

    This is what turns `FRONTEND_ONLY_VOCABULARIES` into something better than a comment - a new Zod enum on
    the frontend fails this until someone says which phase answers it.
    """
    matched = {schema_name for _, schema_name in SHARED_VOCABULARIES.values()}
    matched |= {schema_name for _, schema_name in SHARED_VOCABULARY_ALIASES.values()}
    unclassified = sorted(set(FRONTEND_STRING_ENUMS) - matched - set(FRONTEND_ONLY_VOCABULARIES))

    assert not unclassified, (
        f"The frontend defines these enums and the backend has said nothing about them: {unclassified}. "
        "Pair each with a backend enum in `SHARED_VOCABULARIES`, or record the phase that will meet it in "
        "`FRONTEND_ONLY_VOCABULARIES`."
    )

    stale = sorted(set(FRONTEND_ONLY_VOCABULARIES) - set(FRONTEND_STRING_ENUMS))
    assert not stale, (
        f"These are listed as owed to the frontend but no longer exist there: {stale}. The frontend removed "
        f"them; remove them here too. {REGENERATE}"
    )


async def test_the_twelve_model_ids_are_exactly_the_twelve() -> None:
    """Called out by name because `api-contract.md` §7 does, and because it has been got wrong before.

    Twelve is asserted as a number as well as a set: a thirteenth model added on one side only would still
    satisfy a subset check, and the count is what makes "the twelve model ids" a phrase either side can use.
    """
    frontend_values = set(CONTRACTS["features/missionCommand/schemas/model.schema.ts"]["modelIdSchema"]["enum"])

    assert len(frontend_values) == 12
    assert {member.value for member in BACKEND_ENUMS["model_ids.ModelId"]} == frontend_values
    assert "changeformer" in frontend_values
    # The exact mistake api-contract.md §7 records as already made once: a prefixed id on one side only.
    assert not any(value.startswith("mdl_") for value in frontend_values)


async def test_the_pipeline_stage_codes_are_s1_to_s20() -> None:
    """The other vocabulary §7 names. Twenty codes, `S1`-`S20`, invented on neither side."""
    frontend_values = set(
        CONTRACTS["features/investigation/schemas/analysis.schema.ts"]["pipelineStageCodeSchema"]["enum"]
    )

    assert frontend_values == {f"S{number}" for number in range(1, 21)}
    assert {member.value for member in BACKEND_ENUMS["stages.PipelineStage"]} == frontend_values


# --- Recorded run ----------------------------------------------------------------------------------------
#
# $ uv run pytest tests/contracts/ -q                                          2026-08-31
#
#   ..................................                                       [100%]
#   34 passed in 3.49s
#
# Against 92 schemas from 14 modules, exported from Zod 4.4.3 by `pnpm run contracts:export`. These tests
# need no infrastructure - verified by running them on their own, which is the point of committing the
# artefact rather than regenerating it.
#
# 22 of the 27 backend StrEnums pair exactly with a frontend schema. The pairings were **discovered by
# comparing value sets**, not asserted by hand, and the five unpaired ones are each recorded with a reason
# in `app/constants/contracts.py` - two of them (`FigureKind`, `LegendKind`) because `figure-ready` is agreed
# in api-contract.md §6 and not yet implemented on the frontend.
#
# Checked by mutation:
#
#   A  `ModelId.CHANGEFORMER = "mdl_changeformer"`     -> 4 tests FAILED, including
#      (the exact bug api-contract.md §7 records          test_the_twelve_model_ids_are_exactly_the_twelve
#       as already made once)                             and two payload validations
#
#   B  `RunStatus` gains a `PAUSED = "paused"`         -> test_a_shared_vocabulary_matches_the_frontend
#      the frontend has never heard of                    _exactly[statuses.RunStatus] FAILED
#
#   C  a new StrEnum in app/constants/ that nobody     -> test_every_backend_enum_is_classified FAILED
#      classified
#
# C is the one that keeps the rest honest: without it, the way this suite rots is that someone adds an enum,
# no test mentions it, and the two sides turn out to have spelled it differently all along.
#
# Both mutated files were restored and byte-compared against their pre-mutation copies.
