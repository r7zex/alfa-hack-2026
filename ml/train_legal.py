"""Notebook's final 70/15/15 focal experiment and explicit offline recovery.

Artifacts are trusted local joblib files: never load client-supplied pickle paths.
"""
from dataclasses import dataclass
from pathlib import Path
from contextlib import contextmanager
import hashlib
from io import BytesIO
import json
import os
import subprocess
import sys
import tempfile
import fcntl
import joblib
import numpy as np
import pandas as pd
from scipy.special import expit
from sklearn.metrics import (
    average_precision_score, roc_auc_score, precision_recall_curve,
    precision_score, recall_score, f1_score, fbeta_score, confusion_matrix,
)
from sklearn.model_selection import train_test_split
from ml.eda_legal import prepare_legal

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT = ROOT / "artifacts/model_legal.joblib"
FORMAT_VERSION = 1
GAMMAS = np.arange(0, 7.01, 0.5)
PARAMS = dict(n_estimators=400, learning_rate=0.05, num_leaves=31, max_depth=-1,
              min_child_samples=30, reg_lambda=1.0, random_state=42,
              n_jobs=-1, verbosity=-1)


class ScoringError(ValueError):
    """Controlled model, data or schema failure, never a substitute score."""


@dataclass(frozen=True)
class FocalObjective:
    gamma: float
    pos_weight: float

    def __call__(self, y_true, raw_pred):
        p = expit(np.clip(raw_pred, -20, 20))
        pt = np.where(y_true == 1, p, 1 - p)
        pt = np.clip(pt, 1e-8, 1 - 1e-8)
        q = 1 - pt
        sign = np.where(y_true == 1, 1.0, -1.0)
        weight = np.where(y_true == 1, self.pos_weight, 1.0)
        gamma = self.gamma
        grad = weight * sign * (gamma * pt * q**gamma * np.log(pt) - q**(gamma + 1))
        if gamma == 0:
            hess = weight * pt * q
        else:
            hess = weight * pt * q * (
                q**gamma * (2 * gamma + 1 + gamma * np.log(pt))
                - gamma**2 * pt * q**(gamma - 1) * np.log(pt)
            )
        return grad, np.maximum(hess, 1e-4)


def predict_scores(model, features):
    return expit(model.predict(features, raw_score=True))


def split_data(features, target):
    try:
        x_tv, x_test, y_tv, y_test = train_test_split(
            features, target, test_size=0.15, stratify=target, random_state=42)
        x_train, x_val, y_train, y_val = train_test_split(
            x_tv, y_tv, test_size=0.15 / 0.85, stratify=y_tv, random_state=42)
    except ValueError as exc:
        raise ScoringError(f"Insufficient data for stratified 70/15/15 split: {exc}") from exc
    if any(y.nunique() != 2 for y in (y_train, y_val, y_test)):
        raise ScoringError("Both classes must occur in each split")
    return x_train, x_val, x_test, y_train, y_val, y_test


def choose_threshold(target, scores):
    precision, recall, thresholds = precision_recall_curve(target, scores)
    if len(thresholds) == 0:
        raise ScoringError("Validation scores have no classification thresholds")
    f2 = 5 * precision[:-1] * recall[:-1] / (4 * precision[:-1] + recall[:-1] + 1e-12)
    return float(thresholds[np.argmax(f2)])


def calculate_metrics(target, scores, threshold):
    pred = (scores >= threshold).astype(int)
    return dict(N=len(target), Bankrupt=int(target.sum()), Base_AP=float(target.mean()),
                AP=float(average_precision_score(target, scores)),
                ROC_AUC=float(roc_auc_score(target, scores)),
                Precision=float(precision_score(target, pred, zero_division=0)),
                Recall=float(recall_score(target, pred, zero_division=0)),
                F1=float(f1_score(target, pred, zero_division=0)),
                F2=float(fbeta_score(target, pred, beta=2, zero_division=0)),
                confusion_matrix=confusion_matrix(target, pred, labels=[0, 1]).tolist())


