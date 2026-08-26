# SatQuery AI — AERIS
## Agentic Earth Reasoning & Intelligence System

---

## The Core Problem

Remote-sensing analysis today is a **toolchain problem**, not an algorithm problem. Answering even a simple question like *"did built-up area increase here?"* forces an analyst to:

- Know which satellite sensor and dataset to use
- Acquire and preprocess the data (atmospheric correction, cloud masking, co-registration)
- Choose the right analysis method and AI model
- Handle format differences between optical, SAR, and multispectral imagery
- Post-process, quantify area, and interpret results
- Repeat all of this with different tools that each have their own parameters and failure modes

**The bottleneck is not the availability of algorithms — it is the selection, sequencing, and interpretation of algorithms.** The people with the questions (disaster responders, planners, agricultural officers, defence analysts) are usually not the people who can operate the toolchain.

---

## The Idea — The Actual Solution

**AERIS transforms satellite imagery analysis from a fragmented collection of GIS/AI tools into one intelligent, evidence-grounded investigation system.**

The user uploads satellite imagery and asks questions in plain language — or by voice. AERIS figures out what kind of data it's looking at, picks the right remote-sensing tools, runs them, highlights the exact regions that support its answer, and tells you how confident it is and how it got there.

### What Makes This Different From a Satellite Chatbot

AERIS is **not** a chatbot that wraps a VLM. A VLM alone cannot be the system because:

1. **It hallucinates** — fluent answers unsupported by pixels, with no way to audit
2. **No quantitative rigour** — "how many hectares changed?" needs georeferenced pixel counting, not token prediction
3. **Band-blind** — standard VLMs see only RGB; NDVI, NDWI, SAR polarimetry, 13-band Sentinel-2 are invisible
4. **Weak temporal/cross-modal reasoning** — bi-temporal change and optical–SAR comparison are unsolved by off-the-shelf VLMs
5. **No provenance** — no trace of inputs, parameters, model versions, or intermediate products

**Therefore: the VLM is a component, not the architecture.** Specialist models produce structured, checkable results. The VLM perceives and explains — it never invents evidence.

### The Core Architecture

```
User Question (text or voice)
        ↓
Query Understanding (intent, objects, spatial region, temporal range, modality)
        ↓
Input & Metadata Inspection (sensor, bands, CRS, resolution, acquisition date)
        ↓
Task Classification (VQA / Caption / Ground / Index / Detect / Segment / Change / Cross-Modal)
        ↓
Mission Planning (execution graph for multi-step queries)
        ↓
Specialist Model/Tool Selection (from a model registry with versions & capabilities)
        ↓
Remote-Sensing Preprocessing (co-registration, cloud mask, tiling, resampling)
        ↓
Specialist Execution (indices, segmentation, detection, change detection, SAR tools)
        ↓
Evidence Extraction (bind outputs to georeferenced regions — masks, boxes, change maps)
        ↓
Validation & Confidence Estimation (sanity checks, model confidence, uncertainty flagging)
        ↓
VLM Explanation (LLM explains validated evidence — never invents it)
        ↓
Visual Output + Execution Trace (answer + highlighted evidence + confidence + audit trail)
```

### The Three Analysis Pillars

| Pillar | What It Does | Example |
|---|---|---|
| **Single-Image Intelligence** | VQA, captioning, grounding, object detection, segmentation, land-cover classification, spectral indices (NDVI, NDWI, NDBI, NBR) | *"Show me areas with unhealthy vegetation"* → NDVI map + stressed-region mask + area stats |
| **Temporal Intelligence** | Bi-temporal change detection, change segmentation, change classification, change description, change VQA, area calculation | *"Has the built-up area increased between these two images?"* → Change mask + 18.4% increase + 14.2 hectares + confidence 91% |
| **Cross-Modal Intelligence** | Optical + SAR fusion — per-sensor analysis followed by joint interpretation with dual evidence | *"What changed between the optical and SAR images?"* → Optical evidence + SAR evidence → fused conclusion, each side inspectable |

### Evidence-First Answers

Every answer is auditable. The pipeline is strictly:

