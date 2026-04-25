"""SocketIO background streamer for live simulation metrics."""

from __future__ import annotations

import logging
from threading import Lock

from app import socketio
from app.services.simulation_engine import METRIC_INTERVAL_SECONDS, generate_metrics


logger = logging.getLogger(__name__)


class MetricsStreamer:
    """Emit live simulation points to connected SocketIO clients."""

    def __init__(self):
        self._lock = Lock()
        self._running = False

    def start(self):
        with self._lock:
            if self._running:
                return
            self._running = True
            socketio.start_background_task(self._stream_loop)
            logger.info('Simulation metrics SocketIO streamer started')

    def stop(self):
        with self._lock:
            self._running = False

    def _stream_loop(self):
        while self._running:
            try:
                metric = generate_metrics(points=1)[0]
                socketio.emit('metrics:update', {
                    'status': 'success',
                    'data': metric,
                })
            except Exception:  # pragma: no cover - defensive background loop
                logger.exception('Failed to emit live simulation metric')
                socketio.emit('metrics:error', {
                    'status': 'error',
                    'error': {
                        'code': 'stream_error',
                        'message': 'Live metrics stream is temporarily unavailable.',
                    },
                })
            socketio.sleep(METRIC_INTERVAL_SECONDS)


metrics_streamer = MetricsStreamer()
