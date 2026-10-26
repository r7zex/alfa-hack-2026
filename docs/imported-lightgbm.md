# Импорт предоставленных весов

Native-веса уже включены: `artifacts/LightGBM_native.txt`. Подробные hash, схема, ограничения и проверенные результаты — в [model card](model-card.md). Извлечение воспроизводится только для известного исходного SHA:

```bash
python -m scripts.extract_native_lightgbm --help
python -m pytest -q tests/test_imported_model.py
```

Конвертер читает сжатый joblib как данные, не вызывает `pickle.load`/`joblib.load`. Online worker использует `lightgbm.Booster(model_str=verified_text)` и проверяет hash до загрузки. Размер/порядок/имена признаков проверяются до инференса. Количество деревьев: 450; objective: binary.

`GET /api/applications/{id}/ml` и workflow возвращают сохранённый технический score класса 1 с provenance. Доступ определяется организацией и ролью. Веса не заменяют отдельный legacy `/api/scoring/{id}` контракт банкротства: у импортированной модели неизвестны target mapping и порог.

Синтетические профили независимы от трёх финансовых полей формы. Управление профилем: `PUT /api/admin/businesses/{id}/financial-profile`, admin-only, kind `synthetic_stable`, `synthetic_stressed`, `missing` или `verified` с 24 признаками/источником/периодом. Для исходного обучения не подтверждены единицы, поэтому бизнес-интерпретация score запрещена независимо от выбранного профиля.
