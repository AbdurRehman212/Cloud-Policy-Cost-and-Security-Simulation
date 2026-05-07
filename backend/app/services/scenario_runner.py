from __future__ import annotations
import logging
from typing import Dict, List, Optional
from app import simulation_engine

logger = logging.getLogger(__name__)

SCENARIO_WORKLOAD_PATTERNS: Dict[int, List[Dict]] = {
    1: [{"rps": 80, "ticks": 4, "label": "Baseline"}, {"rps": 300, "ticks": 6, "label": "Traffic burst"}, {"rps": 500, "ticks": 4, "label": "Peak overload"}, {"rps": 200, "ticks": 4, "label": "Cooldown"}, {"rps": 80, "ticks": 2, "label": "Recovery"}],
    2: [{"rps": 20, "ticks": 6, "label": "Idle load"}, {"rps": 10, "ticks": 4, "label": "Near-zero"}, {"rps": 50, "ticks": 4, "label": "Right-sized"}, {"rps": 30, "ticks": 6, "label": "Stable low"}],
    3: [{"rps": 60, "ticks": 5, "label": "Normal"}, {"rps": 75, "ticks": 5, "label": "Slightly elevated"}, {"rps": 60, "ticks": 5, "label": "Normal"}, {"rps": 55, "ticks": 5, "label": "Baseline"}],
    4: [{"rps": 150, "ticks": 3, "label": "Pre-outage"}, {"rps": 0, "ticks": 4, "label": "Outage"}, {"rps": 50, "ticks": 3, "label": "Recovery ramp"}, {"rps": 120, "ticks": 4, "label": "Restored"}, {"rps": 150, "ticks": 6, "label": "Healthy steady"}],
}
_DEFAULT_PATTERN = [{"rps": 100, "ticks": 10, "label": "Default"}]

def expand_pattern(pattern: List[Dict]) -> List[int]:
    result: List[int] = []
    for seg in pattern:
        result.extend([seg["rps"]] * seg["ticks"])
    return result

class ScenarioRunner:
    def start(self, scenario_id: int, org_id: int) -> dict:
        if simulation_engine.is_scenario_running(org_id):
            return {"ok": False, "error": "A scenario is already running.", "code": "scenario_already_running"}
        
        pattern = SCENARIO_WORKLOAD_PATTERNS.get(scenario_id, _DEFAULT_PATTERN)
        rps_sequence = expand_pattern(pattern)
        
        if simulation_engine.start_scenario(org_id=org_id, workload_pattern=rps_sequence, scenario_id=scenario_id):
            return {"ok": True, "scenario_id": scenario_id, "org_id": org_id, "total_ticks": len(rps_sequence), "workload_pattern": pattern}
        return {"ok": False, "error": "Failed to start scenario.", "code": "scenario_error"}

    def stop(self, org_id: int) -> None:
        simulation_engine.stop_scenario(org_id)

    def get_state(self, org_id: int) -> dict:
        return simulation_engine.get_state(org_id)

scenario_runner = ScenarioRunner()
