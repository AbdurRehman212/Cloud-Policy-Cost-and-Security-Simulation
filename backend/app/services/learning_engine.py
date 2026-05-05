"""Scenario-based learning engine for the cloud simulator."""

from __future__ import annotations
import subprocess
import json
from functools import lru_cache
from typing import Any

import pandas as pd

from app.data.scenarios import SCENARIOS
from app.utils.dataset_loader import load_dataset
from app.services.scoring_engine import DecisionScorer


SCENARIO_MAP = {scenario["id"]: scenario for scenario in SCENARIOS}
CURRICULUM_SEQUENCE = [scenario["id"] for scenario in SCENARIOS]
ROLE_LABELS = {
    "viewer": "student",
    "member": "student",
    "student": "student",
    "owner": "organization",
    "organization": "organization",
    "admin": "admin",
    "superadmin": "admin",
}

ROLE_SYSTEM = {
    "student": {
        "title": "Student",
        "description": "Learns cloud concepts by solving guided scenarios.",
        "permissions": ["view scenarios", "run simulations", "track progress"],
    },
    "organization": {
        "title": "Organization",
        "description": "Manages shared infrastructure and team learning paths.",
        "permissions": ["manage organization", "share infra", "review progress"],
    },
    "admin": {
        "title": "Admin",
        "description": "Creates scenarios and manages the learning curriculum.",
        "permissions": ["create scenarios", "seed curriculum", "manage platform"],
    },
}

LEVELS = [
    {"level": 1, "title": "Beginner", "min_points": 0, "focus": "single-service basics"},
    {"level": 2, "title": "Foundation", "min_points": 100, "focus": "safe operations"},
    {"level": 3, "title": "Intermediate", "min_points": 250, "focus": "multi-service reasoning"},
    {"level": 4, "title": "Advanced", "min_points": 500, "focus": "failure recovery and optimization"},
    {"level": 5, "title": "Architect", "min_points": 800, "focus": "system design and tradeoffs"},
]

PROGRESSION_PATH = [
    {
        "level": level["level"],
        "title": level["title"],
        "focus": level["focus"],
        "scenario": next((scenario for scenario in SCENARIOS if scenario.get("recommended_for", "").lower() == level["title"].lower()), None),
    }
    for level in LEVELS
]

TRACK_LIMITS = {
    "beginner": 1,
    "intermediate": 3,
    "advanced": 4,
}

TRACK_ALIASES = {
    "foundation": "intermediate",
    "starter": "beginner",
    "expert": "advanced",
}


def resolve_learning_role(user=None, membership=None) -> str:
    """Map platform roles to the learning role requested by the product."""
    if getattr(user, "is_superadmin", False):
        return "admin"
    role = getattr(membership, "role", None) or getattr(membership, "my_role", None)
    if role in {"owner", "admin"}:
        return "organization"
    return "student"


def normalize_learning_level(level: str | None) -> str:
    """Normalize level labels to the supported learning tracks."""
    normalized = (level or "beginner").strip().lower()
    normalized = TRACK_ALIASES.get(normalized, normalized)
    if normalized not in TRACK_LIMITS:
        return "beginner"
    return normalized


def curriculum_limit(level: str | None) -> int:
    """Return the maximum scenario index unlocked for a learning track."""
    return TRACK_LIMITS.get(normalize_learning_level(level), 1)


def _scenario_id_list(limit: int) -> list[int]:
    return [scenario_id for scenario_id in CURRICULUM_SEQUENCE if scenario_id <= limit]


def next_unlocked_scenario(progress=None, level: str | None = None) -> dict[str, Any] | None:
    """Return the next scenario the learner can actually open."""
    limit = curriculum_limit(level)
    completed = set((getattr(progress, "scenarios_completed", None) or []))
    for scenario_id in _scenario_id_list(limit):
        if str(scenario_id) not in completed and scenario_id not in completed:
            return SCENARIO_MAP.get(scenario_id)
    return SCENARIO_MAP.get(_scenario_id_list(limit)[-1]) if _scenario_id_list(limit) else None


