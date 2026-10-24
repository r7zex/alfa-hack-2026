"""Offline preparation of X_2022/y_2022 (not the revenue-filtered subset)."""
from pathlib import Path
import numpy as np
import pandas as pd

FINANCIAL_NAMES = (
    "asset_turnover", "asset_turnover_days", "receivables_collection_days",
    "inventory_turnover_days", "cash_ratio", "quick_ratio", "current_ratio",
    "return_on_assets_pct", "return_on_equity_pct", "operating_profit_margin_pct",
    "net_profit_to_long_term_capital_pct", "labor_remuneration_ratio",
    "wages_to_assets_ratio", "gross_profit_per_employee", "liabilities_to_assets_pct",
    "liabilities_to_equity_pct", "financial_leverage", "assets_to_liabilities",
    "net_profit_to_interest_paid", "assets_to_noncurrent_assets",
    "borrowings_to_liabilities_pct",
)
RENAME_2022 = {f"V{i}": f"{name}_2022" for i, name in enumerate(FINANCIAL_NAMES, 22)}
EXCLUDED_RATIOS = {
    f"{name}_2022" for name in (
        "labor_remuneration_ratio", "wages_to_assets_ratio", "gross_profit_per_employee",
        "net_profit_to_interest_paid", "assets_to_noncurrent_assets",
    )
}
EXTRA_NAMES = (
    "business_age", "region", "okopf", "simplified", "revenue", "net_profit",
    "total_assets", "equity", "cash", "long_term_liabilities", "short_term_liabilities",
)
FORBIDDEN = {
    "id", "inn", "bankrupt", "industry", "region", "okopf", "long_term_liabilities",
    "evaluation_year", "year_r1", "year_r2", "year_r3",
    "business_id", "user_id", "application_id", "owner_id", "ogrn", "ogrnip", "kpp",
    "filed", "imputed", "outlier", "source", "data_origin", "status", "year",
}


def read_labeled_csv(csv_path: str | Path) -> tuple[pd.DataFrame, pd.Series]:
    """Read identifiers as strings; refuse ambiguous companies before splitting."""
    try:
        frame = pd.read_csv(csv_path, dtype={"inn": "string", "id": "string"}, low_memory=False)
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        raise ValueError(f"Cannot read training CSV: {exc}") from exc
    if frame.empty or "bankrupt" not in frame:
        raise ValueError("A nonempty CSV with target bankrupt is required")
    if "id" in frame:
        if frame.id.isna().any() or frame.id.duplicated().any():
            raise ValueError("Missing or duplicate id")
        frame = frame.set_index("id")
    if "inn" in frame:
        frame["inn"] = (frame.inn.str.strip().str.replace(r"\.0$", "", regex=True)
                        .replace("", pd.NA))
        if frame.inn.dropna().duplicated().any():
            raise ValueError("Duplicate inn: the final experiment requires unique companies")
    target = pd.to_numeric(frame["bankrupt"], errors="coerce")
    if target.isna().any() or not target.isin([0, 1]).all():
        raise ValueError("bankrupt must contain only 0 and 1")
    return frame, target.astype(int)


def prepare_legal(csv_path: str | Path) -> tuple[pd.DataFrame, pd.Series]:
    frame, target = read_labeled_csv(csv_path)
    raw = [name for name in RENAME_2022 if name in frame]
    if raw:
        if len(raw) != 21:
            raise ValueError("Incomplete 2022 schema: all V22-V42 are required")
        # Notebook cell 9 deliberately selects only the 2022 block in raw input.
        frame = frame[raw].rename(columns=RENAME_2022)
    elif any(str(c).startswith("V") and str(c)[1:].isdigit() for c in frame):
        raise ValueError("Raw input has no complete V22-V42 block")
    frame = frame.drop(columns=list(FORBIDDEN | EXCLUDED_RATIOS), errors="ignore")
    # Cell 11 coerces enrichment fields; also accept CSV numeric strings in ratios.
    for name in set(RENAME_2022.values()) | set(EXTRA_NAMES):
        if name in frame and name not in {"region", "okopf"}:
            frame[name] = pd.to_numeric(frame[name], errors="coerce")
    # Other numeric prepared columns follow cell 12; service identifiers never do.
    frame = frame.drop(columns=[c for c in frame if str(c).endswith("_id")
                               or str(c).startswith("Unnamed:")], errors="ignore")
    features = frame.select_dtypes(include="number").replace([np.inf, -np.inf], np.nan)
    features = features.loc[:, features.notna().any(axis=0)]
    if features.empty:
        raise ValueError("No usable numeric features after 2022 preparation")
    return features, target.loc[features.index]
