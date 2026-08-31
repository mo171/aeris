"""Answers what is actually on this machine and what each dataset's licence permits - the report `aeris dataset list` prints.

what  : `DatasetStatus`, `Availability`, `inspect_dataset()` and `inspect_catalogue()`.
where : Called by `app/cli/dataset.py`. Phase 1.6 calls `require_trainable()` before a training run.
how   : The catalogue in `constants/datasets.py` says what the project *intends* to use. This says what is
        **on the disk in front of you**, which is a different question and the one an operator asks.

        **Size is measured, never declared.** Each record carries an `approximate_size` from the published
        figures, and a half-finished 4 GB download of a 10 GB dataset looks exactly like a finished one to
        anything that trusts that number. Walking the directory is slower and is the only answer worth
        printing.

        **`require_trainable()` is the roadmap's gate expressed as a function call.** "Licences are
        recorded before any training begins, not after" is a rule about sequence, and a rule about sequence
        needs something that refuses at the right moment. An unverified licence is not a warning here; it
        raises, and Phase 1.6 cannot start a training run past it.
"""

import logging
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from app.constants.datasets import DATASET_CATALOGUE, DatasetId, DatasetRecord, DatasetSplit
from app.constants.licences import Licence, LicenceTerms, terms_for
from app.lib.exceptions import ConflictError
from app.services.datasets.loader import count_samples, dataset_directory, split_directory

logger = logging.getLogger(__name__)


class Availability(StrEnum):
    """What state a dataset is in on this machine.

    Four states rather than three, and the fourth was added because a test caught the model being wrong:
    a dataset with its train split downloaded and its test split not is neither ready nor malformed. It is
    **partial**, which is an ordinary and recoverable situation - and reporting it as malformed sends
    someone to check how the archive unpacked when what they actually need to do is finish downloading.
    """

    ABSENT = "absent"

    # Some declared splits are present and others are not. Common and fine: several of these publish their
    # splits as separate archives, and a phase that only trains needs only `train`.
    PARTIAL = "partial"

    # A split that *is* present cannot be read in the declared layout. Distinct from `ABSENT` and `PARTIAL`
    # because it needs the opposite response: not "download more", but "look at how this unpacked".
    MALFORMED = "malformed"

    READY = "ready"


@dataclass(frozen=True, slots=True)
class DatasetStatus:
    """One row of `aeris dataset list`: what it is, whether it is here, and what may be done with it."""

    record: DatasetRecord
    availability: Availability
    directory: Path
    size_bytes: int

    # Only the splits actually present, with their counted sample totals. A declared split missing from
    # this mapping is one that is not on disk - which is why `missing_splits` reads it rather than a flag.
    sample_counts: dict[DatasetSplit, int]
    problem: str | None = None

    @property
    def missing_splits(self) -> tuple[DatasetSplit, ...]:
        """The declared splits that are not on disk. Empty for a complete download."""
        return tuple(
            split for split in self.record.layout.split_directories if split not in self.sample_counts
        )

    def has(self, split: DatasetSplit) -> bool:
        """Whether one split is present and holds samples. The question every caller actually has."""
        return self.sample_counts.get(split, 0) > 0

    @property
    def terms(self) -> LicenceTerms:
        return terms_for(self.record.licence)

    @property
    def is_licensed_for_training(self) -> bool:
        """Whether the licence permits training. Says nothing about whether the data is here.

        Split from availability on purpose: they are different questions with different answers and
        different fixes, and a single `is_trainable` flag hid which of the two was the problem.
        """
        return self.record.licence_verified and self.terms.training_permitted

    def is_trainable(self, split: DatasetSplit = DatasetSplit.TRAIN) -> bool:
        """Whether a model may be trained on one split: it is here, and its licence permits it."""
        return self.has(split) and self.is_licensed_for_training

    @property
    def licence_label(self) -> str:
        """The licence as the table shows it, with unverified ones marked rather than reading as a fact."""
        if self.record.licence is Licence.UNVERIFIED:
            return "UNVERIFIED"
        return self.record.licence.value if self.record.licence_verified else f"{self.record.licence.value} (unchecked)"


def directory_size_bytes(directory: Path) -> int:
    """Total size of everything under a directory.

    Sync and unashamedly a full walk. Measuring is the point - see the module docstring - and this runs
    once per `aeris dataset list`, against directories the operator already knows are large.
    """
    if not directory.exists():
        return 0
    return sum(path.stat().st_size for path in directory.rglob("*") if path.is_file())


