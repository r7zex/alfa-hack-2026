"""Separate IE contract, pending an agreed experiment and actual IE data."""
from pathlib import Path
from ml.eda_entrepreneur import prepare_ie
from ml.train_legal import ScoringError

DEFAULT_ARTIFACT = Path(__file__).resolve().parents[1] / "artifacts/model_entrepreneur.joblib"


def train_ie(csv_path, artifact_path=DEFAULT_ARTIFACT, *, feature_names=None):
    prepare_ie(csv_path, feature_names=feature_names)
    raise ScoringError("IE training experiment is not specified; no weights were written")


def predict_ie(artifact_path=DEFAULT_ARTIFACT, features=None, *, training_csv=None, **kwargs):
    raise ScoringError("IE inference is unavailable: an agreed IE experiment and artifact are required")
