import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import pytest
from scipy.special import expit
from ml.eda_legal import prepare_legal, RENAME_2022, EXCLUDED_RATIOS
from ml.eda_entrepreneur import prepare_ie
from ml.train_entrepreneur import train_ie, predict_ie
from ml import train_legal as legal
from ml_fixtures import (
    scoring_env, signup, csrf, application, MockSources, ModelInputs, mock_predictor,
    get_scoring_inputs, get_scoring_predictors, run_db,
)


def csv_fixture(tmp_path, **changes):
    # Small validation fixture, not a supplied dataset or claimed training data.
    frame = pd.DataFrame({"id": ["a", "b", "c", "d"], "inn": ["TEST-A", "TEST-B", "TEST-C", "TEST-D"],
                          "bankrupt": [0, 1, 0, 1], "cash_ratio_2022": [1, 2, np.inf, 4],
                          "industry": [10, 20, 10, 20], "region": [1, 2, 1, 2]})
    for key, value in changes.items():
        frame[key] = value
    path = tmp_path / "fixture.csv"
    frame.to_csv(path, index=False)
    return path


def test_prepared_eda_no_leakage_or_revenue_filter(tmp_path):
    path = csv_fixture(tmp_path, revenue=[-1, 9000000, np.nan, 100], owner_id=[1, 2, 3, 4],
                       long_term_liabilities=[5] * 4, labor_remuneration_ratio_2022=[9] * 4)
    x, y = prepare_legal(path)
    assert len(x) == len(y) == 4
    assert list(x) == ["cash_ratio_2022", "revenue"]
    assert x.index.equals(y.index) and y.tolist() == [0, 1, 0, 1]
    assert np.isnan(x.iloc[2, 0]) and np.isnan(x.iloc[2, 1])
    assert x.iloc[1, 1] == 9000000


def test_raw_eda_exact_notebook_mapping(tmp_path):
    path = csv_fixture(tmp_path, **{name: [1, 2, 3, 4] for name in RENAME_2022},
                       V1=[8] * 4, V43=[9] * 4, revenue=[100] * 4)
    x, _ = prepare_legal(path)
    assert list(x) == [name for name in RENAME_2022.values() if name not in EXCLUDED_RATIOS]
    assert len(x.columns) == 16


@pytest.mark.parametrize("changes,match", [
    ({"id": ["a", "a", "c", "d"]}, "duplicate id"),
    ({"inn": ["A", "A.0", "B", "C"]}, "Duplicate inn"),
    ({"bankrupt": [0, 2, 0, 1]}, "only 0 and 1"),
    ({"bankrupt": [0, np.nan, 0, 1]}, "only 0 and 1"),
    ({"cash_ratio_2022": [np.nan] * 4}, "No usable"),
    ({"V22": [1, 2, 3, 4]}, "Incomplete 2022"),
])
def test_eda_validation(tmp_path, changes, match):
    with pytest.raises(ValueError, match=match):
        prepare_legal(csv_fixture(tmp_path, **changes))


def test_split_is_stratified_deterministic_and_disjoint():
    x = pd.DataFrame({"x": np.arange(200)})
    y = pd.Series([0, 0, 0, 1] * 50)
    first, second = legal.split_data(x, y), legal.split_data(x, y)
    assert [len(v) for v in first[:3]] == [139, 31, 30]  # sklearn rounds the second floating split upward
    for left, right in zip(first, second):
        assert left.equals(right)
    sets = [set(v.index) for v in first[:3]]
    assert not sets[0] & sets[1] and not sets[0] & sets[2] and not sets[1] & sets[2]
    assert set.union(*sets) == set(x.index)


