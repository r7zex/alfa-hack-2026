# ML

Основной эксперимент — стандартный LightGBM binary log loss в `train_legal.py`, с изолированным test split и подбором только на validation. Установка: `pip install -r requirements-ml.txt`.

```bash
python -m ml.train_legal --help
python -m ml.eda_legal --help
```

Обучение требует исходного CSV и не запускается при обычном старте. Сохраняются схема, версии, source hash, параметры, порог и AP/ROC-AUC/Precision/Recall/F1/F2. Собственный артефакт имеет безопасный JSON/native формат; историческое расширение `.joblib` не означает pickle.

Предоставленные пользователем веса — отдельный native binary LightGBM на 24 признаках. Они включены и используются фоновым worker; `imported_lightgbm.py` проверяет hash, значения и contributions. Target mapping, исходные единицы и threshold неизвестны. Не смешивайте этот score класса 1 с контрактом bankruptcy из собственного обучения. [Model card](../docs/model-card.md).
