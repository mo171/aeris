# Architecture Decisions

## ADR 001: Workflow Orchestration (Celery vs. Inngest)

**Date:** 2026-08-30
**Status:** Accepted

### Context
The `aeris` backend requires a robust background task and workflow orchestration system to handle complex, long-running AI pipelines (e.g., imagery ingestion, segmentation, VQA, cross-modal analysis). These pipelines are modeled as Directed Acyclic Graphs (DAGs) and require reliable state management, retries, and error recovery. The two primary candidates considered were **Celery** (with Redis) and **Inngest**.

### Decision
We have decided to use **Inngest** for workflow orchestration instead of Celery.

### Rationale

1. **Native Support for Complex Pipelines (DAGs):** 
   The architecture relies heavily on multi-step pipelines (`pipeline/graphs/`, `agents/state.py`). Celery requires complex custom state-tracking (often via Redis) to manage multi-step workflows with dependencies. Inngest is built fundamentally around "steps" and handles state management, pausing, resuming, and retrying individual steps natively out of the box.

2. **Error Recovery & Developer Experience:**
   AI inference pipelines are prone to unpredictable failures (e.g., model timeouts, OOM errors). Inngest provides a modern dashboard that allows developers to inspect the exact state of a failed workflow, fix the issue, and replay the pipeline from the exact point of failure. This significantly accelerates development and debugging compared to Celery's monitoring tools (like Flower).

3. **Infrastructure Overhead:**
   Celery requires provisioning, scaling, and managing separate worker pools and message brokers (Redis/RabbitMQ). Inngest operates as an event-driven orchestrator, triggering HTTP endpoints on the existing API server, reducing the operational burden of managing complex infrastructure early in the project lifecycle.

### Caveats and Constraints
* **Data Payloads:** Because Inngest orchestrates via HTTP, large payloads (like raw satellite imagery or model weights) **must not** be sent through Inngest events. 
* **Mitigation:** The ingestion service must save raw files to persistent storage (e.g., S3 or local disk) and pass only the `file_url` or `reference_id` within the Inngest event payload. The executing steps will read the file directly from storage.

### Alternatives Considered
* **Celery + Redis:** Rejected due to the complexity of managing state across multi-step DAGs and the high infrastructure overhead.
* **Temporal:** A viable self-hosted alternative to Inngest. It offers similar workflow capabilities but requires managing the Temporal server infrastructure. Inngest was favored for its immediate ease of use, but Temporal remains a fallback if self-hosting orchestration becomes a strict requirement.
