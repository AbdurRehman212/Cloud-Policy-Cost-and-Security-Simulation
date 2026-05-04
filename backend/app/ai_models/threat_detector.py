"""Threat detector for the simulator using real dataset training when available."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd

from app.data_sources.real_datasets import dataset_catalog

try:  # Optional dependency when TensorFlow/Keras is installed.
    from tensorflow.keras import Sequential
    from tensorflow.keras.layers import Dense, Dropout
except Exception:  # pragma: no cover - optional dependency
    Sequential = None
    Dense = None
    Dropout = None

try:  # Optional lightweight fallback.
    from sklearn.model_selection import train_test_split
    from sklearn.neural_network import MLPClassifier
    from sklearn.preprocessing import StandardScaler
except Exception:  # pragma: no cover - optional dependency
    train_test_split = None
    MLPClassifier = None
    StandardScaler = None


THREAT_LABELS = {
    0: 'normal',
    1: 'ddos',
    2: 'brute_force',
}


@dataclass
class ThreatDetector:
    """Train a small DNN or MLP classifier on a staged real dataset when available."""

    def __post_init__(self):
        self.model = None
        self.scaler = None
        self.backend = 'heuristic'
        self.feature_columns = [
            'requests_per_minute',
            'avg_latency_ms',
            'error_rate',
            'bytes_in',
            'bytes_out',
            'active_connections',
            'cpu_utilization',
            'memory_utilization',
            'disk_read_iops',
            'disk_write_iops',
            'network_in_mbps',
            'network_out_mbps',
            'auth_failures',
        ]
        self._train_if_possible()

    def _training_frame(self) -> pd.DataFrame:
        frame = dataset_catalog.load_security_frame()
        if frame.empty or 'label' not in frame.columns:
            return pd.DataFrame()
        for column in self.feature_columns:
            if column not in frame.columns:
                frame[column] = 0.0
        return frame

    def train_from_frame(self, frame: pd.DataFrame):
        """Train from a real staged dataset frame."""
        if frame is None or frame.empty or 'label' not in frame.columns:
            return False
        for column in self.feature_columns:
            if column not in frame.columns:
                frame[column] = 0.0
        if len(frame) < 20:
            return False

        X = frame[self.feature_columns].fillna(0.0).astype(float)
        y = frame['label'].astype(int)

        if Sequential is not None:
            self.backend = 'tensorflow'
            self.scaler = StandardScaler() if StandardScaler is not None else None
            X_scaled = self.scaler.fit_transform(X) if self.scaler is not None else X.to_numpy()
            self.model = Sequential([
                Dense(32, activation='relu', input_shape=(X_scaled.shape[1],)),
                Dropout(0.2),
                Dense(16, activation='relu'),
                Dense(3, activation='softmax'),
            ])
            self.model.compile(optimizer='adam', loss='sparse_categorical_crossentropy', metrics=['accuracy'])
            self.model.fit(X_scaled, y, epochs=8, batch_size=32, verbose=0)
            return True

        if MLPClassifier is not None:
            self.backend = 'sklearn'
            self.scaler = StandardScaler() if StandardScaler is not None else None
            X_scaled = self.scaler.fit_transform(X) if self.scaler is not None else X.to_numpy()
            self.model = MLPClassifier(hidden_layer_sizes=(32, 16), max_iter=500, random_state=42)
            self.model.fit(X_scaled, y)
            return True

        self.backend = 'heuristic'
        return False

    def _train_if_possible(self):
        frame = self._training_frame()
        if frame.empty:
            self.backend = 'heuristic'
            return
        self.train_from_frame(frame)

    def _feature_frame(self, metrics):
        row = {column: float(metrics.get(column, 0) or 0) for column in self.feature_columns}
        return pd.DataFrame([row])

    def real_time_monitor(self, metrics):
        """Return the threat verdict for a single metrics snapshot."""
        snapshot = metrics or {}
        frame = self._feature_frame(snapshot)

        if self.backend == 'tensorflow' and self.model is not None:
            X = self.scaler.transform(frame) if self.scaler is not None else frame.to_numpy()
            probabilities = self.model.predict(X, verbose=0)[0]
            label = int(np.argmax(probabilities))
            confidence = float(probabilities[label])
            return self._format_result(label, confidence, snapshot)

        if self.backend == 'sklearn' and self.model is not None:
            X = self.scaler.transform(frame) if self.scaler is not None else frame.to_numpy()
            probabilities = self.model.predict_proba(X)[0]
            label = int(np.argmax(probabilities))
            confidence = float(probabilities[label])
            return self._format_result(label, confidence, snapshot)

        return self._heuristic_monitor(snapshot)

    def analyze_traffic_logs(self, traffic_frame: pd.DataFrame):
        """Analyze a dataframe of traffic logs and return a summary."""
        if traffic_frame is None or traffic_frame.empty:
            return {'total': 0, 'threats': 0, 'results': []}
        results = [self.real_time_monitor(row.to_dict()) for _, row in traffic_frame.iterrows()]
        return {
            'total': len(results),
            'threats': len([r for r in results if r.get('is_threat')]),
            'results': results,
        }

    def _heuristic_monitor(self, metrics):
        requests_per_minute = float(metrics.get('requests_per_minute', 0) or 0)
        error_rate = float(metrics.get('error_rate', 0) or 0)
        avg_latency_ms = float(metrics.get('avg_latency_ms', 0) or 0)
        auth_failures = float(metrics.get('auth_failures', 0) or 0)
        network_in = float(metrics.get('network_in_mbps', 0) or 0)
        network_out = float(metrics.get('network_out_mbps', 0) or 0)
        cpu = float(metrics.get('cpu_utilization', 0) or 0)

        if requests_per_minute > 5000 or network_in > 250 or network_out > 250:
            return self._format_result(1, 0.92, metrics)
        if auth_failures > 20 or (requests_per_minute < 1500 and error_rate > 0.08):
            return self._format_result(2, 0.88, metrics)
        if avg_latency_ms > 300 or error_rate > 0.15 or cpu > 90:
            return self._format_result(1, 0.79, metrics)
        return self._format_result(0, 0.96, metrics)

    def _format_result(self, label, confidence, metrics):
        threat_type = THREAT_LABELS.get(label, 'normal')
        is_threat = threat_type != 'normal'
        return {
            'is_threat': is_threat,
            'threat_type': threat_type,
            'confidence': round(float(confidence), 4),
            'source': self.backend,
            'detected_at': datetime.utcnow().isoformat(),
            'signals': {
                'requests_per_minute': metrics.get('requests_per_minute'),
                'avg_latency_ms': metrics.get('avg_latency_ms'),
                'error_rate': metrics.get('error_rate'),
                'network_in_mbps': metrics.get('network_in_mbps'),
                'network_out_mbps': metrics.get('network_out_mbps'),
                'auth_failures': metrics.get('auth_failures'),
            },
        }


threat_detector = ThreatDetector()