@pytest.mark.parametrize("gamma", [0, 0.5, 3, 7])
def test_focal_matches_finite_difference(gamma):
    y = np.array([0, 1, 0, 1])
    raw = np.array([-1.0, -0.3, 0.8, 1.2])
    objective = legal.FocalObjective(gamma, 2.0)
    def loss(z):
        p = expit(z)
        pt = np.where(y == 1, p, 1 - p)
        return -np.where(y == 1, 2.0, 1.0) * (1 - pt)**gamma * np.log(pt)
    step = 1e-4
    grad, hess = objective(y, raw)
    np.testing.assert_allclose(grad, (loss(raw + step) - loss(raw - step)) / (2 * step), rtol=1e-6)
    numerical_hess = (loss(raw + step) - 2 * loss(raw) + loss(raw - step)) / step**2
    np.testing.assert_allclose(hess, np.maximum(numerical_hess, 1e-4), rtol=1e-5)
    assert np.all(objective(y, np.array([-1000, 1000, -1000, 1000]))[1] >= 1e-4)


def test_predict_scores_applies_sigmoid_once():
    class RawModel:
        def predict(self, x, *, raw_score):
            assert raw_score is True
            return np.array([-2, 0, 2])
        def predict_proba(self, x):
            pytest.fail("custom objective must not use predict_proba")
    np.testing.assert_allclose(legal.predict_scores(RawModel(), None), expit([-2, 0, 2]))


def test_experiment_selection_uses_only_validation(monkeypatch):
    import lightgbm
    x = pd.DataFrame({"x": np.arange(200, dtype=float)})
    y = pd.Series([0, 0, 0, 1] * 50)
    x_train, x_val, x_test, y_train, y_val, y_test = legal.split_data(x, y)
    predictions, fitted = [], []
    class SpyClassifier:
        def __init__(self, objective, **params):
            self.objective = objective
            assert params == legal.PARAMS
        def fit(self, features, target):
            assert features.equals(x_train) and target.equals(y_train)
            fitted.append(self)
        def predict(self, features, raw_score):
            predictions.append(set(features.index))
            # Explicit fixture predictions are only for selection-isolation tests.
            return np.sin(features.x.to_numpy() + self.objective.gamma)
    monkeypatch.setattr(lightgbm, "LGBMClassifier", SpyClassifier)
    original_threshold = legal.choose_threshold
    def threshold(target, scores):
        assert target.equals(y_val)
        assert all(index == set(x_val.index) for index in predictions)
        return original_threshold(target, scores)
    monkeypatch.setattr(legal, "choose_threshold", threshold)
    artifact = legal.fit_experiment(x, y)
    assert len(fitted) == 15
    assert [m.objective.gamma for m in fitted] == list(legal.GAMMAS)
    assert artifact["pos_weight"] == np.sqrt((y_train == 0).sum() / (y_train == 1).sum())
    assert {k: v["N"] for k, v in artifact["metrics"].items()} == {"Train": 139, "Validation": 31, "Test": 30}
    assert predictions[-1] == set(x_test.index)
    assert artifact["gamma"] == artifact["validation_comparison"][0]["gamma"]


@pytest.fixture
def artifact_fixture():
    from lightgbm import LGBMClassifier
    # In-memory unit fixture; these weights never enter repository artifacts/.
    x = pd.DataFrame({"cash_ratio_2022": np.arange(80, dtype=float),
                      "revenue": np.arange(80, dtype=float)**2})
    y = pd.Series(([0] * 3 + [1]) * 20)
    model = LGBMClassifier(objective=legal.FocalObjective(1.0, 2.0), n_estimators=3,
                           min_child_samples=2, n_jobs=1, verbosity=-1).fit(x, y)
    a = dict(format_version=1, model_type="legal", model=model, feature_names=list(x),
             gamma=1.0, threshold=0.5, objective={"name": "focal", "gamma": 1.0,
                    "pos_weight": 2.0, "hessian_floor": 1e-4, "raw_score_sigmoid": True})
    return a, x.head(4)


