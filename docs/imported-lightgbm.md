# Imported LightGBM artifact

User-supplied file: `LightGBM.joblib`. It was inspected without executing joblib
deserialization. Embedded native LightGBM text was extracted and smoke-tested
with `lightgbm.Booster` (450 trees, 24 features). No original joblib is loaded
by the imported-model adapter.

- Original SHA256: `1b9a0de1523b3c6bb64b269c960fafae169b570d9b056f3ea9198e63e3175f82`
- Converted native model SHA256: `8f5b6d91d91873e2bf8df6c2a0e0a796f076faedddf8dc88e82d28ff5393d386`
- Original metadata: sklearn 1.8.0; 3-fold CV; best CV PR-AUC 0.3468188047579757
- Model: standard binary LightGBMClassifier, not the existing focal-loss artifact
- Feature schema: see `ml/imported_lightgbm.py` (`FEATURE_NAMES`).

To test offline, place the **converted native text model** at
`artifacts/LightGBM_native.txt` and call `score_positive_class` with all 24
correctly calculated financial features. The imported model is not a drop-in
replacement for `artifacts/model_legal.joblib`.

The uploaded artifact does **not** specify the meaning of the positive target,
a decision threshold, or holdout metrics. It uses nonunit class weighting, so
the emitted positive-class scores are not assumed calibrated. Never label them
as credit PD, bankruptcy probability, or approval probability without additional
verified provenance and validation.

The existing server pipeline and `/api/scoring/{application_id}` are unchanged.
They must not invent missing 2022 financial features from loan form amounts.
To integrate online: verify the training label; obtain actual feature values
with documented definitions and provenance; validate threshold/calibration;
then adapt the scoring API and add end-to-end tests. Keep the demo credit policy
independent of this model.
