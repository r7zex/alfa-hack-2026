"""Real supplied native weights; no user pickle deserialization."""
from hashlib import sha256
import json
import numpy as np
import pytest
from ml.imported_lightgbm import ARTIFACT_SHA256,DEFAULT_ARTIFACT,FEATURE_NAMES,ImportedModelError,score_positive_class,load_native_model,validate_features
from app.services.financial_features import STABLE


def test_real_weights_schema_reproducibility_and_contributions():
    assert sha256(DEFAULT_ARTIFACT.read_bytes()).hexdigest()==ARTIFACT_SHA256
    model=load_native_model();assert model.num_trees()==450 and model.feature_name()==list(FEATURE_NAMES)
    a=score_positive_class(STABLE);b=score_positive_class(dict(reversed(list(STABLE.items()))))
    assert a==b and a['threshold'] is None and a['target']=='unspecified_in_supplied_artifact'
    contributions=a['contributions'][0]
    assert abs(sum(contributions['values'].values())+contributions['base_value']-contributions['raw_score'])<1e-7
    assert 0<a['scores'][0]<1


@pytest.mark.parametrize('change',[{'other':1},{'business_age':-1},{'simplified':2},{'cash':float('inf')},{'cash':'123'}])
def test_invalid_feature_contract(change):
    with pytest.raises(ImportedModelError):validate_features({**STABLE,**change})


def test_nan_missing_and_corrupt_model(tmp_path):
    data={**STABLE,'cash':None}
    assert len(score_positive_class(data)['scores'])==1
    with pytest.raises(ImportedModelError):score_positive_class(STABLE,tmp_path/'absent.txt')
    damaged=tmp_path/'bad.txt';damaged.write_bytes(DEFAULT_ARTIFACT.read_bytes()+b'corrupt')
    with pytest.raises(ImportedModelError,match='SHA256'):score_positive_class(STABLE,damaged)
    with pytest.raises(ImportedModelError):validate_features({k:None for k in FEATURE_NAMES})