```
Specialist Model → Structured Result → Spatial/Temporal Evidence → Validation → LLM Explanation
```

Every claim links to: a **region** (georeferenced), a **mask/box** (visual evidence), the **model** used (with version), **confidence**, and a full **execution trace**. When evidence is insufficient, the system says so and offers alternatives — never a fluent guess.

### The Seven Application Pages

1. **Mission Command Center** — Home screen: upload imagery, enter/speak queries, view 3D Earth, access past missions
2. **Investigation Workspace** — Primary analysis interface: image viewer with overlays (boxes, masks, heatmaps), AI answer panel, execution trace
3. **Cross-Modal Analysis Lab** — Optical + SAR side-by-side with a fusion view and joint reasoning
4. **Temporal Change Explorer** — T0 vs T1 comparison with change maps, timeline scrubber, before/after slider
5. **Evidence Explorer** — Every claim connected to visual, spatial, temporal, and model evidence with full execution trace
6. **Model Observatory** — Inspect which models were used, their capabilities, versions, performance, and why they were selected
7. **Mission & Monitoring Center** — Save investigations as reusable missions, set up continuous monitoring with alerts

### Voice Commands

Voice is a natural interface to AERIS. The flow is:

```
Voice → Speech Recognition → Intent → Agent → Action
```

Voice can control both **AI analysis** and the **visual interface**. Examples:

- *"Compare these images."*
- *"Highlight the changes."*
- *"Zoom into the biggest change."*
- *"Use SAR to verify this."*
- *"Generate a report."*
- *"Create a monitoring mission."*

### The Specialist Model Ecosystem

| Model | Capability |
|---|---|
| **RS-VLM** (GeoChat-class) | VQA, captioning, scene understanding |
| **Grounding Model** (Grounding DINO + SAM) | Text → region (boxes/masks) |
| **Change Detection** (BIT/ChangeFormer-class) | Bi-temporal change masks |
| **Change-VQA** | Temporal question answering over image pairs |
| **Optical–SAR Fusion** | Per-sensor analysis + late fusion with dual evidence |
| **Segmentation** (SegFormer-class) | Land-cover / object segmentation |
| **Object Detection** (DOTA/DIOR-trained) | Buildings, roads, vehicles, infrastructure |
| **Spectral Index Engine** | NDVI, EVI, SAVI, NDWI, MNDWI, NDBI, NBR |

### The Target User Experience

```
User: "Compare these two satellite images and tell me whether the built-up area increased."

AERIS: "I detected two temporally corresponding images. I will perform:
        1. Temporal alignment  2. Change detection  3. Built-up segmentation
        4. Change quantification  5. Evidence validation"
            ↓  [PROCESSING]  ↓
AERIS: "Built-up area increased by approximately 18.4%.
        14.2 hectares of new built-up regions detected, primarily north-east.
        Confidence: 91%."

User: "Investigate."
AERIS: Cross-modal evidence → optical + SAR comparison → confirmed by both sensors.

User: "Show me."
AERIS: 3D Earth + T0 + T1 + Change Mask + SAR + Optical + Evidence

User: "Generate a report."
AERIS: → Professional intelligence report with embedded trace ID
```

---

## 📖 PDF Reference Guide — `SatqueryAI.pdf`

Use this to jump to the exact pages for the detailed idea and implementation.

### Idea & Core Problem

| Topic | PDF Pages | What You'll Find |
|---|---|---|
| **What SatQuery AI is** | **7** | Elevator pitch, technical definition, product identity |
| **The core problem** | **7** | Why RS analysis is a toolchain problem |
| **Why conventional RS is hard** | **8** | Data heterogeneity, preprocessing, scale, expertise gap |
| **Why a VLM alone is insufficient** | **8** | The 5 reasons (hallucination, no rigour, band-blind, weak temporal, no provenance) |
| **Why specialist tools are needed** | **9** | Indices, segmentation, detection — deterministic & auditable |
| **What makes this different from a chatbot** | **9** | Evidence-first, tool routing, multimodal, quantified, auditable |
| **Intended user experience** | **9** | The target interaction quality |
| **Target users & their needs** | **10–11** | User table + User→Need→Query→Analysis→Output mapping |

