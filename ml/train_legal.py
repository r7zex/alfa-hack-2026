"""Standard binary-log-loss LightGBM; validation AP selection and F2 threshold.

Artifacts contain checksum JSON and native model text; pickle is never loaded.
"""
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
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score, roc_auc_score, precision_recall_curve,
    precision_score, recall_score, f1_score, fbeta_score, confusion_matrix,
)
from sklearn.model_selection import train_test_split
from ml.eda_legal import prepare_legal

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT = ROOT / "artifacts/model_legal.joblib"
FORMAT_VERSION = 2
CANDIDATES = (15, 31, 63)
PARAMS = dict(n_estimators=400, learning_rate=0.05, num_leaves=31, max_depth=-1,
              min_child_samples=30, reg_lambda=1.0, random_state=42,
              n_jobs=-1, verbosity=-1)


class ScoringError(ValueError):
    """Controlled model, data or schema failure, never a substitute score."""


def predict_scores(model, features):
    if hasattr(model, 'predict_proba'):
        return np.asarray(model.predict_proba(features))[:, 1]
    return np.asarray(model.predict(features, num_threads=1))


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
    x_train, x_val, x_test, y_train, y_val, y_test = split_data(features, target)
    comparisons, models = [], []
    for leaves in CANDIDATES:
        params = {**PARAMS, 'num_leaves': leaves}
        model = LGBMClassifier(objective='binary', **params).fit(x_train, y_train)
        scores = predict_scores(model, x_val)
        comparisons.append(dict(num_leaves=leaves, Val_AP=float(average_precision_score(y_val, scores))))
        models.append(model)
    best = max(range(len(models)), key=lambda i: comparisons[i]['Val_AP'])
    model = models[best]
    threshold = choose_threshold(y_val, predict_scores(model, x_val))
    # Test predictions are used only after model and threshold are fixed.
    metrics = {name: calculate_metrics(y, predict_scores(model, x), threshold)
               for name,x,y in [('Train',x_train,y_train),('Validation',x_val,y_val),('Test',x_test,y_test)]}
    return dict(format_version=FORMAT_VERSION, model_type='legal', model=model,
                feature_names=list(features.columns), threshold=threshold, objective={'name':'binary'},
                positive_class=1, target='bankrupt', metrics=metrics,
                params=model.get_params(), validation_comparison=comparisons,
                experiment='70/15/15; seed=42; validation AP and F2; isolated test')


def validate_artifact(artifact):
    try:
        if artifact['format_version'] != FORMAT_VERSION or artifact['model_type'] != 'legal':
            raise ValueError('Incompatible format or borrower type')
        names=artifact['feature_names']
        model=artifact['model']
        actual_names=list(model.feature_name_) if hasattr(model,'feature_name_') else model.feature_name()
        if not names or len(set(names)) != len(names) or names != actual_names:
            raise ValueError('Model and artifact feature schemas differ')
        if artifact['objective'] != {'name':'binary'} or artifact['positive_class'] != 1:
            raise ValueError('Binary objective and positive class must be explicit')
        if not 0 <= float(artifact['threshold']) <= 1:
            raise ValueError('Invalid threshold')
        native=model.booster_ if hasattr(model,'booster_') else model
        if 'objective=binary' not in native.model_to_string().split('feature_names=')[0]:
            raise ValueError('Model is not a binary-log-loss classifier')
    except (KeyError,AttributeError,TypeError,ValueError) as exc:
        raise ScoringError(f'Incompatible legal artifact: {exc}') from exc
    return artifact


def load_artifact(artifact_path):
    # The historical filename is retained, but new artifacts are JSON + native
    # model text. Old pickle files are rejected without executing deserialization.
    try:
        import lightgbm as lgb
        content=Path(artifact_path).read_bytes()
        artifact=json.loads(content)
        native=artifact.pop('native_model')
        if hashlib.sha256(native.encode()).hexdigest()!=artifact.pop('native_sha256'):
            raise ValueError('Native checksum mismatch')
        artifact['model']=lgb.Booster(model_str=native)
        artifact['_artifact_id']=hashlib.sha256(content).hexdigest()
        return validate_artifact(artifact)
    except ScoringError:
        raise
    except Exception as exc:
        raise ScoringError(f'Cannot load legal artifact: {type(exc).__name__}') from exc


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
    path=Path(path)
    if path.name not in {'model_legal.joblib','model_legal.json'}:
        raise ScoringError('Legal weights must use filename model_legal.joblib or model_legal.json')
    if path.exists() and not allow_replace:
        raise ScoringError('Existing artifact preserved; explicit allow_replace is required')
    validate_artifact(artifact)
    model=artifact['model']
    native=(model.booster_ if hasattr(model,'booster_') else model).model_to_string()
    data={k:v for k,v in artifact.items() if k!='model' and not k.startswith('_')}
    data.update(native_model=native,native_sha256=hashlib.sha256(native.encode()).hexdigest())
    path.parent.mkdir(parents=True,exist_ok=True)
    handle,temporary=tempfile.mkstemp(prefix='.legal-',dir=path.parent)
    os.close(handle)
    try:
        Path(temporary).write_text(json.dumps(data),encoding='utf-8')
        loaded=load_artifact(temporary)
        if not np.allclose(predict_scores(loaded['model'],sample),predict_scores(model,sample),atol=1e-9):
            raise ScoringError('Native round-trip predictions changed')
        if allow_replace:os.replace(temporary,path)
        else:os.link(temporary,path)
    except FileExistsError as exc:
        raise ScoringError('Existing artifact preserved') from exc
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
    print(json.dumps({k: artifact[k] for k in ("threshold", "metrics")}, indent=2))


if __name__ == "__main__":
    # Keep training, objective type checks and pickle imports in one module identity.
    from ml.train_legal import main as canonical_main
    canonical_main()
