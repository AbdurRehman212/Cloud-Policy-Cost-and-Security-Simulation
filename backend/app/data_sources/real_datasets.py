"""Helpers for locating and loading real datasets.

The project is configured to use real public datasets only. The repository
does not ship those datasets directly; instead, place preprocessed exports
under the configured data directories and the helpers below will discover them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from app.config import Config


TABULAR_EXTENSIONS = {'.csv', '.tsv', '.json', '.jsonl'}


def _read_tabular_file(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == '.csv':
        return pd.read_csv(path)
    if suffix == '.tsv':
        return pd.read_csv(path, sep='\t')
    if suffix == '.jsonl':
        return pd.read_json(path, lines=True)
    if suffix == '.json':
        return pd.read_json(path)
    raise ValueError(f'Unsupported tabular file type: {path}')


def _discover_tabular_files(base_path: Path) -> list[Path]:
    if not base_path.exists():
        return []
    return sorted(
        path for path in base_path.rglob('*')
        if path.is_file() and path.suffix.lower() in TABULAR_EXTENSIONS
    )


@dataclass
class RealDatasetCatalog:
    """Discover and load preprocessed real datasets."""

    finops_path: Path = Path(Config.FINOPS_DATASET_PATH)
    security_path: Path = Path(Config.SECURITY_DATASET_PATH)
    simulator_core_path: Path = Path(Config.SIMULATOR_CORE_DATASET_PATH)

    def list_available_files(self) -> dict[str, list[str]]:
        return {
            'finops': [str(path) for path in _discover_tabular_files(self.finops_path)],
            'security': [str(path) for path in _discover_tabular_files(self.security_path)],
            'simulator_core': [str(path) for path in _discover_tabular_files(self.simulator_core_path)],
        }

    def load_finops_frame(self) -> pd.DataFrame:
        return self._load_frame(self.finops_path)

    def load_security_frame(self) -> pd.DataFrame:
        return self._load_frame(self.security_path)

    def load_simulator_core_frame(self) -> pd.DataFrame:
        return self._load_frame(self.simulator_core_path)

    def _load_frame(self, base_path: Path) -> pd.DataFrame:
        files = _discover_tabular_files(base_path)
        if not files:
            return pd.DataFrame()
        frames = [_read_tabular_file(path) for path in files]
        return pd.concat(frames, ignore_index=True, sort=False)


dataset_catalog = RealDatasetCatalog()
