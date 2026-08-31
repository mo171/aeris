"""Says what may legally be done with each dataset and model weight, so the question is answered before training rather than after.

what  : `Licence`, `Redistribution`, `CommercialUse`, and `LICENCE_TERMS` - what each licence permits.
where : Read by `constants/datasets.py` (every dataset names one), by `aeris dataset list`, and from Phase
        1.6 by the model registry, because pretrained weights carry licences too and the same question
        applies to them.
how   : The roadmap's 1.1 gate is explicit: **"Licences are recorded before any training begins, not
        after; most are research-licensed and several forbid redistribution."** That sentence is the whole
        reason this file exists, and it is a requirement about *sequence* - a licence discovered after a
        model is trained is discovered too late to act on.

        **The important member of `Licence` is `UNVERIFIED`, and it is the default rather than an
        oversight.** A dataset whose terms nobody has actually read is not permissive; it is unknown, and
        the two must not look the same in a table. Recording a guess as though it were a fact is worse than
        recording nothing, because the guess is what someone relies on six months later when they are
        deciding whether a demo can be published.

        So `UNVERIFIED` denies everything - `Redistribution.FORBIDDEN`, `CommercialUse.FORBIDDEN`, and
        training not permitted - and `constants/datasets.py` carries, per dataset, the URL where the real
        terms live and what specifically needs checking. `tests/unit/test_dataset_catalogue.py` fails if a
        dataset is marked ready for training while its licence is unverified.

        Nothing here is legal advice, and the code says so where it matters: these are the terms as
        published by each dataset's authors, recorded so a human can check them, not a substitute for that
        check.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class Licence(StrEnum):
    """The licences the datasets and weights in this project are published under."""

    # Copernicus open data. Sentinel-1 and Sentinel-2 are free, full and open: any use, including
    # commercial, with attribution. The one genuinely unambiguous entry in this file.
    COPERNICUS_SENTINEL = "copernicus-sentinel"

    CC_BY_4_0 = "cc-by-4.0"
    CC_BY_SA_4_0 = "cc-by-sa-4.0"
    CC_BY_NC_4_0 = "cc-by-nc-4.0"
    CC_BY_NC_SA_4_0 = "cc-by-nc-sa-4.0"
    MIT = "mit"
    APACHE_2_0 = "apache-2.0"

    # Published for academic use with commercial use reserved or requiring permission. Common for the
    # change-detection and grounding datasets, and the reason the roadmap warns about redistribution.
    RESEARCH_ONLY = "research-only"

    # Nobody has read the terms yet. Denies everything - see the module docstring.
    UNVERIFIED = "unverified"


class Redistribution(StrEnum):
    """Whether this project may hand the data on to someone else.

    The distinction that matters for a submission: a dataset may be perfectly usable for training and still
    forbid us from putting it in a repository, a container image or a demo bundle. `PERMITTED_WITH_ATTRIBUTION`
    and `FORBIDDEN` lead to very different packaging decisions, and the decision is made once, here.
    """

    PERMITTED = "permitted"
    PERMITTED_WITH_ATTRIBUTION = "permitted-with-attribution"
    PERMITTED_SHARE_ALIKE = "permitted-share-alike"
    FORBIDDEN = "forbidden"


class CommercialUse(StrEnum):
    """Whether the data may be used in something sold. Separate from redistribution: they diverge."""

    PERMITTED = "permitted"
    FORBIDDEN = "forbidden"
    REQUIRES_PERMISSION = "requires-permission"


@dataclass(frozen=True, slots=True)
class LicenceTerms:
    """What one licence actually permits, reduced to the three questions this project has to answer."""

    licence: Licence
    redistribution: Redistribution
    commercial_use: CommercialUse

    # Whether a model may be trained or fine-tuned on data under this licence. Separate from commercial use
    # because they come apart in exactly the case that matters here: a research-licensed dataset usually
    # permits training freely and forbids selling the result.
    training_permitted: bool

    # Whether attribution must appear in the report a run produces. Read by Phase 1.12, which generates
    # those reports and is the last place this could be added cheaply.
    attribution_required: bool

    summary: str


LICENCE_TERMS: Final[dict[Licence, LicenceTerms]] = {
    Licence.COPERNICUS_SENTINEL: LicenceTerms(
        licence=Licence.COPERNICUS_SENTINEL,
        redistribution=Redistribution.PERMITTED_WITH_ATTRIBUTION,
        commercial_use=CommercialUse.PERMITTED,
        training_permitted=True,
        attribution_required=True,
        summary=(
            "Free, full and open under the Copernicus data policy. Any use including commercial, with "
            "attribution to Copernicus Sentinel data and the year."
        ),
    ),
    Licence.CC_BY_4_0: LicenceTerms(
        licence=Licence.CC_BY_4_0,
        redistribution=Redistribution.PERMITTED_WITH_ATTRIBUTION,
        commercial_use=CommercialUse.PERMITTED,
        training_permitted=True,
        attribution_required=True,
        summary="Any use with attribution.",
    ),
    Licence.CC_BY_SA_4_0: LicenceTerms(
        licence=Licence.CC_BY_SA_4_0,
        redistribution=Redistribution.PERMITTED_SHARE_ALIKE,
        commercial_use=CommercialUse.PERMITTED,
        training_permitted=True,
        attribution_required=True,
        summary="Any use with attribution; derivatives must carry the same licence.",
    ),
    Licence.CC_BY_NC_4_0: LicenceTerms(
        licence=Licence.CC_BY_NC_4_0,
        redistribution=Redistribution.PERMITTED_WITH_ATTRIBUTION,
        commercial_use=CommercialUse.FORBIDDEN,
        training_permitted=True,
        attribution_required=True,
        summary="Non-commercial use only, with attribution.",
    ),
    Licence.CC_BY_NC_SA_4_0: LicenceTerms(
        licence=Licence.CC_BY_NC_SA_4_0,
        redistribution=Redistribution.PERMITTED_SHARE_ALIKE,
        commercial_use=CommercialUse.FORBIDDEN,
        training_permitted=True,
        attribution_required=True,
        summary="Non-commercial use only, with attribution; derivatives carry the same licence.",
    ),
    Licence.MIT: LicenceTerms(
        licence=Licence.MIT,
        redistribution=Redistribution.PERMITTED_WITH_ATTRIBUTION,
        commercial_use=CommercialUse.PERMITTED,
        training_permitted=True,
        attribution_required=True,
        summary="Any use, with the copyright notice retained.",
    ),
    Licence.APACHE_2_0: LicenceTerms(
        licence=Licence.APACHE_2_0,
        redistribution=Redistribution.PERMITTED_WITH_ATTRIBUTION,
        commercial_use=CommercialUse.PERMITTED,
        training_permitted=True,
        attribution_required=True,
        summary="Any use, with the notice and a statement of changes.",
    ),
    Licence.RESEARCH_ONLY: LicenceTerms(
        licence=Licence.RESEARCH_ONLY,
        redistribution=Redistribution.FORBIDDEN,
        commercial_use=CommercialUse.REQUIRES_PERMISSION,
        training_permitted=True,
        attribution_required=True,
        summary=(
            "Academic and research use permitted, including training. Redistribution is not - so these "
            "never go into a repository, a container image or a demo bundle."
        ),
    ),
    Licence.UNVERIFIED: LicenceTerms(
        licence=Licence.UNVERIFIED,
        redistribution=Redistribution.FORBIDDEN,
        commercial_use=CommercialUse.FORBIDDEN,
        training_permitted=False,
        attribution_required=True,
        summary=(
            "NOBODY HAS READ THE TERMS. Denies everything on purpose: an unknown licence is not a "
            "permissive one, and the two must never look alike in a table. Check the URL recorded against "
            "the dataset, then replace this."
        ),
    ),
}


def terms_for(licence: Licence) -> LicenceTerms:
    """The terms of one licence.

    Sync, and a lookup rather than an attribute on the dataset record, so that adding a licence is one entry
    here instead of an edit at every dataset that uses it.
    """
    return LICENCE_TERMS[licence]