def test_joblib_new_process_roundtrip_order_and_preservation(tmp_path, artifact_fixture):
    artifact, x = artifact_fixture
    path = tmp_path / "model_legal.joblib"
    legal.save_artifact(artifact, path, x)
    result = legal.predict_legal(path, x[list(reversed(x.columns))])
    np.testing.assert_allclose(result["scores"], legal.predict_scores(artifact["model"], x))
    before = path.read_bytes()
    with pytest.raises(legal.ScoringError, match="preserved"):
        legal.save_artifact(artifact, path, x)
    assert path.read_bytes() == before
    with pytest.raises(legal.ScoringError, match="schema mismatch"):
        legal.predict_legal(path, {"unknown": 1})


@pytest.mark.parametrize("problem", ["missing", "corrupt", "version", "ie", "schema"])
def test_incompatible_weights_are_controlled(tmp_path, artifact_fixture, problem):
    artifact, x = artifact_fixture
    path = tmp_path / "model_legal.joblib"
    if problem == "corrupt":
        path.write_bytes(b"invalid joblib")
    elif problem != "missing":
        if problem == "version": artifact["format_version"] = 999
        if problem == "ie": artifact["model_type"] = "ie"
        if problem == "schema": artifact["feature_names"] = ["wrong"]
        joblib.dump(artifact, path)
    with pytest.raises(legal.ScoringError):
        legal.predict_legal(path, x)


def test_fallback_is_opt_in_and_safe_for_parallel_calls(tmp_path, artifact_fixture, monkeypatch):
    artifact, x = artifact_fixture
    csv_path = csv_fixture(tmp_path, revenue=[1, 2, 3, 4])
    path = tmp_path / "model_legal.joblib"
    count = []
    def train(csv, destination, allow_replace):
        count.append(csv)
        legal.save_artifact(artifact, destination, x, allow_replace=allow_replace)
    monkeypatch.setattr(legal, "_train", train)
    with pytest.raises(legal.ScoringError):
        legal.predict_legal(path, x, training_csv=csv_path)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: legal.predict_legal(
            path, x, training_csv=csv_path, allow_retrain=True), range(3)))
    assert len(count) == 1 and results[0] == results[1] == results[2]


def test_corrupt_fallback_preserves_weights_without_explicit_replace(tmp_path, artifact_fixture, monkeypatch):
    artifact, x = artifact_fixture
    csv_path = csv_fixture(tmp_path, revenue=[1, 2, 3, 4])
    path = tmp_path / "model_legal.joblib"
    path.write_bytes(b"preserve me")
    with pytest.raises(legal.ScoringError, match="allow_replace"):
        legal.predict_legal(path, x, training_csv=csv_path, allow_retrain=True)
    assert path.read_bytes() == b"preserve me"
    monkeypatch.setattr(legal, "fit_experiment", lambda *_: artifact)
    result = legal.predict_legal(path, x, training_csv=csv_path, allow_retrain=True, allow_replace=True)
    assert len(result["scores"]) == len(x)


def test_ie_requires_separate_specification(tmp_path):
    path = csv_fixture(tmp_path, ie_declared_income=[1, 2, 3, 4])
    with pytest.raises(ValueError, match="specification"):
        prepare_ie(path)
    x, _ = prepare_ie(path, feature_names=["ie_declared_income"])
    assert list(x) == ["ie_declared_income"]
    with pytest.raises(legal.ScoringError, match="not specified"):
        train_ie(path, feature_names=["ie_declared_income"])
    with pytest.raises(legal.ScoringError, match="IE inference"):
        predict_ie(features={"cash_ratio_2022": 1})


