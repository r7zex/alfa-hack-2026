"""Offline inference for hash-verified imported LightGBM; never loads pickle."""

from __future__ import annotations

from hashlib import sha256
from functools import lru_cache
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT = ROOT / "artifacts" / "LightGBM_native.txt"
ARTIFACT_SHA256 = "8f5b6d91d91873e2bf8df6c2a0e0a796f076faedddf8dc88e82d28ff5393d386"
SOURCE_JOBLIB_SHA256 = "1b9a0de1523b3c6bb64b269c960fafae169b570d9b056f3ea9198e63e3175f82"
FEATURE_NAMES = (
    "asset_turnover_2022",
    "asset_turnover_days_2022",
    "receivables_collection_days_2022",
    "inventory_turnover_days_2022",
    "cash_ratio_2022",
    "quick_ratio_2022",
    "current_ratio_2022",
    "return_on_assets_pct_2022",
    "return_on_equity_pct_2022",
    "operating_profit_margin_pct_2022",
    "net_profit_to_long_term_capital_pct_2022",
    "liabilities_to_assets_pct_2022",
    "liabilities_to_equity_pct_2022",
    "financial_leverage_2022",
    "assets_to_liabilities_2022",
    "borrowings_to_liabilities_pct_2022",
    "business_age",
    "simplified",
    "revenue",
    "net_profit",
    "total_assets",
    "equity",
    "cash",
    "short_term_liabilities",
)


class ImportedModelError(ValueError):
    """A missing, mismatched, or invalid model/data contract."""


def load_native_model(path: Path = DEFAULT_ARTIFACT) -> lgb.Booster:
    """Load a local trusted native text model; no unpickling."""
    try:
        content = Path(path).read_bytes()
    except OSError as exc:
        raise ImportedModelError("Native LightGBM artifact is missing") from exc
    if sha256(content).hexdigest() != ARTIFACT_SHA256:
        raise ImportedModelError("Unexpected native LightGBM model SHA256")
    return _parse_native(content)


@lru_cache(maxsize=2)
def _parse_native(content: bytes) -> lgb.Booster:
    try:
        model = lgb.Booster(model_str=content.decode("utf-8"))
    except (UnicodeError, ValueError, RuntimeError) as exc:
        raise ImportedModelError("Cannot parse LightGBM native artifact") from exc
    if model.feature_name() != list(FEATURE_NAMES) or model.num_trees() != 450:
        raise ImportedModelError("Model feature schema or tree count changed")
    return model


def validate_features(data: Any) -> pd.DataFrame:
    try:
        frame = pd.DataFrame([data] if isinstance(data, dict) else data).copy()
        if frame.empty or frame.columns.duplicated().any():
            raise ValueError("Features must contain at least one row and unique columns")
        missing = set(FEATURE_NAMES) - set(frame.columns)
        extra = set(frame.columns) - set(FEATURE_NAMES)
        if missing or extra:
            raise ValueError(
                f"Feature names mismatch: missing={sorted(missing)}, extra={sorted(extra)}"
            )
        if any(isinstance(v, (str, bool)) for v in frame.to_numpy().ravel() if v is not None):
            raise ValueError("Features must be numeric, not strings or booleans")
        frame = frame.loc[:, FEATURE_NAMES].apply(
            pd.to_numeric, errors="raise"
        ).astype(float)
        if np.isinf(frame.to_numpy()).any() or frame.isna().all(axis=1).any():
            raise ValueError("Features contain infinity or an all-missing row")
        if ((frame["business_age"] < 0) | (frame["business_age"] > 200)).any() or not frame["simplified"].isin([0, 1, np.nan]).all():
            raise ValueError("Invalid business_age or simplified flag")
        return frame
    except (ValueError, TypeError, OverflowError) as exc:
        raise ImportedModelError(str(exc)) from exc


def score_positive_class(data: Any, path: Path = DEFAULT_ARTIFACT) -> dict:
    """Return raw binary class-1 scores; target and threshold are unknown."""
    frame = validate_features(data)
    model = load_native_model(path)
    scores = np.asarray(model.predict(frame, num_threads=1), dtype=float)
    if (
        scores.shape != (len(frame),)
        or not np.isfinite(scores).all()
        or ((scores < 0) | (scores > 1)).any()
    ):
        raise ImportedModelError("Invalid binary output from native LightGBM")
    return {
        "scores": scores.tolist(),
        "artifact_sha256": ARTIFACT_SHA256,
        "kind": "binary_class_1_score",
        "target": "unspecified_in_supplied_artifact",
        "threshold": None,
        "classification": None,
        "calibrated": False,
        "contributions": contributions(model, frame, scores),
    }


def contributions(model, frame, scores):
    values = np.asarray(model.predict(frame, pred_contrib=True, num_threads=1))
    raw = np.asarray(model.predict(frame, raw_score=True, num_threads=1))
    if values.shape != (len(frame), len(FEATURE_NAMES) + 1) or not np.isfinite(values).all():
        raise ImportedModelError("Invalid native feature contributions")
    from scipy.special import expit
    if not np.allclose(values.sum(axis=1), raw, atol=1e-7) or not np.allclose(expit(raw), scores, atol=1e-7):
        raise ImportedModelError("Feature contributions do not reconcile with prediction")
    return [dict(base_value=float(row[-1]), raw_score=float(raw[i]),
                 unit="raw_log_odds_class_1", values={name:float(row[j]) for j,name in enumerate(FEATURE_NAMES)})
            for i,row in enumerate(values)]