def fit_experiment(features, target):
    from lightgbm import LGBMClassifier
    # Canonical module name also when invoked with python -m ml.train_legal.
    from ml.train_legal import FocalObjective as Objective
    x_train, x_val, x_test, y_train, y_val, y_test = split_data(features, target)
    pos_weight = float(np.sqrt((y_train == 0).sum() / (y_train == 1).sum()))
    rows, models = [], {}
    for gamma in GAMMAS:
        gamma = float(gamma)
        model = LGBMClassifier(objective=Objective(gamma, pos_weight), **PARAMS)
        model.fit(x_train, y_train)
        val_scores = predict_scores(model, x_val)
        rows.append(dict(gamma=gamma, Val_AP=float(average_precision_score(y_val, val_scores)),
                         Val_ROC_AUC=float(roc_auc_score(y_val, val_scores))))
        models[gamma] = model
    # Same pandas sorting / tie behaviour as the final notebook cell.
    comparison = pd.DataFrame(rows).sort_values("Val_AP", ascending=False).reset_index(drop=True)
    gamma = float(comparison.iloc[0]["gamma"])
    model = models[gamma]
    val_scores = predict_scores(model, x_val)
    threshold = choose_threshold(y_val, val_scores)
    metrics = {
        name: calculate_metrics(y, predict_scores(model, x), threshold)
        for name, x, y in (("Train", x_train, y_train), ("Validation", x_val, y_val),
                           ("Test", x_test, y_test))
    }
    return dict(format_version=FORMAT_VERSION, model_type="legal", model=model,
                feature_names=list(features.columns), params=PARAMS.copy(), gamma=gamma,
                threshold=threshold, pos_weight=pos_weight,
                objective={"name": "focal", "gamma": gamma, "pos_weight": pos_weight,
                           "hessian_floor": 1e-4, "raw_score_sigmoid": True},
                metrics=metrics, validation_comparison=comparison.to_dict(orient="records"),
                target="bankrupt", experiment="70/15/15; seed=42; validation AP and F2")


def validate_artifact(artifact):
    try:
        if not isinstance(artifact, dict):
            raise ValueError("Expected a mapping")
        if artifact["format_version"] != FORMAT_VERSION or artifact["model_type"] != "legal":
            raise ValueError("Incompatible format or borrower type")
        names = artifact["feature_names"]
        if not names or len(set(names)) != len(names) or not all(isinstance(n, str) for n in names):
            raise ValueError("Invalid feature names")
        model = artifact["model"]
        if list(model.feature_name_) != names:
            raise ValueError("Model and artifact feature schemas differ")
        if not 0 <= float(artifact["threshold"]) <= 1 or artifact["gamma"] not in GAMMAS:
            raise ValueError("Invalid gamma or threshold")
        objective = artifact["objective"]
        if (objective["name"] != "focal" or objective["raw_score_sigmoid"] is not True
                or objective["gamma"] != artifact["gamma"]
                or objective["hessian_floor"] != 1e-4):
            raise ValueError("Incompatible objective")
        actual_objective = model.get_params()["objective"]
        if (not isinstance(actual_objective, FocalObjective)
                or actual_objective.gamma != artifact["gamma"]
                or actual_objective.pos_weight != objective["pos_weight"]
                or not np.isfinite(objective["pos_weight"]) or objective["pos_weight"] <= 0):
            raise ValueError("Model objective differs from artifact metadata")
    except (KeyError, AttributeError, TypeError, ValueError) as exc:
        raise ScoringError(f"Incompatible legal artifact: {exc}") from exc
    return artifact


def load_artifact(artifact_path):
    try:
        content = Path(artifact_path).read_bytes()
        artifact = validate_artifact(joblib.load(BytesIO(content)))
        artifact["_artifact_id"] = hashlib.sha256(content).hexdigest()
        return artifact
    except ScoringError:
        raise
    except Exception as exc:
        raise ScoringError(f"Cannot load legal artifact: {type(exc).__name__}") from exc


def validate_features(features, names):
    try:
        frame = pd.DataFrame([features] if isinstance(features, dict) else features).copy()
        if frame.empty or frame.columns.duplicated().any():
            raise ValueError("Empty features or duplicate column names")
        missing, extra = set(names) - set(frame), set(frame) - set(names)
        if missing or extra:
            raise ValueError(f"Feature schema mismatch; missing={sorted(missing)}, extra={sorted(extra)}")
        frame = frame.loc[:, names].apply(pd.to_numeric, errors="raise")
        frame = frame.replace([np.inf, -np.inf], np.nan).astype(float)
        if frame.isna().all(axis=1).any():
            raise ValueError("Every customer must have observed financial features")
        return frame
    except (ValueError, TypeError, OverflowError) as exc:
        raise ScoringError(str(exc)) from exc


