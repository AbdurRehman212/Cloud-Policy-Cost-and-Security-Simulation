"""Dataset-backed CPU and memory simulation engine (Legacy)."""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from time import monotonic
import numpy as np
from app.utils.dataset_loader import dataset_info, get_dataset

DEFAULT_POINTS = 30
MAX_POINTS = 100
METRIC_INTERVAL_SECONDS = 5
DEFAULT_NOISE_MIN = 0.9
DEFAULT_NOISE_MAX = 1.1
DEFAULT_SPIKE_PROBABILITY = 0.10
SPIKE_WEIGHT_MIN = 0.55
SPIKE_WEIGHT_MAX = 0.85
SMOOTHING_ALPHA = 0.42
ANOMALY_MULTIPLIER = 1.6
MIN_METRIC_VALUE = 0.0001
CPU_RATE = 0.12
MEM_RATE = 0.08

_SERVICE_STARTED_AT = datetime.now(timezone.utc)
_SERVICE_STARTED_MONOTONIC = monotonic()

@dataclass(frozen=True)
class SimulationOptions:
    points: int = DEFAULT_POINTS
    seed: int | None = None
    noise_min: float = DEFAULT_NOISE_MIN
    noise_max: float = DEFAULT_NOISE_MAX
    spike_probability: float = DEFAULT_SPIKE_PROBABILITY

def _round_metric(value: float) -> float:
    return round(float(max(MIN_METRIC_VALUE, value)), 6)

def _format_time(moment: datetime) -> str:
    return moment.isoformat(timespec='seconds').replace('+00:00', 'Z')

def _rng(seed: int | None = None) -> np.random.Generator:
    return np.random.default_rng(seed)

def _priority_factor(priority: float) -> float:
    if priority < 100: return 0.8
    if priority <= 250: return 1.0
    if priority <= 400: return 1.2
    return 1.5

def _sample_arrays(options: SimulationOptions, generator: np.random.Generator):
    dataset = get_dataset()
    if dataset.empty: raise RuntimeError('Simulator dataset is empty.')
    row_indices = generator.integers(0, len(dataset), size=options.points)
    sample = dataset.iloc[row_indices]
    cpu_avg = np.maximum(np.nan_to_num(sample['cpu_avg'].to_numpy(dtype=np.float32), nan=MIN_METRIC_VALUE), MIN_METRIC_VALUE)
    mem_avg = np.maximum(np.nan_to_num(sample['mem_avg'].to_numpy(dtype=np.float32), nan=MIN_METRIC_VALUE), MIN_METRIC_VALUE)
    cpu_max = np.where(np.isnan(sample['cpu_max'].to_numpy()), cpu_avg, sample['cpu_max'].to_numpy())
    mem_max = np.where(np.isnan(sample['mem_max'].to_numpy()), mem_avg, sample['mem_max'].to_numpy())
    priority = np.nan_to_num(sample['priority'].to_numpy(), nan=200.0)
    return cpu_avg, mem_avg, np.maximum(cpu_avg, cpu_max), np.maximum(mem_avg, mem_max), priority

def _apply_noise(base_values, options, generator):
    return base_values * generator.uniform(options.noise_min, options.noise_max, size=base_values.shape)

def _apply_spikes(values, base_values, peak_values, options, generator):
    spike_mask = generator.random(size=values.shape) < options.spike_probability
    if not spike_mask.any(): return values, spike_mask
    weights = generator.uniform(SPIKE_WEIGHT_MIN, SPIKE_WEIGHT_MAX, size=values.shape)
    result = values.copy()
    result[spike_mask] = np.maximum(result[spike_mask], (base_values * (1.0 - weights) + peak_values * weights)[spike_mask])
    for index in np.where(spike_mask)[0]:
        if index + 1 < len(result): result[index+1] = max(result[index+1], result[index]*0.45 + values[index+1]*0.55)
    return result, spike_mask

def _smooth(values):
    if len(values) <= 1: return values
    smoothed = values.astype(np.float64, copy=True)
    for i in range(1, len(smoothed)): smoothed[i] = values[i]*SMOOTHING_ALPHA + smoothed[i-1]*(1.0-SMOOTHING_ALPHA)
    return smoothed

def _build_series(options: SimulationOptions):
    generator = _rng(options.seed)
    cpu_avg, mem_avg, cpu_max, mem_max, priority = _sample_arrays(options, generator)
    cpu_values, cpu_spike_mask = _apply_spikes(_apply_noise(cpu_avg, options, generator), cpu_avg, cpu_max, options, generator)
    memory_values, memory_spike_mask = _apply_spikes(_apply_noise(mem_avg, options, generator), mem_avg, mem_max, options, generator)
    cpu_values, memory_values = np.maximum(_smooth(cpu_values), MIN_METRIC_VALUE), np.maximum(_smooth(memory_values), MIN_METRIC_VALUE)
    anomaly_mask = cpu_spike_mask | (cpu_values >= (cpu_avg * ANOMALY_MULTIPLIER))
    start_time = datetime.now(timezone.utc)
    metrics = [{'time': _format_time(start_time + timedelta(seconds=i*METRIC_INTERVAL_SECONDS)), 'cpu': _round_metric(cpu_values[i]), 'memory': _round_metric(memory_values[i]), 'anomaly': bool(anomaly_mask[i]), 'anomaly_reason': 'cpu_spike' if bool(anomaly_mask[i]) else None} for i in range(options.points)]
    stats = {'cpu_avg': float(np.mean(cpu_values)), 'mem_avg': float(np.mean(memory_values)), 'priority_avg': float(np.mean(priority)), 'anomaly_count': int(np.sum(anomaly_mask)), 'memory_spike_count': int(np.sum(memory_spike_mask))}
    return metrics, stats

def generate_metrics(points=DEFAULT_POINTS, **kwargs):
    m, _ = _build_series(SimulationOptions(points=points, **kwargs))
    return m

@lru_cache(maxsize=1)
def get_summary():
    d = get_dataset()
    return {'cpu_avg': _round_metric(d['cpu_avg'].mean()), 'cpu_max': _round_metric(d['cpu_max'].max()), 'mem_avg': _round_metric(d['mem_avg'].mean()), 'mem_max': _round_metric(d['mem_max'].max())}

@lru_cache(maxsize=1)
def get_peaks():
    d = get_dataset()
    return {'cpu_peak': _round_metric(d['cpu_max'].max()), 'memory_peak': _round_metric(d['mem_max'].max())}

def get_cost(points=DEFAULT_POINTS, **kwargs):
    _, s = _build_series(SimulationOptions(points=points, **kwargs))
    f = _priority_factor(s['priority_avg'])
    cost = (s['cpu_avg']*CPU_RATE + s['mem_avg']*MEM_RATE)*f
    rec = 'Usage is within range.'
    if s['anomaly_count'] > max(1, points*0.15): rec = 'Elevated CPU anomalies.'
    return {'cpu_avg': _round_metric(s['cpu_avg']), 'mem_avg': _round_metric(s['mem_avg']), 'priority_factor': round(f, 2), 'cost': round(float(cost), 6), 'anomaly_count': s['anomaly_count'], 'recommendation': rec}

def get_health():
    info = dataset_info()
    return {'service': 'simulation', 'status': 'ok', 'dataset_loaded': True, 'row_count': info['rows'], 'uptime_seconds': round(monotonic() - _SERVICE_STARTED_MONOTONIC, 2), 'started_at': _format_time(_SERVICE_STARTED_AT)}
