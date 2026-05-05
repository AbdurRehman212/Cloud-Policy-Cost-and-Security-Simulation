# Decision Scoring and Failure Mechanics Design

## Overview
This document outlines the architecture for the "Decision Evaluation and Learning Feedback" module in the cloud simulator. It introduces a hybrid scoring engine that combines universal telemetry normalization with scenario-specific weighting to accurately grade user infrastructure decisions.

## 1. Universal Metrics (The 4 Pillars)
Every simulation cycle evaluates four universal metrics, normalizing each to a continuous 0-100 scale:

* **Latency (L):** Evaluated against a target (e.g., P95 <= 100ms -> 100). Latency above the target reduces the score logarithmically.
* **Cost (C):** Evaluated against the organization's budget. Staying under budget -> 100. Overspending applies a harsh penalty.
* **Efficiency (E):** Evaluated by optimal CPU and Memory utilization. Resources running idle (< 10% CPU) or constantly thrashing (> 95% CPU) lower the score.
* **Reliability (R):** A strict stability check. **Rule:** If `dropped_requests > 0`, then `R = 0`. Otherwise, `R = 100`.

## 2. Scenario-Specific Weighting (The Hybrid Model)
Each scenario dictates the importance of these metrics.

* **Formula:** `Final Score = (wL * L) + (wC * C) + (wE * E) + (wR * R)`
* **Example Profiles:**
    * *Cost Optimization Scenario:* `wC=0.6, wL=0.2, wE=0.2, wR=0`
    * *Black Friday (High Traffic):* `wR=0.4, wL=0.4, wC=0.1, wE=0.1`

## 3. Feedback and Reasoning Engine (Gemini Integration)
The backend scoring truth is passed to the Gemini CLI (or internal reasoning layer) to dynamically generate the learning insight:
* **Input:** Raw snapshot + 4 Pillar Scores + Scenario Weights.
* **Output:** A concise, causal explanation (e.g., *"You achieved low latency but overspent by 2x. Try reducing instances after peak load."*)

## 4. Failure Mechanics & Dataset Explanations
* **Degradation:** High queue build-ups natively cause latency spikes and dropped requests via the `VMDESSimulator`. These real metrics directly crash the Reliability score.
* **Dataset Visibility:** The `dataset_workload_patterns` will be surfaced in the scenario detail UI to show learners why the workload is changing (e.g., "Expected: Spiky traffic due to anomaly row 284").

## 5. UI Presentation
The learning loop UI will be updated to display:
1. **Final Grade:** Numeric score + Letter Grade (A, B, C, D, F).
2. **Breakdown:** A radar chart or progress bar group showing L, C, E, R independently.
3. **Insight:** The LLM-generated causal feedback.
4. **Retry Options:** Allow learners to loop back and try the scenario again to compare scores.

## Architecture & Data Flow
1. User takes action -> UI updates.
2. `ResourceSimulator` churns traffic -> generates snapshot.
3. `learning_engine.py` ingests snapshot -> runs normalization -> applies scenario weights -> creates final `EvaluationReport`.
4. Gemini infers Insight -> binds to `EvaluationReport`.
5. Frontend consumes `EvaluationReport` on scenario complete/validate.
