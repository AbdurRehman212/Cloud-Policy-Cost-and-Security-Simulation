"""API routes for dataset-backed simulation metrics."""

from __future__ import annotations

from functools import wraps
import logging

from flask import Blueprint, jsonify, request
from app.utils.dataset_loader import dataset_info

from app.services.simulation_engine import (
    DEFAULT_NOISE_MAX,
    DEFAULT_NOISE_MIN,
    DEFAULT_POINTS,
    DEFAULT_SPIKE_PROBABILITY,
    MAX_POINTS,
    generate_metrics,
    get_cost,
    get_health,
    get_peaks,
    get_summary,
)


simulation_bp = Blueprint('simulation', __name__)
logger = logging.getLogger(__name__)


class RequestValidationError(ValueError):
    """Raised when simulation query parameters are invalid."""


def _success(data, status_code=200):
    payload = {
        'status': 'success',
        'data': data,
    }
    return jsonify(payload), status_code


def _error(message, status_code=500, code='simulation_error'):
    return jsonify({
        'status': 'error',
        'error': {
            'message': message,
        },
    }), status_code


def _guard(handler):
    @wraps(handler)
    def wrapped(*args, **kwargs):
        try:
            return handler(*args, **kwargs)
        except RequestValidationError as exc:
            return _error(str(exc), status_code=400, code='invalid_request')
        except Exception as exc:  # pragma: no cover - defensive API boundary
            logger.exception('Simulation endpoint failed: %s', request.path)
            return _error(
                'Simulation service is temporarily unavailable.',
                status_code=500,
                code='internal_error',
            )

    return wrapped


def _optional_int(name):
    value = request.args.get(name)
    if value is None or value == '':
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise RequestValidationError(f'{name} must be an integer.') from exc


def _optional_float(name):
    value = request.args.get(name)
    if value is None or value == '':
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise RequestValidationError(f'{name} must be a number.') from exc


def _simulation_options():
    points = _optional_int('points')
    seed = _optional_int('seed')
    noise_min = _optional_float('noise_min')
    noise_max = _optional_float('noise_max')
    spike_probability = _optional_float('spike_probability')

    points = DEFAULT_POINTS if points is None else points
    noise_min = DEFAULT_NOISE_MIN if noise_min is None else noise_min
    noise_max = DEFAULT_NOISE_MAX if noise_max is None else noise_max
    spike_probability = DEFAULT_SPIKE_PROBABILITY if spike_probability is None else spike_probability

    if not 1 <= points <= MAX_POINTS:
        raise RequestValidationError(f'points must be between 1 and {MAX_POINTS}.')
    if seed is not None and not 0 <= seed <= 2**32 - 1:
        raise RequestValidationError('seed must be between 0 and 4294967295.')
    if not 0.5 <= noise_min <= 1.0:
        raise RequestValidationError('noise_min must be between 0.5 and 1.0.')
    if not 1.0 <= noise_max <= 1.5:
        raise RequestValidationError('noise_max must be between 1.0 and 1.5.')
    if noise_min >= noise_max:
        raise RequestValidationError('noise_min must be less than noise_max.')
    if not 0.0 <= spike_probability <= 0.30:
        raise RequestValidationError('spike_probability must be between 0.0 and 0.30.')

    return {
        'points': points,
        'seed': seed,
        'noise_min': noise_min,
        'noise_max': noise_max,
        'spike_probability': spike_probability,
    }


@simulation_bp.route('/metrics', methods=['GET'])
@_guard
def metrics():
    options = _simulation_options()
    return _success(generate_metrics(**options))


@simulation_bp.route('/summary', methods=['GET'])
@_guard
def summary():
    return _success(get_summary())


@simulation_bp.route('/peaks', methods=['GET'])
@_guard
def peaks():
    return _success(get_peaks())


@simulation_bp.route('/cost', methods=['GET'])
@_guard
def cost():
    options = _simulation_options()
    return _success(get_cost(**options))


@simulation_bp.route('/health', methods=['GET'])
@_guard
def health():
    health_info = get_health()
    return _success({
        'dataset_loaded': bool(health_info.get('dataset_loaded', False)),
        'rows': int(health_info.get('row_count', 0)),
        'uptime': health_info.get('uptime_seconds', 0),
        'simulation_ready': True,
    })


@simulation_bp.route('/simulation/source', methods=['GET'])
@_guard
def simulation_source():
    info = dataset_info()
    return _success({
        'dataset': 'google_cluster_trace',
        'rows': int(info.get('rows', 0)),
        'fields': ['cpu_avg', 'mem_avg'],
    })
