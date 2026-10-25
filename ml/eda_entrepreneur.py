"""IE input validation; no legal-entity transformations are applied."""
from pathlib import Path
from collections.abc import Sequence
import numpy as np
import pandas as pd
from ml.eda_legal import read_labeled_csv, FORBIDDEN


def prepare_ie(csv_path: str | Path, *, feature_names: Sequence[str] | None = None):
    frame, target = read_labeled_csv(csv_path)
    if not feature_names:
        raise ValueError("IE feature specification is unavailable; supply an agreed schema")
    names = list(feature_names)
    if len(set(names)) != len(names) or any(n in FORBIDDEN or n.endswith("_id") for n in names):
        raise ValueError("IE feature schema contains identifiers, target or duplicates")
    if set(names) - set(frame):
        raise ValueError(f"Missing IE features: {sorted(set(names) - set(frame))}")
    features = frame[names].apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
    if features.isna().all().any():
        raise ValueError("IE schema contains unusable numeric features")
    return features, target
