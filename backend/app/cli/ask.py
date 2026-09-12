"""Everything `aeris ask` does - put one or two pictures in front of the VLM with a question, and print what it read.

what  : `execute_ask()`, the async function behind the Typer command in `cli/main.py`; `read_picture()`.
where : Called from `cli/main.py`. The 1.7 gate: *single-image question and answer in the CLI*. 1.10's
        single-image and pair graphs wrap the same services with a run, a trace and a provenance record;
        this command is the model alone, and says so.
how   : PNG and JPEG are read as they are; a TIFF or GeoTIFF is read through rasterio, its first three
        bands taken as red, green, blue, and stretched with the fixed Sentinel-2 window when the values
        are reflectance rather than bytes - the same stretch the training renders used. `--sar` marks a
        picture as radar so the model is told what it is looking at. The answer is printed with the
        model's version (which says whether an adapter is attached) and its mean token probability,
        labelled as the model's certainty in its wording and nothing more.
"""

import asyncio
from pathlib import Path

import numpy as np
from rich.console import Console
from rich.markup import escape

from app.models.manager import get_manager
from app.services.prompts.vlm import SAR_IMAGE_NOTE
from app.services.vlm.math.rendering import S2_REFLECTANCE_WINDOW, render_s1_false_colour, render_s2_true_colour
from app.services.vlm.reading import answer_question, describe_image, read_pair


async def execute_ask(
    *, images: list[Path], question: str | None, sar: list[bool], console: Console
) -> bool:
    """One or two pictures and a question - or no question, for a caption."""
    pictures = [await asyncio.to_thread(read_picture, path, is_sar) for path, is_sar in zip(images, sar, strict=True)]
    manager = await get_manager()
    if len(pictures) == 2:
        notes = tuple(SAR_IMAGE_NOTE if flag else None for flag in sar)
        reading = await read_pair(pictures[0], pictures[1], question or "Compare the two images.", manager=manager, notes=notes)  # type: ignore[arg-type]
    elif question:
        reading = await answer_question(pictures[0], question, manager=manager, is_sar=sar[0])
    else:
        reading = await describe_image(pictures[0], manager=manager, is_sar=sar[0])

    console.print(f"\n  [bold]{escape(reading.text)}[/bold]\n")
    console.print(
        f"  model {escape(reading.model_version)}   {reading.latency_ms} ms   "
        f"model-stated certainty in its wording {reading.confidence:.2f}   images {reading.image_count}"
    )
    if "unadapted" in reading.model_version:
        console.print("  [yellow]no remote-sensing adapter is attached (VLM_ADAPTER_REPOSITORY); this is the base model[/yellow]")
    return True


def read_picture(path: Path, is_sar: bool) -> np.ndarray:
    """An (H, W, 3) 8-bit RGB array from a PNG/JPEG, or from the first bands of a (Geo)TIFF."""
    if path.suffix.lower() in {".tif", ".tiff"}:
        import rasterio

        with rasterio.open(path) as dataset:
            bands = dataset.read(list(range(1, min(dataset.count, 3) + 1))).astype(np.float32)
        if is_sar:
            vv = bands[0]
            vh = bands[1] if bands.shape[0] > 1 else bands[0]
            return render_s1_false_colour(vv, vh, already_decibels=bool(np.nanmax(vv) <= 0))
        if bands.shape[0] < 3:
            bands = np.repeat(bands[:1], 3, axis=0)
        if np.nanmax(bands) > 255 or np.nanmax(bands) <= S2_REFLECTANCE_WINDOW[1] / 10_000:
            scale = 10_000.0 if np.nanmax(bands) <= 1.0 else 1.0
            return render_s2_true_colour(bands[0] * scale, bands[1] * scale, bands[2] * scale)
        return np.moveaxis(bands, 0, -1).clip(0, 255).astype(np.uint8)
    from PIL import Image

    return np.asarray(Image.open(path).convert("RGB"))
