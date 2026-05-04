"""Dataset-backed CPU and memory simulation engine.

The module has no Flask imports. REST routes and SocketIO background tasks both
call this service so simulation behavior stays consistent across transports.
"""

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
    if priority < 100:
        return 0.8
    if priority <= 250:
        return 1.0
    if priority <= 400:
        return 1.2
    return 1.5


def _sample_arrays(
    options: SimulationOptions,
    generator: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    dataset = get_dataset()
    if dataset.empty:
        raise RuntimeError('Simulator dataset is empty.')

    row_indices = generator.integers(0, len(dataset), size=options.points)
    sample = dataset.iloc[row_indices]

    cpu_avg = sample['cpu_avg'].to_numpy(dtype=np.float32, copy=False)
    mem_avg = sample['mem_avg'].to_numpy(dtype=np.float32, copy=False)
    cpu_max = sample['cpu_max'].to_numpy(dtype=np.float32, copy=False)
    mem_max = sample['mem_max'].to_numpy(dtype=np.float32, copy=False)
    priority = sample['priority'].to_numpy(dtype=np.float32, copy=False)

    cpu_avg = np.maximum(np.nan_to_num(cpu_avg, nan=MIN_METRIC_VALUE), MIN_METRIC_VALUE)
    mem_avg = np.maximum(np.nan_to_num(mem_avg, nan=MIN_METRIC_VALUE), MIN_METRIC_VALUE)
    cpu_max = np.where(np.isnan(cpu_max), cpu_avg, cpu_max)
    mem_max = np.where(np.isnan(mem_max), mem_avg, mem_max)
    priority = np.nan_to_num(priority, nan=200.0)

    return cpu_avg, mem_avg, np.maximum(cpu_avg, cpu_max), np.maximum(mem_avg, mem_max), priority


def _apply_noise(
    base_values: np.ndarray,
    options: SimulationOptions,
    generator: np.random.Generator,
) -> np.ndarray:
    noise = generator.uniform(options.noise_min, options.noise_max, size=base_values.shape)
    return base_values * noise


def _apply_spikes(
    values: np.ndarray,
    base_values: np.ndarray,
    peak_values: np.ndarray,
    options: SimulationOptions,
    generator: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    spike_mask = generator.random(size=values.shape) < options.spike_probability
    if not spike_mask.any():
        return values, spike_mask

    weights = generator.uniform(SPIKE_WEIGHT_MIN, SPIKE_WEIGHT_MAX, size=values.shape)
    spiked_values = (base_values * (1.0 - weights)) + (peak_values * weights)
    result = values.copy()
    result[spike_mask] = np.maximum(result[spike_mask], spiked_values[spike_mask])

    # Carry a smaller aftershock into the next point so spikes look like short
    # incidents instead of isolated random dots.
    for index in np.where(spike_mask)[0]:
        if index + 1 < len(result):
            result[index + 1] = max(result[index + 1], (result[index] * 0.45) + (values[index + 1] * 0.55))

    return result, spike_mask


def _smooth(values: np.ndarray) -> np.ndarray:
    if len(values) <= 1:
        return values

    smoothed = values.astype(np.float64, copy=True)
    for index in range(1, len(smoothed)):
        smoothed[index] = (values[index] * SMOOTHING_ALPHA) + (smoothed[index - 1] * (1.0 - SMOOTHING_ALPHA))
    return smoothed


def _build_series(options: SimulationOptions) -> tuple[list[dict], dict]:
    generator = _rng(options.seed)
    cpu_avg, mem_avg, cpu_max, mem_max, priority = _sample_arrays(options, generator)

    cpu_values, cpu_spike_mask = _apply_spikes(
        _apply_noise(cpu_avg, options, generator),
        cpu_avg,
        cpu_max,
        options,
        generator,
    )
    memory_values, memory_spike_mask = _apply_spikes(
        _apply_noise(mem_avg, options, generator),
        mem_avg,
        mem_max,
        options,
        generator,
    )

    cpu_values = np.maximum(_smooth(cpu_values), MIN_METRIC_VALUE)
    memory_values = np.maximum(_smooth(memory_values), MIN_METRIC_VALUE)
    anomaly_mask = cpu_spike_mask | (cpu_values >= (cpu_avg * ANOMALY_MULTIPLIER))

    start_time = datetime.now(timezone.utc)
    metrics = [
        {
            'time': _format_time(start_time + timedelta(seconds=index * METRIC_INTERVAL_SECONDS)),
            'cpu': _round_metric(cpu_values[index]),
            'memory': _round_metric(memory_values[index]),
            'anomaly': bool(anomaly_mask[index]),
            'anomaly_reason': 'cpu_spike' if bool(anomaly_mask[index]) else None,
        }
        for index in range(options.points)
    ]

    stats = {
        'cpu_avg': float(np.mean(cpu_values)),
        'mem_avg': float(np.mean(memory_values)),
        'priority_avg': float(np.mean(priority)),
        'anomaly_count': int(np.sum(anomaly_mask)),
        'memory_spike_count': int(np.sum(memory_spike_mask)),
    }
    return metrics, stats


def generate_metrics(
    points: int = DEFAULT_POINTS,
    seed: int | None = None,
    noise_min: float = DEFAULT_NOISE_MIN,
    noise_max: float = DEFAULT_NOISE_MAX,
    spike_probability: float = DEFAULT_SPIKE_PROBABILITY,
) -> list[dict]:
    """Generate simulated CPU and memory time-series points."""
    options = SimulationOptions(
        points=points,
        seed=seed,
        noise_min=noise_min,
        noise_max=noise_max,
        spike_probability=spike_probability,
    )
    metrics, _ = _build_series(options)
    return metrics


@lru_cache(maxsize=1)
def get_summary() -> dict:
    """Return aggregate CPU and memory statistics from the cached dataset."""
    dataset = get_dataset()
    return {
        'cpu_avg': _round_metric(dataset['cpu_avg'].mean(skipna=True)),
        'cpu_max': _round_metric(dataset['cpu_max'].max(skipna=True)),
        'mem_avg': _round_metric(dataset['mem_avg'].mean(skipna=True)),
        'mem_max': _round_metric(dataset['mem_max'].max(skipna=True)),
    }


@lru_cache(maxsize=1)
def get_peaks() -> dict:
    """Return peak CPU and memory values from the cached dataset."""
    dataset = get_dataset()
    return {
        'cpu_peak': _round_metric(dataset['cpu_max'].max(skipna=True)),
        'memory_peak': _round_metric(dataset['mem_max'].max(skipna=True)),
    }


def get_cost(
    points: int = DEFAULT_POINTS,
    seed: int | None = None,
    noise_min: float = DEFAULT_NOISE_MIN,
    noise_max: float = DEFAULT_NOISE_MAX,
    spike_probability: float = DEFAULT_SPIKE_PROBABILITY,
) -> dict:
    """Return a cost estimate based on the same simulated sample model."""
    options = SimulationOptions(
        points=points,
        seed=seed,
        noise_min=noise_min,
        noise_max=noise_max,
        spike_probability=spike_probability,
    )
    _, stats = _build_series(options)
    factor = _priority_factor(stats['priority_avg'])
    cost = (stats['cpu_avg'] * CPU_RATE + stats['mem_avg'] * MEM_RATE) * factor

    recommendation = 'Usage is within the expected simulated range.'
    if stats['anomaly_count'] > max(1, options.points * 0.15):
        recommendation = 'CPU anomalies are elevated. Review workload scheduling or autoscaling limits.'
    elif stats['cpu_avg'] > 0.08 and stats['mem_avg'] < 0.02:
        recommendation = 'CPU pressure is higher than memory pressure. Consider compute-optimized sizing.'

    return {
        'cpu_avg': _round_metric(stats['cpu_avg']),
        'mem_avg': _round_metric(stats['mem_avg']),
        'priority_factor': round(factor, 2),
        'cost': round(float(cost), 6),
        'anomaly_count': stats['anomaly_count'],
        'recommendation': recommendation,
    }


def get_health() -> dict:
    """Return simulation service health information."""
    info = dataset_info()
    return {
        'service': 'simulation',
        'status': 'ok',
        'dataset_loaded': True,
        'row_count': info['rows'],
        'uptime_seconds': round(monotonic() - _SERVICE_STARTED_MONOTONIC, 2),
        'started_at': _format_time(_SERVICE_STARTED_AT),
        'dataset': {
            'status': 'loaded',
            **info,
        },
    }
