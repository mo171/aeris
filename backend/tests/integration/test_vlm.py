"""The VLM in the fleet: it loads within its footprint, reads a picture, phrases claims without inventing a number, and says whether it is adapted.

Needs the Qwen3-VL base (4 GB, fetched on first use) and a CUDA device for the footprint check.
"""

import asyncio

import numpy as np
import pytest
import pytest_asyncio

from app.config import settings
from app.constants.model_ids import ModelId
from app.constants.vlm import UNADAPTED_SUFFIX
from app.models.manager import ModelManager, get_manager, reset_manager
from app.models.registry import resolved_fleet
from app.services.answer.constrained import phrase_claims
from app.services.vlm.reading import answer_question, describe_image, read_pair
from tests.integration.test_specialist_models import dota8_crop

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def manager() -> ModelManager:
    manager = await get_manager()
    yield manager
    await reset_manager()


async def test_the_version_says_whether_an_adapter_is_attached() -> None:
    record = resolved_fleet()[ModelId.REMOTE_SENSING_VLM]
    assert record.weights is not None and record.weights.repository.startswith("Qwen/Qwen3-VL")
    assert (UNADAPTED_SUFFIX in record.version) == (settings.vlm_adapter_repository is None)


async def test_the_gate_a_question_about_one_picture_is_answered_in_the_cli_path(manager: ModelManager) -> None:
    image = dota8_crop()
    reading = await answer_question(image, "Is there a sports field in this image?", manager=manager)
    assert reading.text and reading.image_count == 1 and 0.0 < reading.confidence <= 1.0
    assert reading.model_id is ModelId.REMOTE_SENSING_VLM and reading.model_version
    caption = await describe_image(image, manager=manager)
    assert len(caption.text.split()) >= 8
    pair = await read_pair(image, np.ascontiguousarray(image[::-1]), "What differs between the two images?", manager=manager)
    assert pair.image_count == 2 and pair.text


async def test_the_gate_a_seeded_number_comes_out_of_the_model_exactly_or_not_at_all(manager: ModelManager, monkeypatch: pytest.MonkeyPatch) -> None:
    """The constrained generator on the real model: either the phrasing carries 2,471.0 and 20.7%
    verbatim, or it was rejected and the template did. Never a third number."""
    claims = [
        {
            "text": "Sparse vegetation (NDVI 0.20-0.40) covers 2,471.0 hectares of scene S2A_TEST: 20.7% of the ground observed.",
            "isPrimary": True,
            "metrics": [
                {"label": "Area", "value": 2471.0, "unit": "ha", "precision": 1},
                {"label": "Share of observed ground", "value": 20.7, "unit": "%", "precision": 1},
            ],
        },
        {"text": "The largest region lies in the north-east of the scene.", "isPrimary": False, "metrics": []},
    ]
    monkeypatch.setattr(settings, "vlm_adapter_repository", None)
    answer = await phrase_claims("How much unhealthy vegetation is there?", claims, manager=manager)
    assert "2,471.0" in answer.text and "20.7%" in answer.text
    assert "{m" not in answer.text
    if answer.source == "vlm":
        assert answer.model_version and "2471" not in answer.text.replace("2,471", "")
    else:
        assert answer.rejected_phrasing is not None


async def test_declared_footprint_is_not_smaller_than_measured(manager: ModelManager) -> None:
    if not manager.device.has_accelerator:
        pytest.skip("footprints are measured on a CUDA device")
    import torch

    image = dota8_crop()
    await manager.unload_all()
    torch.cuda.reset_peak_memory_stats()
    await read_pair(image, image, "Compare the two images briefly.", manager=manager)
    peak = int(torch.cuda.max_memory_allocated() // (1 << 20))
    declared = resolved_fleet()[ModelId.REMOTE_SENSING_VLM].vram_megabytes
    assert declared >= peak, f"rs-vlm peaked at {peak} MB through a two-image prompt; declared {declared}"
    await asyncio.sleep(0)
