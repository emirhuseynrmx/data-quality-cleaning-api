from __future__ import annotations

import re
from io import StringIO
from typing import Any

import pandas as pd

from data_quality_api.email_tools import looks_like_email_column, normalize_email
from data_quality_api.models import ColumnProfile, DatasetProfile, DuplicateKeySummary
from data_quality_api.phone_tools import looks_like_phone_column, normalize_phone
from data_quality_api.settings import MAX_RECORDS


def read_csv_text(csv_text: str, delimiter: str = ",") -> pd.DataFrame:
    frame = pd.read_csv(StringIO(csv_text), delimiter=delimiter, dtype=str, keep_default_na=False)
    if len(frame) > MAX_RECORDS:
        raise ValueError(f"Maximum {MAX_RECORDS} rows per request.")
    return frame


def profile_frame(
    frame: pd.DataFrame,
    duplicate_key_summary: list[DuplicateKeySummary] | None = None,
) -> DatasetProfile:
    duplicate_rows = int(frame.duplicated().sum())
    column_profiles = [_profile_column(frame[column], str(column)) for column in frame.columns]
    warnings = _build_warnings(frame, column_profiles, duplicate_rows)
    invalid_email_count = _invalid_count_for_type(column_profiles, "email")
    invalid_phone_count = _invalid_count_for_type(column_profiles, "phone")
    return DatasetProfile(
        rows=len(frame),
        columns=len(frame.columns),
        duplicate_rows=duplicate_rows,
        invalid_email_count=invalid_email_count,
        invalid_phone_count=invalid_phone_count,
        duplicate_key_summary=duplicate_key_summary or [],
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
    inferred_type, confidence, invalid_count = _infer_column(non_empty, name)
    return ColumnProfile(
        name=name,
        inferred_type=inferred_type,
        missing_count=missing_count,
        missing_rate=round(missing_count / max(len(series), 1), 4),
        unique_count=int(non_empty.nunique(dropna=True)),
        confidence=confidence,
        invalid_count=invalid_count,
        example_values=_examples(non_empty),
    )


def summarize_duplicate_keys(frame: pd.DataFrame, keys: list[str]) -> list[DuplicateKeySummary]:
    if not keys:
        return []
    duplicated = frame.duplicated(subset=keys, keep=False)
    duplicate_records = int(duplicated.sum())
    if duplicate_records == 0:
        duplicate_groups = 0
    else:
        duplicate_groups = int(frame.loc[duplicated, keys].drop_duplicates().shape[0])
    return [
        DuplicateKeySummary(
            keys=keys,
            duplicate_records=duplicate_records,
            duplicate_groups=duplicate_groups,
        )
    ]


def _infer_column(series: pd.Series, name: str) -> tuple[str, float, int]:
    if series.empty:
        return "empty", 1.0, 0
    email_rate, invalid_email_count = _email_validity(series)
    if looks_like_email_column(name):
        return "email", email_rate, invalid_email_count
    if email_rate >= 0.7:
        return "email", email_rate, invalid_email_count
    phone_rate, invalid_phone_count = _phone_validity(series)
    if looks_like_phone_column(name):
        return "phone", phone_rate, invalid_phone_count
    if phone_rate >= 0.8:
        return "phone", phone_rate, invalid_phone_count
    lowered = series.astype(str).str.lower()
    boolean_rate = float(lowered.isin(["true", "false", "yes", "no", "0", "1"]).mean())
    if boolean_rate >= 0.9:
        return "boolean", round(boolean_rate, 4), 0
    numeric = pd.to_numeric(series, errors="coerce")
    numeric_rate = float(numeric.notna().mean())
    if numeric_rate >= 0.9:
        inferred_type = "integer" if (numeric.dropna() % 1 == 0).all() else "number"
        return inferred_type, round(numeric_rate, 4), 0
    if _looks_date_like(series):
        dates = pd.to_datetime(series, errors="coerce")
        date_rate = float(dates.notna().mean())
        if date_rate >= 0.9:
            return "date", round(date_rate, 4), 0
    return "text", 1.0, 0


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
    invalid_sum = sum(profile.invalid_count for profile in column_profiles)
    invalid_penalty = invalid_sum / max(len(frame) * len(column_profiles), 1)
    score = 100 - (missing_penalty * 50) - (duplicate_penalty * 30) - (invalid_penalty * 35)
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
        if profile.inferred_type in {"email", "phone"} and profile.invalid_count:
            field_type = profile.inferred_type
            warnings.append(
                f"{profile.name} has {profile.invalid_count} invalid {field_type} values."
            )
    if len(frame.columns) != len(set(frame.columns)):
        warnings.append("Duplicate column names detected.")
    return warnings


def _invalid_count_for_type(column_profiles: list[ColumnProfile], inferred_type: str) -> int:
    return sum(
        profile.invalid_count
        for profile in column_profiles
        if profile.inferred_type == inferred_type
    )


def _email_validity(series: pd.Series) -> tuple[float, int]:
    results = [normalize_email(str(value)).valid_format for value in series]
    valid_count = sum(results)
    invalid_count = len(results) - valid_count
    return round(valid_count / max(len(results), 1), 4), invalid_count


def _phone_validity(series: pd.Series) -> tuple[float, int]:
    results = [normalize_phone(str(value), "US").valid for value in series]
    valid_count = sum(results)
    invalid_count = len(results) - valid_count
    return round(valid_count / max(len(results), 1), 4), invalid_count


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