### Research & Foundations

| Topic | PDF Pages | What You'll Find |
|---|---|---|
| **Remote-sensing fundamentals** | **12–14** | EM spectrum, 4 resolutions, sensors, data formats, CRS, indices (NDVI/NDWI/NDBI/NBR formulas) |
| **RS image captioning research** | **15** | Evolution of captioning, VLM limitations on satellite imagery |
| **RS VQA research** | **16** | Task formulation, methods, open difficulties |
| **Text-guided grounding** | **17** | REC/RES tasks, answer generation vs evidence localisation |
| **Bi-temporal change detection** | **17–18** | Siamese, transformer, Mamba architectures, failure modes |
| **Change description & change VQA** | **18–19** | CDVQA, change stack, dependency chain |
| **Optical–SAR fusion** | **19** | Fusion strategies (early/feature/late/cross-attention), when to fuse |
| **Foundation models & VLM comparison** | **20–21** | Full model comparison table with SatQuery AI roles |
| **Datasets** | **21–24** | Every dataset with task, sensor, resolution, relevance |

### System Design & Implementation

| Topic | PDF Pages | What You'll Find |
|---|---|---|
| **Agentic routing — why not just LLM** | **24–25** | Routing pipeline, deterministic router vs autonomous agent |
| **All 40 features — specification** | **25–27** | Feature spec table: input, modality, preprocessing, model/tool |
| **All 40 features — engineering assessment** | **28–29** | Priority (MVP/SIH/ADV/FUT), difficulty, reliability, demo value |
| **Critical analysis of feature list** | **30** | Duplicates, missing features, infrastructure mislabelled as features |
| **Feature taxonomy & dependency graph** | **31** | 9 domains, build-order dependency graph |
| **20-stage analysis pipeline** | **31–32** | S1–S20 canonical pipeline, stage activation per input type |
| **System modules (M1–M22)** | **33–34** | Every module: purpose, I/O, technologies, owner, complexity |
| **Technical architecture** | **36** | Frontend, backend, AI layer, geospatial layer, storage, model serving |
| **Query understanding & routing examples** | **37** | 6 routing examples end-to-end |
| **Evidence-grounded answers** | **38** | The evidence-first design principle, answer object structure |
| **Explainability & provenance** | **38–39** | Auditable trace structure, provenance requirements |

### Engineering Governance

| Topic | PDF Pages | What You'll Find |
|---|---|---|
| **Evaluation framework** | **39** | RS metrics, VLM/VQA metrics, grounding metrics, system-level metrics |
| **Design decisions log** | **40–41** | Every architectural decision with alternatives and trade-offs |
| **Risk register** | **41–43** | 20+ risks with probability, impact, detection, mitigation, fallback |

### Execution & Build Plan

| Topic | PDF Pages | What You'll Find |
|---|---|---|
| **Feasibility analysis (MVP/SIH/ADV/FUT tiers)** | **44** | What to build, what to cut, and why |
| **Build order (Phases 0–10)** | **44** | Dependency-aware build sequence with gates |
| **Learning roadmap** | **45–47** | Per-role study plan: topics, libraries, models, exercises |
| **Research gaps & novelty** | **48** | Honest novelty assessment, what existing systems don't combine |
| **Competitive comparison** | **49** | Capability comparison table vs GeoChat, EarthGPT, etc. |
| **Final end-to-end system blueprint** | **50** | The complete system flow diagram |
| **References** | **51–54** | All 80+ cited papers |

### Key Pages to Start With

> **If you only read a few pages**, read these:
> - **Pages 7–9** — The core idea, why VLM alone fails, what makes this different
> - **Pages 37–38** — Query routing examples + evidence-grounded answer design
> - **Pages 44** — Feasibility tiers (MVP vs SIH vs Advanced vs Future)
> - **Page 50** — The complete system blueprint diagram

---

## One-Line Definition

> **AERIS is an agentic Earth-observation intelligence system that transforms satellite imagery, multimodal observations, and temporal data into interactive, evidence-grounded geospatial intelligence through specialized computer-vision and vision-language models — where the LLM explains evidence, never invents it.**
