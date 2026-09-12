"""Drives the Kaggle side from this terminal: upload the instruction set as a dataset, push the training notebook as a kernel, poll it, pull the adapter back.

what  : `python -m training.vlm.kaggle upload-data | push [--size 2b|4b] [--rows N] | status | output`.
where : Run on the laptop after `prepare_*.py`. Needs `~/.kaggle/kaggle.json` (the operator's API token -
        placed by them, never read or written here) and a Kaggle secret `HF_TOKEN` for the push to the Hub.
how   : Thin calls to the official `kaggle` CLI, so nothing here is a re-implementation of its API. The
        kernel metadata is written next to the notebook with the operator's Kaggle username filled in from
        `kaggle config view`; the notebook reads its knobs from environment variables Kaggle does not
        pass, so `push` bakes `BASE`, `HF_REPO` and the row cap into a first cell instead.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
NOTEBOOK = BACKEND / "notebooks" / "08_vlm_finetuning" / "03_train_lora.ipynb"
DATA_DIRECTORY = BACKEND / "data" / "training" / "vlm"
DATA_SLUG = "aeris-vlm-instructions"
KERNEL_SLUG = "aeris-vlm-lora-train"
BASES = {"2b": "Qwen/Qwen3-VL-2B-Instruct", "4b": "Qwen/Qwen3-VL-4B-Instruct"}


def kaggle(*arguments: str) -> str:
    completed = subprocess.run(["kaggle", *arguments], capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise SystemExit(f"kaggle {' '.join(arguments)} failed:\n{completed.stdout}\n{completed.stderr}")
    return completed.stdout.strip()


def username() -> str:
    for line in kaggle("config", "view").splitlines():
        if line.strip().startswith("- username:"):
            return line.split(":", 1)[1].strip()
    raise SystemExit("kaggle config view reports no username; is ~/.kaggle/kaggle.json in place?")


def upload_data() -> None:
    """Create (or version) the Kaggle dataset from data/training/vlm."""
    user = username()
    metadata = {"title": "AERIS VLM instruction set", "id": f"{user}/{DATA_SLUG}", "licenses": [{"name": "other"}]}
    # The VRSBench slicer runs on Kaggle (the archive is 7.8 GB); it travels with the data.
    shutil.copyfile(Path(__file__).with_name("prepare_vrsbench.py"), DATA_DIRECTORY / "prepare_vrsbench.py")
    (DATA_DIRECTORY / "dataset-metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    listing = kaggle("datasets", "list", "-m", "-s", DATA_SLUG)
    if f"{user}/{DATA_SLUG}" in listing:
        print(kaggle("datasets", "version", "-p", str(DATA_DIRECTORY), "-m", "refreshed instruction set", "-r", "zip"))
    else:
        print(kaggle("datasets", "create", "-p", str(DATA_DIRECTORY), "-r", "zip"))


def push(size: str, rows: int | None, hf_repo: str | None, vrsbench_images: int) -> None:
    """Write kernel metadata beside the notebook, bake the knobs into it, and push."""
    user = username()
    workdir = BACKEND / "data" / "training" / "kernel"
    workdir.mkdir(parents=True, exist_ok=True)
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    # A syntax slip costs a queue wait and a GPU session to discover on Kaggle; parse every cell here first.
    import ast

    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            ast.parse("".join(cell["source"]))
    knobs = [
        "import os\n",
        f"os.environ['AERIS_VLM_BASE'] = {BASES[size]!r}\n",
        f"os.environ['AERIS_HF_REPO'] = {(hf_repo or f'{user}/aeris-qwen3vl-{size}-bigearthnet-txt-lora')!r}\n",
        f"os.environ['AERIS_MAX_ROWS'] = {str(rows or 0)!r}\n",
    ]
    notebook["cells"].insert(0, {"cell_type": "code", "metadata": {}, "source": knobs, "outputs": [], "execution_count": None})
    (workdir / "train.ipynb").write_text(json.dumps(notebook), encoding="utf-8")
    metadata = {
        "id": f"{user}/{KERNEL_SLUG}-{size}", "title": f"AERIS VLM LoRA train {size}", "code_file": "train.ipynb",
        "language": "python", "kernel_type": "notebook", "is_private": True, "enable_gpu": True, "enable_tpu": False,
        # A bare `enable_gpu` handed the first run a P100 (sm_60), which neither Kaggle's torch nor
        # bitsandbytes' 4-bit kernels support. The T4 is named explicitly.
        "machine_shape": "NvidiaTeslaT4",
        "enable_internet": True, "dataset_sources": [f"{user}/{DATA_SLUG}"], "competition_sources": [],
        "kernel_sources": [], "model_sources": [],
    }
    (workdir / "kernel-metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(kaggle("kernels", "push", "-p", str(workdir), "--accelerator", "NvidiaTeslaT4"))
    print(f"kernel: https://www.kaggle.com/code/{user}/{KERNEL_SLUG}-{size}")


def status(size: str) -> None:
    print(kaggle("kernels", "status", f"{username()}/{KERNEL_SLUG}-{size}"))


def output(size: str) -> None:
    destination = BACKEND / "data" / "training" / "kernel-output" / size
    destination.mkdir(parents=True, exist_ok=True)
    print(kaggle("kernels", "output", f"{username()}/{KERNEL_SLUG}-{size}", "-p", str(destination)))
    print(f"pulled to {destination}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("command", choices=["upload-data", "push", "status", "output"])
    parser.add_argument("--size", choices=list(BASES), default="2b")
    parser.add_argument("--rows", type=int, default=None, help="Cap the training rows (smoke run).")
    parser.add_argument("--hf-repo", default=None, help="Hub repository for the adapter; defaults to <user>/aeris-qwen3vl-<size>-bigearthnet-txt-lora.")
    parser.add_argument("--vrsbench-images", type=int, default=1200, help="Images in the VRSBench slice cut on Kaggle; 0 skips it.")
    arguments = parser.parse_args()
    match arguments.command:
        case "upload-data":
            upload_data()
        case "push":
            push(arguments.size, arguments.rows, arguments.hf_repo, arguments.vrsbench_images)
        case "status":
            status(arguments.size)
        case "output":
            output(arguments.size)


if __name__ == "__main__":
    main()
