"""The unified evaluation harness for Phase 1.15.

what  : `aeris evaluate`, which produces a scorecard over the whole Phase 1 system.
where : Called from `cli/main.py`.
how   : It coordinates ML evaluation (Change Detection, VQA, Object Detection), 
        routing accuracy, and runs the integration tests to guarantee behavioral regressions 
        (like voice interruption, provenance, and refusal quality) are blocked.
"""

import asyncio
import sys
import pytest
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from app.constants.datasets import DatasetId, DatasetSplit
from app.models.manager import get_manager
from app.services.evaluation.change_detection import evaluate_change_detection
from app.services.evaluation.object_detection import evaluate_object_detection
from app.services.evaluation.vqa import evaluate_vqa
from app.services.evaluation.intent import evaluate_intents, CASCADE
from app.cli.models import render_status

console = Console()

async def _run_ml_evaluations(manager, vlm_file: Path | None = None) -> bool:
    console.print("\n[bold cyan]=== ML Models Evaluation ===[/bold cyan]")
    
    # 1. Change Detection
    console.print("\n[bold]1. Change Detection (LEVIR-CD)[/bold]")
    try:
        report_cd = await evaluate_change_detection(
            manager=manager, dataset_id=DatasetId.LEVIR_CD, split=DatasetSplit.TEST, limit=256
        )
        score_cd = report_cd.score
        console.print(f"  F1: {score_cd.f1:.4f} | IoU: {score_cd.iou:.4f} | Mean Latency: {report_cd.mean_latency_ms:.0f} ms")
    except Exception as e:
        console.print(f"  [red]Failed to evaluate change detection: {e}[/red]")
        
    # 2. Object Detection
    console.print("\n[bold]2. Object Detection (DOTA)[/bold]")
    try:
        report_od = await evaluate_object_detection(
            manager=manager, dataset_id=DatasetId.DOTA8, split=DatasetSplit.VALIDATION, limit=128
        )
        score_od = report_od.score
        console.print(f"  F1: {score_od.f1:.4f} | Mean Latency: {report_od.mean_latency_ms:.0f} ms")
    except Exception as e:
        console.print(f"  [red]Failed to evaluate object detection: {e}[/red]")

    # 3. VLM (VRSBench)
    console.print("\n[bold]3. VQA & Captioning (VLM)[/bold]")
    if vlm_file:
        try:
            report_vlm = await evaluate_vqa(manager=manager, file=vlm_file, limit=128)
            console.print(f"  Overall Score: {report_vlm.score.overall:.4f} | Mean Latency: {report_vlm.mean_latency_ms:.0f} ms")
        except Exception as e:
            console.print(f"  [red]Failed to evaluate VQA: {e}[/red]")
    else:
        console.print("  [dim]Skipped (no --vlm-file provided)[/dim]")
        
    # 4. Zero-Shot Perception
    console.print("\n[bold]4. Zero-Shot Perception (Grounding DINO + SAM)[/bold]")
    console.print("  [dim]Status (Owed): N/A[/dim]")

    return True

async def _run_routing_evaluation() -> bool:
    console.print("\n[bold cyan]=== Routing & Orchestration ===[/bold cyan]")
    try:
        from app.models.encoder import load_encoder
        from app.services.query.bank import embed_bank
        encoder = await load_encoder()
        bank = await embed_bank(encoder)
        report = await evaluate_intents(encoder=encoder, bank=bank, configuration=CASCADE)
        console.print(f"  Intent Accuracy (Cascade): {report.accuracy:.4f} across {report.samples} samples.")
    except Exception as e:
        console.print(f"  [red]Failed to evaluate routing: {e}[/red]")
    return True

def _run_integration_tests() -> int:
    console.print("\n[bold cyan]=== System & Behavioral Gates ===[/bold cyan]")
    console.print("  Running Pytest Integration Suite (Voice, Refusals, Trace Integrity)...")
    
    import subprocess
    tests_dir = str(Path(__file__).parent.parent.parent / "tests" / "integration")
    
    # Run pytest in a separate process to avoid nested asyncio event loop issues
    result = subprocess.run([
        sys.executable, "-m", "pytest",
        tests_dir,
        "-q",
        "--disable-warnings",
        "--tb=short"
    ])
    exit_code = result.returncode
    
    if exit_code == 0:
        console.print("  [green]Integration Suite: PASSED[/green]")
    else:
        console.print("  [red]Integration Suite: FAILED[/red]")
        
    return exit_code

async def execute_scorecard(skip_ml: bool, vlm_file: Path | None) -> int:
    """Run the entire scorecard process."""
    console.print("\n[bold]AERIS PHASE 1.15 SCORECARD[/bold]")
    
    if not skip_ml:
        manager = await get_manager()
        await _run_ml_evaluations(manager, vlm_file)
        
        console.print("\n[bold cyan]=== System Telemetry (VRAM) ===[/bold cyan]")
        await render_status(console, manager)
    else:
        console.print("\n[dim](ML evaluation skipped)[/dim]")

    await _run_routing_evaluation()
    
    return _run_integration_tests()