def scenario_unlock_state(progress=None, level: str | None = None) -> list[dict[str, Any]]:
    """Return scenario unlock metadata for the frontend."""
    limit = curriculum_limit(level)
    completed = set(str(item) for item in (getattr(progress, "scenarios_completed", None) or []))
    unlocked_ids = _scenario_id_list(limit)
    next_scenario = next_unlocked_scenario(progress=progress, level=level)
    next_scenario_id = next_scenario.get("id") if next_scenario else None
    states: list[dict[str, Any]] = []
    for scenario in SCENARIOS:
        scenario_id = scenario["id"]
        unlocked = scenario_id in unlocked_ids and (
            scenario_id == next_scenario_id or str(scenario_id) in completed
        )
        states.append({
            "id": scenario_id,
            "unlocked": unlocked,
            "locked": not unlocked,
            "completed": str(scenario_id) in completed,
            "unlock_limit": limit,
            "reason": (
                "Complete the current module first" if not unlocked else "Available now"
            ),
        })
    return states


@lru_cache(maxsize=1)
def dataset_workload_patterns() -> dict[str, Any]:
    """Derive realistic workload patterns from the staged dataset."""
    try:
        frame = load_dataset()
    except Exception:
        frame = pd.DataFrame()

    if frame.empty:
        return {
            "spikes": {"peak_cpu": 0, "peak_memory": 0, "count": 0},
            "seasonal": {"peak_window": [], "off_peak_window": []},
            "failures": [],
        }

    cpu = pd.to_numeric(frame["cpu_avg"], errors="coerce").fillna(0)
    mem = pd.to_numeric(frame["mem_avg"], errors="coerce").fillna(0)
    time_axis = pd.to_numeric(frame["time"], errors="coerce").fillna(0)
    high_cpu = cpu.quantile(0.9)
    low_cpu = cpu.quantile(0.1)
    peak_rows = frame.loc[cpu >= high_cpu, ["time", "cpu_avg", "mem_avg"]].head(5)
    trough_rows = frame.loc[cpu <= low_cpu, ["time", "cpu_avg", "mem_avg"]].head(5)

    def _rows_to_series(rows: pd.DataFrame) -> list[dict[str, Any]]:
        return [
            {
                "time": int(row["time"]),
                "cpu_avg": round(float(row["cpu_avg"]), 2),
                "mem_avg": round(float(row["mem_avg"]), 2),
            }
            for _, row in rows.iterrows()
        ]

    failure_rows = frame.loc[(cpu >= cpu.quantile(0.95)) | (mem >= mem.quantile(0.95)), ["time", "cpu_avg", "mem_avg"]].head(10)
    return {
        "spikes": {
            "peak_cpu": round(float(cpu.max()), 2),
            "peak_memory": round(float(mem.max()), 2),
            "count": int((cpu >= high_cpu).sum()),
        },
        "seasonal": {
            "peak_window": _rows_to_series(peak_rows),
            "off_peak_window": _rows_to_series(trough_rows),
            "time_span": [int(time_axis.min()), int(time_axis.max())],
        },
        "failures": _rows_to_series(failure_rows),
    }


def role_profile(role: str) -> dict[str, Any]:
    """Return a short role description for the learning UI."""
    return {
        "role": role,
        **ROLE_SYSTEM.get(role, ROLE_SYSTEM["student"]),
    }


def current_level(total_points: int | None) -> dict[str, Any]:
    points = int(total_points or 0)
    level = LEVELS[0]
    for candidate in LEVELS:
        if points >= candidate["min_points"]:
            level = candidate
    next_level = next((candidate for candidate in LEVELS if candidate["level"] > level["level"]), None)
    return {
        **level,
        "points": points,
        "points_to_next": max(0, (next_level["min_points"] - points) if next_level else 0),
        "next_level": next_level["title"] if next_level else None,
        "roadmap": PROGRESSION_PATH,
    }