@pytest.mark.parametrize("kind,expected", [("llc", "legal"), ("ip", "ie")])
def test_api_model_routing_persistence_and_ownership(scoring_env, kind, expected):
    env = scoring_env
    env.app.dependency_overrides[get_scoring_inputs] = ModelInputs
    env.app.dependency_overrides[get_scoring_predictors] = lambda: {
        "legal": (mock_predictor("legal"), Path("mock-legal")),
        "ie": (mock_predictor("ie"), Path("mock-ie")),
    }
    with env.client() as first, env.client() as other, env.client() as guest:
        signup(first, kind=kind)
        signup(other, kind="ip" if kind == "llc" else "llc", email="other@example.com")
        app_id = application(first)
        url = "/api/scoring/" + app_id
        assert guest.get(url).status_code == 401
        assert first.post(url).status_code == 403
        assert other.post(url, headers=csrf(other), json={"owner_id": "user-1"}).status_code == 404
        response = first.post(url, headers=csrf(first))
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["model_type"] == expected and body["provenance"]["inference"] == "mock"
        assert body["target"] == "bankrupt" and body["artifact_id"] == "mock"
        assert first.get(url).json() == body == first.get(url).json()
        assert other.get(url).status_code == 404
        assert first.get("/api/applications/" + app_id).json()["status"] == "draft"


def test_api_missing_features_and_ie_experiment(scoring_env):
    with scoring_env.client() as client:
        signup(client)
        app_id = application(client)
        assert client.get("/api/scoring/" + app_id).status_code == 404
        response = client.post("/api/scoring/" + app_id, headers=csrf(client))
        assert response.status_code == 422 and "2022 financial features" in response.text
    with scoring_env.client() as client:
        signup(client, kind="ip", email="ie@example.com")
        response = client.post("/api/scoring/" + application(client), headers=csrf(client))
        assert response.status_code == 422 and '"model_type":"ie"' in response.text


@pytest.mark.parametrize("registry,bureau", [("available", "clean"), ("available", "overdue"),
        ("available", "unavailable"), ("available", "error"), ("unavailable", "clean")])
def test_mock_sources_are_explicit_and_missing_data_never_invents_ratios(scoring_env, registry, bureau):
    sources = MockSources(registry, bureau)
    assert sources.registry("UNKNOWN")["source"] == "mock"
    assert sources.bureau()["source"] == "mock"
    assert sources.registry("990000000115").get("business_type", "ie") == "ie"
    scoring_env.app.dependency_overrides[get_scoring_inputs] = lambda: sources
    with scoring_env.client() as client:
        signup(client)
        response = client.post("/api/scoring/" + application(client), headers=csrf(client))
        assert response.status_code == 422 and response.json()["detail"]["code"] == "ml_unavailable"


def test_threshold_maximizes_f2_over_validation_candidates():
    from sklearn.metrics import fbeta_score
    y = np.array([0, 1, 1, 0, 1, 0])
    scores = np.array([0.1, 0.2, 0.8, 0.6, 0.7, 0.4])
    threshold = legal.choose_threshold(y, scores)
    actual = fbeta_score(y, scores >= threshold, beta=2)
    assert actual == max(fbeta_score(y, scores >= t, beta=2) for t in scores)


def test_inference_rejects_unknown_or_unusable_values(artifact_fixture):
    a, _ = artifact_fixture
    for values in ({"cash_ratio_2022": "bad", "revenue": 1},
                   {"cash_ratio_2022": np.inf, "revenue": np.nan}):
        with pytest.raises(legal.ScoringError):
            legal.validate_features(values, a["feature_names"])
    values = legal.validate_features({"cash_ratio_2022": -np.inf, "revenue": 1}, a["feature_names"])
    assert np.isnan(values.iloc[0, 0])


def test_fallback_csv_errors_are_controlled(tmp_path):
    with pytest.raises(legal.ScoringError, match="fallback CSV"):
        legal.predict_legal(tmp_path / "model_legal.joblib", {"x": 1},
                            training_csv=tmp_path / "missing.csv", allow_retrain=True)


def test_cli_dispatch_uses_canonical_module_for_pickle(monkeypatch):
    import runpy
    called = []
    monkeypatch.setattr(legal, "main", lambda: called.append(True))
    with pytest.warns(RuntimeWarning, match="found in sys.modules"):
        runpy.run_module("ml.train_legal", run_name="__main__")
    assert called == [True]
