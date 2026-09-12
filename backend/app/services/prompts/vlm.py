"""What the vision-language model is asked, word for word - the prompts, in one place, so training and serving ask the same thing.

what  : `SYSTEM_PROMPT`, `SAR_IMAGE_NOTE`, `VQA_TEMPLATE`, `CAPTION_TEMPLATE`, `CONSTRAINED_ANSWER_TEMPLATE`.
where : `app/models/vlm.py` (system prompt), `services/vlm/reading.py` (VQA, caption, SAR note),
        `services/answer/constrained.py` (the constrained answer), and `training/vlm/` and the notebooks
        under `notebooks/08_vlm_finetuning/`, which restate these by value and say they must match.
how   : Strings only. The sizes, footprints, image size, token budgets and the numeral rule are
        `constants/vlm.py` - fixed sets belong there (`code-standards.md`), prompts belong here.

        The constrained-answer template is the contract with the guard: the model is told to copy the
        `{m1}` placeholders and invent no figure, and `services/answer/constrained.py` checks that it did.
"""

from typing import Final

SYSTEM_PROMPT: Final[str] = (
    "You are a remote-sensing analyst. You read satellite and aerial images: optical (true colour), "
    "multispectral index maps, and SAR (radar) backscatter. Answer only from what is visible. If the image "
    "does not show enough to answer, say so."
)

# How a SAR image is introduced when it is shown beside or instead of an optical one. VV/VH backscatter is
# not a photograph and the model is told what it is looking at rather than left to guess.
SAR_IMAGE_NOTE: Final[str] = (
    "This is a synthetic-aperture radar image (Sentinel-1 style backscatter shown as a false-colour "
    "composite of VV, VH and their ratio). Bright is strong backscatter (built-up, rough); dark is smooth "
    "(calm water, flat bare ground)."
)

VQA_TEMPLATE: Final[str] = "{question}\nAnswer briefly."
CAPTION_TEMPLATE: Final[str] = (
    "Describe the land cover and the major objects visible in this image in two or three sentences. "
    "Name only what you can see."
)
# The constrained answer: the claims are given as numbered facts with placeholders where their numbers
# go, and the model is asked to phrase them - placeholders copied verbatim, no new figures.
CONSTRAINED_ANSWER_TEMPLATE: Final[str] = (
    "The analysis produced these findings:\n{facts}\n\n"
    "Write a short plain-English answer to the question \"{question}\" using only these findings. Copy each "
    "placeholder such as {{m1}} exactly where its value belongs. Do not invent any number, area, "
    "percentage or count that is not a placeholder. Do not add findings."
)
