# 08 · Fine-tuning the remote-sensing VLM

The problem statement's hard requirement: *a generic VLM without remote-sensing adaptation will not satisfy
the requirements*, and *at least one vision-language component must be fine-tuned using BigEarthNet.txt or
open training data*. This folder is that adaptation, written to be read by someone who has not done it
before. Four notebooks, in order; the code they call lives in `training/vlm/` and `app/`, so nothing
ships *from* a notebook - the notebooks explain, the modules enforce.

| # | Notebook | Runs on | What it answers |
|---|---|---|---|
| 01 | `01_data_analysis` | laptop | What is in BigEarthNet.txt, what could a lazy model exploit, what do we have pictures for |
| 02 | `02_baseline_zero_shot` | laptop | How good is the unadapted Qwen3-VL on our rows - the number to beat |
| 03 | `03_train_lora` | **Kaggle T4** | Train the LoRA adapter and push it to the Hub |
| 04 | `04_evaluate_adapter` | laptop | Base vs adapter on the same rows; did it actually help, and where |

## The idea in one paragraph

A vision-language model (VLM) is a language model with a vision encoder bolted on: the picture becomes a
few hundred "visual tokens" that the language model reads like words. Qwen3-VL was trained on web
photographs and documents; it has never been told what a Sentinel-2 patch of arable land looks like at
10 m, or that a bright streak in a radar image is a building and not a road. **Fine-tuning** shows it a
few tens of thousands of (picture, question, answer) rows from Earth observation so that it learns the
vocabulary and the visual cues. **LoRA** does that without touching the original weights: it learns a
small correction to each attention layer (a few percent of the parameters, ~70 MB) that is loaded *on
top of* the published model. The published model stays exactly as it was, which is what lets one flag
(`VLM_SIZE=2b|4b`) pick the base per demo machine.

## The recipe, and why each choice

- **Base: Qwen3-VL-2B-Instruct** (4B where 8 GB of VRAM exists). Apache-2.0, native multi-image input
  (a bi-temporal pair is two images in one prompt), native grounding, plain `transformers`. The
  RS-native alternatives (EarthDial, GeoChat) are 4-7B with custom code and were adapted by someone else.
- **Data: BigEarthNet.txt** (the statement's dataset), on the Lithuania-summer image subset (2.3 GB of
  the 145 GB archive) - captions, yes/no, MCQ and boxes over *co-registered S1 + S2* pairs, which is the
  optical–SAR paired reasoning the statement asks for. Plus **RSVQA-LR** (another country, another
  question generator) so the model does not learn one dataset's habits. VRSBench is held for evaluation.
- **What the model sees:** S2 as true colour with a fixed 0–2500 reflectance window and gamma 0.6; S1 as
  a VV/VH/ratio false-colour composite with a note telling the model it is radar; both upscaled from
  120 px to 448 px. Training and serving use the same functions (`app/services/vlm/math/rendering.py`).
- **What it is not trained on:** country, season and climate zone - constants in a one-country subset,
  and a model trained on them says "Lithuania" to every picture on Earth.
- **QLoRA, rank 16, one epoch, lr 2e-4**, LoRA on the language model's attention and MLP projections,
  vision tower frozen. Standard; changed only if notebook 04 says so.
- **Scoring:** exact match for closed answers, IoU ≥ 0.5 for boxes, ROUGE-L for captions, per type, with
  the mean over types as the headline. Human-verified `bench` rows are reported separately from the
  template-generated `test` rows.

## Running it

```bash
uv run python -m training.vlm.prepare_bigearthnet_txt      # laptop: renders + rows (needs the licence flag, below)
uv run python -m training.vlm.prepare_rsvqa_lr
uv run python -m training.vlm.merge_instruction_sets
uv run python -m training.vlm.kaggle upload-data           # -> Kaggle dataset "aeris-vlm-instructions"
uv run python -m training.vlm.kaggle push --size 2b        # -> the notebook runs on a T4; ~3 h
uv run python -m training.vlm.kaggle status --size 2b
```

Then set `VLM_ADAPTER_REPOSITORY=<user>/aeris-qwen3vl-2b-bigearthnet-txt-lora` in `backend/.env` and run
notebook 04. `aeris models status` shows the version with the adapter's name; without it the version
carries `-unadapted`, on purpose.

**Credentials you place yourself** (never typed into this repo): `~/.kaggle/kaggle.json` (Kaggle → Settings
→ API token; phone-verify the account for GPU access) and a Kaggle *secret* named `HF_TOKEN` (a Hugging
Face write token) for the push.

**The licence gate.** `prepare_*` refuses to write a *train* split until `licence_verified=True` on the
dataset's record in `app/constants/datasets.py`. That flag means a human read the terms:
BigEarthNet.txt is CDLA-Permissive-1.0 (use, modify, share; keep the agreement text); RSVQA is CC-BY-4.0.
Read them, then flip the flag. Evaluation splits need no flag (`--skip-licence-gate`).

## What the first run measured (2026-09-13)

Overall (mean over answer types), base -> adapter: human-verified bench **0.28 -> 0.53**, template test
0.24 -> 0.64, RSVQA-LR 0.53 -> 0.67. MCQ, boxes and captions improved significantly on every file;
yes/no significantly on the larger files; **counting did not move** (0.22 -> 0.23) - a VLM is the wrong
tool for "how many", the detector is the right one. Full table with the paired test in `bcontext/roadmap.md` 1.7.

Two lessons worth more than the numbers:

1. **Look at what the model says, not only the score.** Captions scored 3x higher - and every one began
   "captured during the summer in Lithuania", because the caption *text* carries the constants we had
   only removed as *categories*. The prep now scrubs those clauses; the next run will tell whether the
   caption gain survives without them.
2. **A fine-tuned model is worse at what it was not trained on.** Asked to phrase claims (a text-only
   task) the adapter replied with one placeholder. AERIS now phrases on the base weights and reads
   pictures with the adapter - LoRA lets you switch per call.