@contextmanager
def artifact_lock(path):
    """Process/thread-safe Linux lock, also used by the explicit recovery path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(path.suffix + ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def save_artifact(artifact, path, sample, *, allow_replace=False):
    path = Path(path)
    if path.name != "model_legal.joblib":
        raise ScoringError("Legal weights must use filename model_legal.joblib")
    if path.exists() and not allow_replace:
        raise ScoringError("Existing artifact preserved; explicit allow_replace is required")
    validate_artifact(artifact)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".legal-", dir=path.parent)
    os.close(handle)
    try:
        joblib.dump(artifact, temporary)
        # A new interpreter proves that the objective is importable and picklable.
        code = ("import sys,json,joblib; from io import BytesIO; "
                "from ml.train_legal import load_artifact,predict_scores; "
                "a=load_artifact(sys.argv[1]); x=joblib.load(BytesIO(sys.stdin.buffer.read())); "
                "print(json.dumps(predict_scores(a['model'],x).tolist()))")
        payload = BytesIO()
        joblib.dump(sample, payload)
        result = subprocess.run([sys.executable, "-c", code, temporary], cwd=ROOT,
                                input=payload.getvalue(), capture_output=True, timeout=120)
        if result.returncode:
            raise ScoringError("Artifact failed prediction check in a new process")
        if not np.allclose(json.loads(result.stdout), predict_scores(artifact["model"], sample),
                           rtol=1e-8, atol=1e-10):
            raise ScoringError("Predictions changed after joblib reload")
        if allow_replace:
            os.replace(temporary, path)
        else:
            os.link(temporary, path)  # Atomic create; never overwrites another process.
    except FileExistsError as exc:
        raise ScoringError("Existing artifact preserved") from exc
    finally:
        Path(temporary).unlink(missing_ok=True)


def _train(csv_path, artifact_path, allow_replace):
    try:
        features, target = prepare_legal(csv_path)
        artifact = fit_experiment(features, target)
        save_artifact(artifact, artifact_path, features.head(8), allow_replace=allow_replace)
        return artifact
    except ScoringError:
        raise
    except (OSError, ValueError) as exc:
        raise ScoringError(f"Cannot train legal model: {exc}") from exc


def train_legal(csv_path, artifact_path=DEFAULT_ARTIFACT, *, allow_replace=False):
    with artifact_lock(artifact_path):
        if Path(artifact_path).exists() and not allow_replace:
            raise ScoringError("Existing artifact preserved; explicit allow_replace is required")
        return _train(csv_path, artifact_path, allow_replace)


def predict_legal(artifact_path=DEFAULT_ARTIFACT, features=None, *, training_csv=None,
                  allow_retrain=False, allow_replace=False):
    def ready():
        artifact = load_artifact(artifact_path)
        return artifact, validate_features(features, artifact["feature_names"])
    try:
        artifact, frame = ready()
    except ScoringError:
        if not allow_retrain or training_csv is None:
            raise
        with artifact_lock(artifact_path):
            # Another request/process may already have recovered it.
            try:
                artifact, frame = ready()
            except ScoringError:
                if Path(artifact_path).exists() and not allow_replace:
                    raise ScoringError("Recovery needs explicit allow_replace for an existing artifact")
                try:
                    train_features, _ = prepare_legal(training_csv)
                except ValueError as exc:
                    raise ScoringError(f"Cannot prepare fallback CSV: {exc}") from exc
                validate_features(features, list(train_features.columns))
                _train(training_csv, artifact_path, allow_replace)
                artifact, frame = ready()
    scores = predict_scores(artifact["model"], frame)
    if not np.isfinite(scores).all():
        raise ScoringError("Model returned non-finite scores")
    return dict(scores=scores.tolist(), classifications=(scores >= artifact["threshold"]).astype(int).tolist(),
                threshold=artifact["threshold"], model_type="legal", artifact_version=FORMAT_VERSION,
                artifact_id=artifact["_artifact_id"],
                target="bankrupt")


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--allow-replace", action="store_true")
    args = parser.parse_args()
    artifact = train_legal(args.csv_path, allow_replace=args.allow_replace)
    print(json.dumps({k: artifact[k] for k in ("gamma", "threshold", "metrics")}, indent=2))


if __name__ == "__main__":
    # Keep training, objective type checks and pickle imports in one module identity.
    from ml.train_legal import main as canonical_main
    canonical_main()
