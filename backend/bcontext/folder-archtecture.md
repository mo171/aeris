backend/
│
├── app/
│   ├── main.py
│   │
│   ├── config.py
│   │
│   ├── routes/
│   │   ├── investigation.py
│   │   ├── imagery.py
│   │   ├── missions.py
│   │   ├── analysis.py
│   │   ├── models.py
│   │   ├── reports.py
│   │   └── health.py
│   │
│   ├── controllers/
│   │   ├── investigation_controller.py
│   │   ├── imagery_controller.py
│   │   ├── analysis_controller.py
│   │   ├── mission_controller.py
│   │   └── report_controller.py
│   │
│   ├── schemas/
│   │   ├── requests/
│   │   │   ├── investigation.py
│   │   │   ├── imagery.py
│   │   │   ├── analysis.py
│   │   │   └── mission.py
│   │   │
│   │   └── responses/
│   │       ├── investigation.py
│   │       ├── evidence.py
│   │       ├── trace.py
│   │       ├── analysis.py
│   │       └── common.py
│   │
│   ├── services/
│   │   │
│   │   ├── pipeline/
│   │   │   ├── pipeline.py
│   │   │   ├── state.py
│   │   │   ├── context.py
│   │   │   ├── executor.py
│   │   │   │
│   │   │   ├── nodes/
│   │   │   │   ├── input_validation.py
│   │   │   │   ├── metadata_analysis.py
│   │   │   │   ├── query_interpretation.py
│   │   │   │   ├── task_classification.py
│   │   │   │   ├── modality_check.py
│   │   │   │   ├── temporal_check.py
│   │   │   │   ├── mission_planning.py
│   │   │   │   ├── model_routing.py
│   │   │   │   ├── inference.py
│   │   │   │   ├── evidence_generation.py
│   │   │   │   ├── confidence.py
│   │   │   │   ├── response_synthesis.py
│   │   │   │   └── trace_generation.py
│   │   │   │
│   │   │   └── graphs/
│   │   │       ├── investigation_graph.py
│   │   │       ├── single_image_graph.py
│   │   │       ├── temporal_graph.py
│   │   │       └── cross_modal_graph.py
│   │   │
│   │   ├── imagery/
│   │   │   ├── ingestion.py
│   │   │   ├── metadata.py
│   │   │   ├── validation.py
│   │   │   ├── preprocessing.py
│   │   │   └── tiling.py
│   │   │
│   │   ├── spectral/
│   │   │   ├── indices.py
│   │   │   ├── ndvi.py
│   │   │   ├── ndwi.py
│   │   │   └── nbr.py
│   │   │
│   │   ├── detection/
│   │   │   ├── detector.py
│   │   │   ├── postprocess.py
│   │   │   └── geometry.py
│   │   │
│   │   ├── segmentation/
│   │   │   ├── segmenter.py
│   │   │   ├── postprocess.py
│   │   │   └── vectorize.py
│   │   │
│   │   ├── change_detection/
│   │   │   ├── detector.py
│   │   │   ├── comparison.py
│   │   │   ├── classification.py
│   │   │   └── postprocess.py
│   │   │
│   │   ├── optical_sar/
│   │   │   ├── alignment.py
│   │   │   ├── preprocessing.py
│   │   │   ├── fusion.py
│   │   │   └── analysis.py
│   │   │
│   │   ├── vqa/
│   │   │   ├── inference.py
│   │   │   └── prompts.py
│   │   │
│   │   ├── captioning/
│   │   │   └── inference.py
│   │   │
│   │   ├── grounding/
│   │   │   ├── inference.py
│   │   │   └── postprocess.py
│   │   │
│   │   └── evidence/
│   │       ├── builder.py
│   │       ├── spatial.py
│   │       ├── confidence.py
│   │       └── trace.py
│   │
│   ├── agents/
│   │   ├── agent.py
│   │   ├── state.py
│   │   ├── planner.py
│   │   ├── router.py
│   │   ├── tools.py
│   │   └── prompts/
│   │       ├── planner.py
│   │       ├── analyst.py
│   │       └── synthesis.py
│   │
│   ├── models/
│   │   ├── registry.py
│   │   ├── loader.py
│   │   ├── manager.py
│   │   ├── vqa.py
│   │   ├── grounding.py
│   │   ├── segmentation.py
│   │   ├── detection.py
│   │   ├── change.py
│   │   └── fusion.py
│   │
│   ├── workers/
│   │   ├── worker.py
│   │   ├── queues.py
│   │   ├── tasks.py
│   │   │
│   │   ├── jobs/
│   │   │   ├── imagery_jobs.py
│   │   │   ├── preprocessing_jobs.py
│   │   │   ├── inference_jobs.py
│   │   │   ├── change_jobs.py
│   │   │   ├── fusion_jobs.py
│   │   │   ├── report_jobs.py
│   │   │   └── monitoring_jobs.py
│   │   │
│   │   └── handlers/
│   │       ├── success.py
│   │       ├── failure.py
│   │       └── retry.py
│   │
│   ├── lib/
│   │   ├── responses.py
│   │   ├── exceptions.py
│   │   ├── error_handler.py
│   │   ├── logger.py
│   │   ├── database.py
│   │   ├── redis.py
│   │   ├── storage.py
│   │   ├── websocket.py
│   │   ├── telemetry.py
│   │   └── security.py
│   │
│   └── constants/
│       ├── tasks.py
│       ├── modalities.py
│       ├── statuses.py
│       ├── errors.py
│       └── limits.py
│
├── notebooks/
        00_experminet/
│   ├── 01_remote_sensing/
│   ├── 02_data_exploration/
│   ├── 03_vlm/
│   ├── 04_vqa/
│   ├── 05_grounding/
│   ├── 06_segmentation/
│   ├── 07_change_detection/
│   ├── 08_optical_sar/
│   ├── 09_finetuning/
│   ├── 10_evaluation/
│   └── experiments/
│
├── training/
│   ├── datasets/
│   ├── configs/
│   ├── scripts/
│   ├── trainers/
│   └── checkpoints/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── pipeline/
│   ├── agents/
│   └── evaluation/
│
├── scripts/
│   ├── download_models.py
│   ├── setup_datasets.py
│   └── run_worker.py
│
├── .env
├── .env.example
├── requirements.txt
├── Dockerfile
└── docker-compose.yml