"""In-memory loader for the core cloud simulator dataset."""

from __future__ import annotations

import logging
from pathlib import Path
from threading import Lock

import pandas as pd
from pandas.api.types import is_numeric_dtype


REQUIRED_COLUMNS = (
    'time',
    'scheduling_class',
    'collection_type',
    'priority',
    'cpu_req',
    'mem_req',
    'cpu_avg',
    'mem_avg',
    'cpu_max',
    'mem_max',
)

COLUMN_DTYPES = {
    'time': 'int64',
    'scheduling_class': 'int16',
    'collection_type': 'int16',
    'priority': 'int32',
    'cpu_req': 'float32',
    'mem_req': 'float32',
    'cpu_avg': 'float32',
    'mem_avg': 'float32',
    'cpu_max': 'float32',
    'mem_max': 'float32',
}

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = BACKEND_ROOT / 'data' / 'dataset-3k-final.csv'

logger = logging.getLogger(__name__)

_dataset: pd.DataFrame | None = None
_dataset_lock = Lock()


def _validate_dataset(frame: pd.DataFrame) -> None:
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing_columns:
        raise ValueError(f'Dataset is missing required columns: {", ".join(missing_columns)}')

    non_numeric_columns = [
        column for column in REQUIRED_COLUMNS
        if not is_numeric_dtype(frame[column])
    ]
    if non_numeric_columns:
        raise ValueError(f'Dataset columns must be numeric: {", ".join(non_numeric_columns)}')

    columns_with_missing_values = [
        column for column in REQUIRED_COLUMNS
        if frame[column].isna().any()
    ]
    if columns_with_missing_values:
        logger.warning(
            'Simulator dataset contains missing values in numeric columns: %s',
            ', '.join(columns_with_missing_values),
        )


def _freeze_dataframe(frame: pd.DataFrame) -> None:
    """Mark underlying column arrays as read-only to prevent accidental mutation."""
    # NOTE: allows_duplicate_labels=False removed — pandas propagates this flag to every
    # .iloc slice result via __finalize__, causing DuplicateLabelError on random samples.
    # Block-level writeable=False is sufficient to guard against accidental mutation.
    for block in frame._mgr.blocks:
        block.values.flags.writeable = False


def load_dataset() -> pd.DataFrame:
    """Load the simulator CSV once and keep it cached in memory."""
    global _dataset

    if _dataset is not None:
        return _dataset

    with _dataset_lock:
        if _dataset is not None:
            return _dataset

        if not DATASET_PATH.exists():
            raise FileNotFoundError(f'Simulator dataset not found: {DATASET_PATH}')

        try:
            frame = pd.read_csv(
                DATASET_PATH,
                dtype=COLUMN_DTYPES,
                usecols=lambda column: column in REQUIRED_COLUMNS,
            )
        except ValueError as exc:
            raise ValueError(
                f'Failed to load simulator dataset from {DATASET_PATH}. '
                'Ensure all required columns are present and numeric.'
            ) from exc

        _validate_dataset(frame)
        frame = frame.reindex(columns=REQUIRED_COLUMNS, copy=False)
        frame = frame.reset_index(drop=True)  # Ensure unique integer index to prevent DuplicateLabelError on iloc sampling
        _freeze_dataframe(frame)
        _dataset = frame

        info = dataset_info()
        logger.info(
            'Loaded simulator dataset from %s with %s rows, %s columns, %.4f MB memory usage',
            DATASET_PATH,
            info['rows'],
            len(info['columns']),
            info['memory_usage_mb'],
        )
        return _dataset


def get_dataset() -> pd.DataFrame:
    """Return the cached simulator dataset without touching the filesystem."""
    if _dataset is None:
        raise RuntimeError('Dataset has not been loaded. Call load_dataset() during app startup.')
    return _dataset


def dataset_info() -> dict:
    """Return basic health information for the cached dataset."""
    frame = get_dataset()
    return {
        'rows': int(len(frame)),
        'columns': list(frame.columns),
        'memory_usage_mb': round(float(frame.memory_usage(deep=True).sum()) / (1024 * 1024), 4),
    }
