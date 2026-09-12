"""Prints a Kaggle kernel's log without downloading its output files - the CLI's `kernels output` pulls every artefact first.

what  : `python -m training.vlm.kernel_log [--size 2b] [--tail N] [--grep WORD]`.
where : Beside `kaggle.py`; used while a training kernel runs or after it fails, to read what happened.
how   : One SDK call for the session's output listing with page size 1 - the log rides along with it -
        then the JSON log entries are flattened to text. UTF-8 throughout, because the CLI writes the log
        with the console code page on Windows and dies on the first non-ASCII character.
"""

from __future__ import annotations

import argparse
import json

from training.vlm.kaggle import KERNEL_SLUG, username


def fetch_log(size: str) -> str:
    from kaggle.api.kaggle_api_extended import KaggleApi
    from kagglesdk.kernels.types.kernels_api_service import ApiListKernelSessionOutputRequest

    api = KaggleApi()
    api.authenticate()
    with api.build_kaggle_client() as client:
        request = ApiListKernelSessionOutputRequest()
        request.user_name = username()
        request.kernel_slug = f"{KERNEL_SLUG}-{size}"
        request.page_size = 1
        response = client.kernels.kernels_api_client.list_kernel_session_output(request)
    try:
        entries = json.loads(response.log)
        return "\n".join(entry.get("data", "") for entry in entries if isinstance(entry.get("data", ""), str))
    except (TypeError, ValueError):
        return str(response.log)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--size", default="2b")
    parser.add_argument("--tail", type=int, default=60)
    parser.add_argument("--grep", default=None)
    arguments = parser.parse_args()
    lines = [line for line in fetch_log(arguments.size).splitlines() if line.strip()]
    if arguments.grep:
        lines = [line for line in lines if arguments.grep.lower() in line.lower()]
    for line in lines[-arguments.tail :]:
        print(line[:300])


if __name__ == "__main__":
    main()
