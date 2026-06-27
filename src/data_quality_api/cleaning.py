from __future__ import annotations

from io import StringIO
from typing import Any

import pandas as pd

from data_quality_api.email_tools import looks_like_email_column, normalize_email
from data_quality_api.models import (
    CsvCleanRequest,
    CsvCleanResponse,
    RecordCleanRequest,
    RecordCleanResponse,
)
from data_quality_api.phone_tools import looks_like_phone_column, normalize_phone
from data_quality_api.profiling import profile_frame, read_csv_text, records_to_frame


def clean_csv_request(request: CsvCleanRequest) -> CsvCleanResponse:
    frame = read_csv_text(request.csv_text, request.delimiter)
    cleaned, duplicates_removed = clean_frame(
        frame,
        deduplicate_keys=request.deduplicate_keys,
        trim_strings=request.trim_strings,
        empty_strings_to_null=request.empty_strings_to_null,
        lowercase_email_fields=request.lowercase_email_fields,
        normalize_phone_fields=False,
        default_phone_region="US",
    )
    profile = profile_frame(cleaned.fillna(""))
    output = StringIO()
    cleaned.to_csv(output, index=False, float_format="%.4f")
    return CsvCleanResponse(
        profile=profile,
        cleaned_csv=output.getvalue(),
        cleaned_records_sample=_sample_records(cleaned),
        duplicates_removed=duplicates_removed,
    )


def clean_record_request(request: RecordCleanRequest) -> RecordCleanResponse:
    frame = records_to_frame(request.records)
    cleaned, duplicates_removed = clean_frame(
        frame,
        deduplicate_keys=request.deduplicate_keys,
        trim_strings=request.trim_strings,
        empty_strings_to_null=request.empty_strings_to_null,
        lowercase_email_fields=request.lowercase_email_fields,
        normalize_phone_fields=request.normalize_phone_fields,
        default_phone_region=request.default_phone_region,
    )
    return RecordCleanResponse(
        profile=profile_frame(cleaned.fillna("")),
        cleaned_records=_sample_records(cleaned, limit=len(cleaned)),
        duplicates_removed=duplicates_removed,
    )


def clean_frame(
    frame: pd.DataFrame,
    *,
    deduplicate_keys: list[str],
    trim_strings: bool,
    empty_strings_to_null: bool,
    lowercase_email_fields: bool,
    normalize_phone_fields: bool,
    default_phone_region: str,
) -> tuple[pd.DataFrame, int]:
    cleaned = frame.copy()
    for column in cleaned.columns:
        cleaned[column] = cleaned[column].map(
            lambda value: _clean_value(
                value,
                trim_strings=trim_strings,
                empty_strings_to_null=empty_strings_to_null,
            )
        )
        if lowercase_email_fields and looks_like_email_column(str(column)):
            cleaned[column] = cleaned[column].map(_normalize_email_value)
        if normalize_phone_fields and looks_like_phone_column(str(column)):
            cleaned[column] = cleaned[column].map(
                lambda value: _normalize_phone_value(value, default_phone_region)
            )
    before = len(cleaned)
    if deduplicate_keys:
        missing = [key for key in deduplicate_keys if key not in cleaned.columns]
        if missing:
            raise ValueError(f"Cannot deduplicate; missing columns: {', '.join(missing)}")
        cleaned = cleaned.drop_duplicates(subset=deduplicate_keys, keep="first")
    return cleaned.reset_index(drop=True), before - len(cleaned)


def _clean_value(
    value: Any,
    *,
    trim_strings: bool,
    empty_strings_to_null: bool,
) -> Any:
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    cleaned = " ".join(value.split()) if trim_strings else value
    if empty_strings_to_null and cleaned.strip().lower() in {"", "none", "null", "nan", "n/a"}:
        return None
    return cleaned


def _normalize_email_value(value: Any) -> Any:
    if value is None:
        return None
    result = normalize_email(str(value))
    return result.normalized if result.valid_format else value


def _normalize_phone_value(value: Any, default_region: str) -> Any:
    if value is None:
        return None
    result = normalize_phone(str(value), default_region)
    return result.e164 if result.valid else value


def _sample_records(frame: pd.DataFrame, limit: int = 10) -> list[dict[str, Any]]:
    return frame.where(pd.notna(frame), None).head(limit).to_dict(orient="records")