def inspect_dataset(dataset_id: DatasetId) -> DatasetStatus:
    """What state one dataset is in, measured rather than assumed.

    Async would buy nothing: this is `stat` calls against a local filesystem, and making it a coroutine
    would put an await in front of a syscall (`code-standards.md` §7 asks for async where there is I/O
    that blocks meaningfully, not everywhere).
    """
    record = DATASET_CATALOGUE[dataset_id]
    directory = dataset_directory(dataset_id)

    if not directory.exists():
        return DatasetStatus(
            record=record,
            availability=Availability.ABSENT,
            directory=directory,
            size_bytes=0,
            sample_counts={},
        )

    size_bytes = directory_size_bytes(directory)
    counts: dict[DatasetSplit, int] = {}
    problem: str | None = None

    for split in record.layout.split_directories:
        split_root = split_directory(dataset_id, split)
        if not split_root.exists():
            # Absent, not broken. Recorded by *omission* from `counts`, which `missing_splits` reads back.
            continue
        try:
            counts[split] = count_samples(dataset_id, split)
        except Exception as error:  # noqa: BLE001 - the message is the useful part and reaches the operator
            # A split that is on disk and cannot be read is the malformed case, and the only one. This is
            # where an incomplete archive or an unexpected top-level directory actually surfaces.
            problem = str(error)
            logger.debug(
                "dataset split could not be enumerated",
                extra={"dataset_id": dataset_id.value, "split": split.value},
            )
            break

    availability = _availability_from(record, counts, problem)
    if availability is Availability.MALFORMED and problem is None:
        problem = f"{directory} exists but holds no samples in the layout {record.layout.kind.value}."
    if availability is Availability.PARTIAL:
        absent = ", ".join(
            split.value for split in record.layout.split_directories if split not in counts
        )
        problem = f"Splits not downloaded: {absent}."

    return DatasetStatus(
        record=record,
        availability=availability,
        directory=directory,
        size_bytes=size_bytes,
        sample_counts=counts,
        problem=problem,
    )


def _availability_from(
    record: DatasetRecord, counts: dict[DatasetSplit, int], problem: str | None
) -> Availability:
    """Turn what was found on disk into one of the four states.

    Separated out because the decision is the whole substance of `inspect_dataset` and reads badly inline:
    the order of the checks *is* the meaning. A readable split that failed to enumerate wins over
    everything, because that is the one an operator has to act on differently.
    """
    if problem is not None:
        return Availability.MALFORMED
    if not counts or not any(counts.values()):
        return Availability.MALFORMED
    if len(counts) < len(record.layout.split_directories):
        return Availability.PARTIAL
    return Availability.READY


def inspect_catalogue() -> list[DatasetStatus]:
    """Every dataset, in catalogue order - which is the order the phases need them."""
    return [inspect_dataset(dataset_id) for dataset_id in DATASET_CATALOGUE]


def require_trainable(dataset_id: DatasetId, split: DatasetSplit = DatasetSplit.TRAIN) -> DatasetStatus:
    """Refuse to proceed unless this dataset is present and its licence has been read and permits training.

    **The roadmap's 1.1 gate, as something that can actually stop a run**: "licences are recorded before
    any training begins, not after". A rule about sequence needs a refusal at the right moment, and a
    warning printed into a log at 2am is not one.

    Phase 1.6 calls this before every training run. `ConflictError` rather than `InvalidRequestError`
    because nothing about the request is malformed - the machine is in a state that forbids the action.
    """
    status = inspect_dataset(dataset_id)

    # Checked per split, not per dataset. Training reads `train` and evaluation reads `test`, and a
    # dataset whose test split has not been downloaded is perfectly trainable - refusing it would be
    # wrong, and accepting a *missing train split* because some other split is present would be worse.
    if not status.has(split):
        raise ConflictError(
            f"{status.record.title} has no {split.value} split on disk ({status.availability.value}). "
            f"{status.problem or ''} Get it from {status.record.source_url}.".strip(),
            details={
                "datasetId": dataset_id.value,
                "split": split.value,
                "availability": status.availability.value,
            },
        )

    if not status.record.licence_verified:
        raise ConflictError(
            f"{status.record.title}'s licence has not been checked. Read {status.record.licence_url}, then "
            f"set `licence_verified=True` on its record in `app/constants/datasets.py`. Training on data "
            "whose terms nobody has read is the thing this check exists to prevent.",
            details={"datasetId": dataset_id.value, "licenceUrl": status.record.licence_url},
        )

    if not status.terms.training_permitted:
        raise ConflictError(
            f"{status.record.title} is licensed {status.record.licence.value}, which does not permit "
            f"training. {status.terms.summary}",
            details={"datasetId": dataset_id.value, "licence": status.record.licence.value},
        )

    return status
