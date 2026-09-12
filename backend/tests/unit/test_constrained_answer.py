"""The constrained generator: placeholders in, placeholders out, and any number the model wrote itself is fatal."""

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import pytest

from app.lib.exceptions import ConflictError
from app.services.answer.constrained import (
    facts_from_claims,
    fill_placeholders,
    format_metric,
    phrase_claims,
    template_answer,
    verify_phrasing,
)

AREA = 2_471.0
SHARE = 20.7


def claims() -> list[dict[str, Any]]:
    return [
        {
            "text": f"Sparse vegetation (NDVI 0.20-0.40) covers {AREA:,.1f} hectares of the scene: {SHARE:.1f}% of the ground observed.",
            "isPrimary": True,
            "metrics": [
                {"label": "Area", "value": AREA, "unit": "ha", "precision": 1},
                {"label": "Share of observed ground", "value": SHARE, "unit": "%", "precision": 1},
            ],
        },
        {"text": "The largest region lies in the north-east.", "isPrimary": False, "metrics": []},
    ]


@dataclass
class FakeGeneration:
    text: str
    mean_token_probability: float = 0.9
    generated_tokens: int = 10


class FakeVlm:
    version = "fake-vlm"

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.prompts: list[str] = []

    def generate(self, images: list[Any], prompt: str, *, max_new_tokens: int = 0, use_adapter: bool = True, **_: Any) -> FakeGeneration:
        assert use_adapter is False, "phrasing must run on the base weights"
        self.prompts.append(prompt)
        return FakeGeneration(self.reply)


class FakeManager:
    def __init__(self, model: FakeVlm | None) -> None:
        self.model = model

    @asynccontextmanager
    async def lease(self, model_id: str):
        if self.model is None:
            raise ConflictError("offline", details={})
        yield self.model


def test_facts_replace_each_metric_with_a_numbered_placeholder() -> None:
    [primary, spatial] = facts_from_claims(claims())
    assert primary.statement == "Sparse vegetation (NDVI 0.20-0.40) covers {m1} hectares of the scene: {m2} of the ground observed."
    assert primary.values == {"m1": "2,471.0", "m2": "20.7%"}
    [bare] = facts_from_claims([{"text": "Counted.", "isPrimary": True, "metrics": [{"label": "Regions", "value": 12.0, "unit": "", "precision": 0}]}])
    assert bare.statement == "Counted. (Regions: {m1})" and bare.values == {"m1": "12"}
    assert spatial.values == {} and "{m" not in spatial.statement
    assert format_metric(12.0, 0, "") == "12"


def test_a_numeral_the_model_wrote_itself_is_rejected_and_a_placeholder_is_required() -> None:
    facts = facts_from_claims(claims())
    assert verify_phrasing("About {m1} of sparse vegetation, {m2} of the ground, mostly north-east.", facts) is None
    assert "numerals" in (verify_phrasing("About 2,471 hectares ({m1}) are sparse.", facts) or "")
    assert "no fact defines" in (verify_phrasing("Sparse vegetation covers {m7}.", facts) or "")
    assert "unspoken" in (verify_phrasing("Some vegetation is sparse.", facts) or "")
    assert "unspoken" in (verify_phrasing("{m1}", facts) or "")
    # Numerals the facts already carry (the index range) may be repeated; any other is invented.
    assert verify_phrasing("Vegetation with NDVI 0.20-0.40 covers {m1}, {m2} of the ground.", facts) is None
    assert "numerals" in (verify_phrasing("Vegetation with NDVI 0.20-0.50 covers {m1}, {m2}.", facts) or "")


async def test_the_gate_the_seeded_number_comes_out_exactly() -> None:
    model = FakeVlm("Sparse vegetation covers {m1}, which is {m2} of the observed ground, mostly to the north-east.")
    answer = await phrase_claims("How much unhealthy vegetation is there?", claims(), manager=FakeManager(model))
    assert answer.source == "vlm" and answer.model_version == "fake-vlm"
    assert "2,471.0" in answer.text and "20.7%" in answer.text and "ha hectares" not in answer.text
    assert "{m" not in answer.text
    assert "{m1}" in model.prompts[0] and "2,471" not in model.prompts[0]


async def test_a_hallucinated_number_falls_back_to_the_template_and_keeps_the_evidence() -> None:
    model = FakeVlm("Roughly 3,000 hectares ({m1}) are sparse, about {m2}.")
    answer = await phrase_claims("q", claims(), manager=FakeManager(model))
    assert answer.source == "template" and answer.rejected_phrasing is not None
    assert answer.text == template_answer(claims())
    assert "3,000" not in answer.text


async def test_no_model_means_the_template_with_no_pretence() -> None:
    answer = await phrase_claims("q", claims(), manager=FakeManager(None))
    assert answer.source == "template" and answer.model_version is None
    assert (await phrase_claims("q", claims(), manager=None)).source == "template"
    assert fill_placeholders("{m1}", facts_from_claims(claims())) == "2,471.0"
    with pytest.raises(KeyError):
        fill_placeholders("{m9}", facts_from_claims(claims()))


def test_a_reading_is_spoken_only_when_its_numerals_are_already_on_a_claim() -> None:
    from app.services.answer.constrained import admissible_reading

    assert admissible_reading("Sparse fields lie to the north-east near a river.", claims())
    assert admissible_reading("Vegetation with NDVI 0.20-0.40 dominates.", claims())
    assert not admissible_reading("About 3 fields are visible.", claims())
    assert not admissible_reading("Roughly 40% of the scene is farmland.", claims())