def level_options() -> list[dict[str, Any]]:
    return [
        {
            "id": "beginner",
            "title": "Beginner",
            "description": "Focus on the first module and guided feedback.",
        },
        {
            "id": "intermediate",
            "title": "Intermediate",
            "description": "Unlock the first three modules in sequence.",
        },
        {
            "id": "advanced",
            "title": "Advanced",
            "description": "Unlock the full recovery and optimization path.",
        },
    ]


def explain_metric_change(scenario: dict[str, Any], snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a short causal explanation for why the metrics changed."""
    snapshot = snapshot or {}
    cause_effect = scenario.get("cause_effect", {})
    loop = scenario.get("learning_loop", {})
    return {
        "why": cause_effect.get("why", scenario.get("description", "")),
        "trigger": cause_effect.get("trigger", scenario.get("title", "Scenario trigger")),
        "result": cause_effect.get("result", "The simulator updated its state based on the chosen action."),
        "what_you_changed": loop.get("action", "A corrective action was applied."),
        "why_this_changes_metrics": cause_effect.get(
            "why",
            "The simulator responds to the selected action by changing workload, capacity, or risk.",
        ),
        "evidence": {
            "cpu_avg": snapshot.get("cpu_avg", 0),
            "memory_avg": snapshot.get("memory_avg", 0),
            "queue_total_ms": snapshot.get("workload", {}).get("queue_total_ms", 0),
            "p95_latency_ms": snapshot.get("workload", {}).get("p95_latency_ms", 0),
            "bpi": snapshot.get("bpi", 0),
            "target_bpi": snapshot.get("target_bpi", 0),
            "capacity": snapshot.get("capacity", 1),
        },
    }


def recommended_scenario(level_title: str | None = None, progress=None) -> dict[str, Any] | None:
    """Pick the next scenario the learner should see for the selected track."""
    next_scenario = next_unlocked_scenario(progress=progress, level=level_title)
    if next_scenario:
        return next_scenario
    return SCENARIOS[0] if SCENARIOS else None


def learning_loop_for_scenario(scenario: dict[str, Any], snapshot: dict[str, Any] | None = None, *, level: str | None = None, progress=None) -> dict[str, Any]:
    """Return the learning loop: user → scenario → action → simulation → result → explanation."""
    snapshot = snapshot or {}
    loop = scenario.get("learning_loop", {})
    explanation = explain_metric_change(scenario, snapshot)
    return {
        "user": loop.get("user", "student"),
        "scenario": loop.get("scenario", scenario.get("title")),
        "action": loop.get("action", "Take a corrective action"),
        "simulation": loop.get("simulation", "The simulator updates metrics and behavior."),
        "result": loop.get("result", "Observe what changed."),
        "explanation": explanation,
        "cause_effect": scenario.get("cause_effect", {}),
        "module": scenario.get("module"),
        "next_scenario": recommended_scenario(level, progress),
    }


def build_learning_profile(user=None, membership=None, progress=None, snapshot=None, level: str | None = None) -> dict[str, Any]:
    """Compose a scenario-based learning view for the dashboard and labs."""
    role = resolve_learning_role(user, membership)
    role_info = role_profile(role)
    progress_level = current_level(getattr(progress, "total_points", None) if progress else None)
    selected_level = normalize_learning_level(level or getattr(progress, "learning_stage", None))
    scenario = recommended_scenario(selected_level, progress=progress)
    loop = learning_loop_for_scenario(scenario, snapshot, level=selected_level, progress=progress) if scenario else None
    return {
        "role": role,
        "role_info": role_info,
        "level": progress_level,
        "learning_track": selected_level,
        "level_options": level_options(),
        "scenario_catalog": SCENARIOS,
        "recommended_scenario": scenario,
        "learning_loop": loop,
        "modules": [s.get("module", s.get("title")) for s in SCENARIOS],
        "progression_path": PROGRESSION_PATH,
        "curriculum_limit": curriculum_limit(selected_level),
        "unlock_state": scenario_unlock_state(progress=progress, level=selected_level),
        "next_scenario": next_unlocked_scenario(progress=progress, level=selected_level),
        "workload_patterns": dataset_workload_patterns(),
        "scenario_learning_map": [
            {
                "id": scenario_item["id"],
                "module": scenario_item.get("module"),
                "difficulty": scenario_item.get("difficulty"),
                "recommended_for": scenario_item.get("recommended_for"),
                "learning_loop": scenario_item.get("learning_loop", {}),
                "cause_effect": scenario_item.get("cause_effect", {}),
                "locked": scenario_item["id"] > curriculum_limit(selected_level),
            }
            for scenario_item in SCENARIOS
        ],
    }


def _generate_gemini_insight(payload: dict) -> dict:
    """Invoke Gemini CLI to get qualitative feedback."""
    prompt = (
        "As a cloud architect, evaluate these simulation results. "
        f"Metrics: {json.dumps(payload['raw_metrics'])}. "
        f"Scores: {json.dumps(payload['normalized_scores'])}. "
        f"Final Score: {payload['final_score']}. "
        "Provide a 1-sentence insight and 1 specific suggested action. "
        "Format as JSON: {\"insight\": \"...\", \"suggested_actions\": [\"...\"]}"
    )
    try:
        # Use subprocess to call gemini CLI
        result = subprocess.check_output(["gemini", prompt], text=True, timeout=10)
        # Attempt to parse JSON from output
        start_idx = result.find("{")
        end_idx = result.rfind("}") + 1
        if start_idx != -1 and end_idx != -1:
            data = json.loads(result[start_idx:end_idx])
            return {
                "insight": data.get("insight", "Performance is within expected parameters."),
                "suggested_actions": data.get("suggested_actions", ["No changes needed."])
            }
        return {
            "insight": result.strip()[:200],
            "suggested_actions": ["Follow architectural best practices."]
        }
    except Exception:
        # Robust fallback
        return {
            "insight": "Your system configuration has been evaluated. Review the metric breakdown to identify areas for improvement.",
            "suggested_actions": ["Check resource utilization vs cost."]
        }


def evaluate_scenario_decision(scenario: dict, snapshot: dict) -> dict:
    """Calculate the decision score and generate feedback."""
    scoring_profile = scenario.get("scoring_profile", {
        "wL": 0.25, "wC": 0.25, "wE": 0.25, "wR": 0.25,
        "target_latency_ms": 100.0,
        "budget": 10.0
    })

    # Map snapshot to raw metrics expected by scorer
    workload = snapshot.get("workload", {})
    raw_metrics = {
        "p95_latency": workload.get("p95_latency_ms", 0.0),
        "rps": workload.get("requests_per_second", 0.0),
        "actual_cost": snapshot.get("current_month_spend", 0.0) / 720.0, # Hourly approx
        "cpu_avg": snapshot.get("cpu_avg", 0.0),
        "capacity": snapshot.get("capacity", 1.0),
        "dropped_requests": workload.get("dropped_requests", 0),
        "queue_ms": workload.get("queue_total_ms", 0.0)
    }

    weights = {k: scoring_profile.get(k, 0.25) for k in ["wL", "wC", "wE", "wR"]}
    constraints = {
        "target_latency": scoring_profile.get("target_latency_ms", 100.0),
        "budget": scoring_profile.get("budget", 10.0)
    }

    report = DecisionScorer.calculate_score(raw_metrics, weights, constraints)

    # Get Gemini insight
    insight_payload = {
        "scenario_weights": weights,
        "normalized_scores": report["breakdown"],
        "raw_metrics": raw_metrics,
        "final_score": report["score"]
    }

    ai_feedback = _generate_gemini_insight(insight_payload)
    report.update(ai_feedback)
    report["workload_explanation"] = f"Traffic behavior driven by scenario workload patterns for {scenario.get('title')}."

    return report
