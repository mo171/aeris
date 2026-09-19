"""What the vision-language model is, what it is shown, what it is asked, and what it may not say - fixed, not code.

what  : `VlmSize` and `VLM_VARIANTS` (the base checkpoints and their measured footprints), the image size
        the model is fed, the generation settings, the prompt templates for VQA / captioning / the
        constrained answer, and the numeral rule the constrained generator enforces.
where : `app/models/vlm.py` loads by variant; the prompt strings themselves are `app/prompts/vlm.py`;
        `services/answer/` enforces `NUMERAL_PATTERN`; the training notebooks under `notebooks/08_vlm_finetuning/` read the
        same templates so the model is asked at inference exactly what it was taught.
how   : Qwen3-VL-Instruct (Apache-2.0), 2B on the 4 GB profile and 4B where 8 GB or more is available, both
        served 4-bit (NF4) on CUDA and bf16 on the CPU. The remote-sensing adaptation is a LoRA adapter
        trained on BigEarthNet.txt (plus RSVQA-LR and a VRSBench slice for resolution diversity), named in
        `settings.vlm_adapter_repository`; without it the model runs *unadapted* and says so in its version
        string, because the problem statement rules a generic VLM out and a fleet that hid that would be
        lying to the judges.

        **The model never produces a number the specialists did not.** Its answers to a run are phrased
        from claim objects with `{metric}` placeholders that are filled after generation; any other
        numeral in its output is rejected (`services/answer/constrained.py`). For free-form VQA over a
        single image there are no claims, and the answer is labelled as the model's reading of the
        picture rather than a measurement.
"""

import re
from enum import StrEnum
from typing import Final, NamedTuple


class VlmSize(StrEnum):
    """Which base checkpoint. Chosen by configuration, not by the manager, so a demo machine is one flag."""

    SMALL_2B = "2b"
    MEDIUM_4B = "4b"


class VlmVariant(NamedTuple):
    repository: str
    revision: str
    # 4-bit weights plus activations at `VLM_IMAGE_PIXELS` and `VLM_MAX_NEW_TOKENS`, on the device. To be
    # measured on each variant before it is declared final; the 4B figure is an estimate until then.
    vram_megabytes: int
    version: str


VLM_VARIANTS: Final[dict[VlmSize, VlmVariant]] = {
    VlmSize.SMALL_2B: VlmVariant("Qwen/Qwen3-VL-2B-Instruct", "main", 2_048, "qwen3-vl-2b"),
    VlmSize.MEDIUM_4B: VlmVariant("Qwen/Qwen3-VL-4B-Instruct", "main", 3_584, "qwen3-vl-4b"),
}

# Version suffix when no adapter is attached - visible on the wire, on purpose.
UNADAPTED_SUFFIX: Final[str] = "-unadapted"

# The longer side of every image the model is shown, in pixels. Qwen3-VL tokenises 16-pixel patches merged
# 2x2, so 448 is 196 visual tokens per image - enough for a 120 m BigEarthNet patch upscaled ~4x and for a
# 512-pixel benchmark crop scaled down slightly, and small enough that a two-image pair fits the KV budget
# of a 4 GB card. The training notebooks use the same number.
VLM_IMAGE_PIXELS: Final[int] = 448

# Greedy decoding: the same picture and question give the same words, which is what an evidence record
# needs. Length bounds a runaway caption; VQA answers are a few tokens.
VLM_MAX_NEW_TOKENS: Final[int] = 160
VLM_MAX_NEW_TOKENS_SHORT: Final[int] = 24

# A numeral the model wrote itself. Digits with optional thousands separators and decimals; placeholders
# `{m3}` and their filled values are inserted after this check, so anything matching here is new.
NUMERAL_PATTERN: Final[re.Pattern[str]] = re.compile(r"(?<![{\w])\d[\d,]*(?:\.\d+)?%?")
PLACEHOLDER_PATTERN: Final[re.Pattern[str]] = re.compile(r"\{m(\d+)\}")

# BigEarthNet.txt categories the LoRA is trained on, and the ones it is not. The training images are the
# Lithuania-summer subset of BigEarthNet v2.0, in which country, season and climate zone are constants -
# a model trained on them would learn to say "Lithuania" to every image on Earth.
BEN_TXT_TRAINED_CATEGORIES: Final[frozenset[str]] = frozenset(
    {"presence", "area", "count", "adjacency", "relative pos", "point", "reference", "None"}
)
BEN_TXT_CONSTANT_CATEGORIES: Final[frozenset[str]] = frozenset({"country", "season", "climate zone"})
