"""Pushes a trained adapter from the pulled kernel output to the Hugging Face Hub, so the fleet can fetch it like any other checkpoint.

what  : `python -m training.vlm.publish_adapter --size 2b [--repo <user>/<name>]`.
where : After `kaggle.py output --size 2b` has pulled `adapter/` into `data/training/kernel-output/<size>/`.
        Kaggle's secrets service is not reachable from an API-pushed kernel (measured: the notebook's own
        push reported a connection error), so the upload happens here with `settings.huggingface_token`.
how   : Refuses without `training_record.json` beside the weights - an adapter that cannot say what it was
        trained on is not one the fleet should serve - then uploads the folder in one commit whose
        message names the base and the row count. The repository is public: the base is Apache-2.0 and
        the data CDLA-Permissive / CC-BY, and a judge can pull the adapter without an account.
"""

from __future__ import annotations

import argparse
import json

from app.config import settings
from training.vlm.kaggle import BACKEND, username


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--size", default="2b")
    parser.add_argument("--repo", default=None)
    parser.add_argument("--private", action="store_true")
    arguments = parser.parse_args()

    folder = BACKEND / "data" / "training" / "kernel-output" / arguments.size / "adapter"
    record_path = folder / "training_record.json"
    if not (folder / "adapter_model.safetensors").exists() or not record_path.exists():
        raise SystemExit(f"{folder} holds no adapter_model.safetensors + training_record.json; pull the kernel output first.")
    if settings.huggingface_token is None:
        raise SystemExit("HUGGINGFACE_TOKEN is not set in backend/.env.")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    repo = arguments.repo or f"{username()}/aeris-qwen3vl-{arguments.size}-bigearthnet-txt-lora"

    from huggingface_hub import HfApi

    api = HfApi(token=settings.huggingface_token.get_secret_value())
    api.create_repo(repo, private=arguments.private, exist_ok=True)
    api.upload_folder(
        folder_path=str(folder), repo_id=repo,
        commit_message=f"LoRA on {record['base']} - {record['train_rows']} rows, val loss {record['validation_loss'][-1][1]:.3f}",
    )
    print(f"pushed {folder} -> https://huggingface.co/{repo}")
    print(f"set VLM_ADAPTER_REPOSITORY={repo} in backend/.env")


if __name__ == "__main__":
    main()
