from __future__ import annotations

import re
from io import StringIO
from typing import Any

import pandas as pd

from data_quality_api.email_tools import looks_like_email_column, normalize_email
from data_quality_api.models import ColumnProfile, DatasetProfile
from data_quality_api.phone_tools import looks_like_phone_column
from data_quality_api.settings import MAX_RECORDS


def read_csv_text(csv_text: str, delimiter: str = ",") -> pd.DataFrame:
    frame = pd.read_csv(StringIO(csv_text), delimiter=delimiter, dtype=str, keep_default_na=False)
    if len(frame) > MAX_RECORDS:
        raise ValueError(f"Maximum {MAX_RECORDS} rows per request.")
    return frame


def profile_frame(frame: pd.DataFrame) -> DatasetProfile:
    duplicate_rows = int(frame.duplicated().sum())
    column_profiles = [_profile_column(frame[column], str(column)) for column in frame.columns]
    warnings = _build_warnings(frame, column_profiles, duplicate_rows)
    return DatasetProfile(
        rows=len(frame),
        columns=len(frame.columns),
        duplicate_rows=duplicate_rows,
        quality_score=_quality_score(frame, duplicate_rows, column_profiles),
        column_profiles=column_profiles,
        warnings=warnings,
    )


def records_to_frame(records: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(records).fillna("")


def _profile_column(series: pd.Series, name: str) -> ColumnProfile:
    normalized = series.map(_normalize_missing)
    missing_count = int((normalized == "").sum())
    non_empty = normalized[normalized != ""]
    return ColumnProfile(
        name=name,
        inferred_type=_infer_type(non_empty, name),
        missing_count=missing_count,
        missing_rate=round(missing_count / max(len(series), 1), 4),
        unique_count=int(non_empty.nunique(dropna=True)),
        example_values=_examples(non_empty),
    )


def _infer_type(series: pd.Series, name: str) -> str:
    if series.empty:
        return "empty"
    if looks_like_email_column(name):
        if len(series) <= 3:
            return "email"
        valid_rate = sum(normalize_email(str(value)).valid_format for value in series) / len(series)
        if valid_rate >= 0.7:
            return "email"
    if looks_like_phone_column(name):
        return "phone"
    lowered = series.astype(str).str.lower()
    if lowered.isin(["true", "false", "yes", "no", "0", "1"]).mean() >= 0.9:
        return "boolean"
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().mean() >= 0.9:
        return "integer" if (numeric.dropna() % 1 == 0).all() else "number"
    if _looks_date_like(series):
        dates = pd.to_datetime(series, errors="coerce")
        if dates.notna().mean() >= 0.9:
            return "date"
    return "text"


def _quality_score(
    frame: pd.DataFrame,
    duplicate_rows: int,
    column_profiles: list[ColumnProfile],
) -> float:
    if frame.empty or not column_profiles:
        return 0.0
    missing_sum = sum(profile.missing_rate for profile in column_profiles)
    missing_penalty = missing_sum / len(column_profiles)
    duplicate_penalty = duplicate_rows / max(len(frame), 1)
    score = 100 - (missing_penalty * 55) - (duplicate_penalty * 35)
    return round(max(min(score, 100), 0), 2)


def _build_warnings(
    frame: pd.DataFrame,
    column_profiles: list[ColumnProfile],
    duplicate_rows: int,
) -> list[str]:
    warnings: list[str] = []
    if duplicate_rows:
        warnings.append(f"{duplicate_rows} duplicate rows detected.")
    for profile in column_profiles:
        if profile.missing_rate >= 0.5:
            warnings.append(f"{profile.name} has {profile.missing_rate:.0%} missing values.")
    if len(frame.columns) != len(set(frame.columns)):
        warnings.append("Duplicate column names detected.")
    return warnings


def _examples(series: pd.Series) -> list[Any]:
    values = series.drop_duplicates().head(3).tolist()
    return [None if value == "" else value for value in values]


def _normalize_missing(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"", "nan", "none", "null", "na", "n/a"} else text


def _looks_date_like(series: pd.Series) -> bool:
    sample = " ".join(series.astype(str).head(10).tolist())
    return bool(re.search(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}", sample))
