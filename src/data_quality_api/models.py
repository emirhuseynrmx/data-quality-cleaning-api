from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from data_quality_api.settings import MAX_BATCH_SIZE, MAX_CSV_CHARS, MAX_RECORDS


class EmailBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    emails: list[str] = Field(min_length=1, max_length=MAX_BATCH_SIZE)


class EmailResult(BaseModel):
    input: str
    normalized: str | None
    valid_format: bool
    domain: str | None
    username: str | None
    disposable_domain: bool
    reason: str | None = None


class EmailBatchResponse(BaseModel):
    total: int
    valid: int
    invalid: int
    results: list[EmailResult]


class PhoneBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phones: list[str] = Field(min_length=1, max_length=MAX_BATCH_SIZE)
    default_region: str = Field(default="US", min_length=2, max_length=2)


class PhoneResult(BaseModel):
    input: str
    e164: str | None
    national: str | None
    valid: bool
    country_code: int | None
    reason: str | None = None


class PhoneBatchResponse(BaseModel):
    total: int
    valid: int
    invalid: int
    results: list[PhoneResult]


class CsvProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    csv_text: str = Field(min_length=1, max_length=MAX_CSV_CHARS)
    delimiter: str = Field(default=",", min_length=1, max_length=1)
    sample_rows: int = Field(default=5, ge=1, le=25)


class CsvCleanRequest(CsvProfileRequest):
    trim_strings: bool = True
    empty_strings_to_null: bool = True
    lowercase_email_fields: bool = True
    deduplicate_keys: list[str] = Field(default_factory=list, max_length=10)


class RecordCleanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    records: list[dict[str, Any]] = Field(min_length=1, max_length=MAX_RECORDS)
    trim_strings: bool = True
    empty_strings_to_null: bool = True
    lowercase_email_fields: bool = True
    normalize_phone_fields: bool = True
    default_phone_region: str = Field(default="US", min_length=2, max_length=2)
    deduplicate_keys: list[str] = Field(default_factory=list, max_length=10)


class ColumnProfile(BaseModel):
    name: str
    inferred_type: Literal[
        "integer",
        "number",
        "boolean",
        "date",
        "email",
        "phone",
        "text",
        "empty",
    ]
    missing_count: int
    missing_rate: float
    unique_count: int
    example_values: list[Any]


class DatasetProfile(BaseModel):
    rows: int
    columns: int
    duplicate_rows: int
    quality_score: float
    column_profiles: list[ColumnProfile]
    warnings: list[str]


class CsvProfileResponse(BaseModel):
    profile: DatasetProfile
    sample_records: list[dict[str, Any]]


class CsvCleanResponse(BaseModel):
    profile: DatasetProfile
    cleaned_csv: str
    cleaned_records_sample: list[dict[str, Any]]
    duplicates_removed: int


class RecordCleanResponse(BaseModel):
    profile: DatasetProfile
    cleaned_records: list[dict[str, Any]]
    duplicates_removed: int


class ErrorResponse(BaseModel):
    detail: str


class DomainParseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    values: list[str] = Field(min_length=1, max_length=MAX_BATCH_SIZE)

    @field_validator("values")
    @classmethod
    def strip_values(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values]


class DomainParseResult(BaseModel):
    input: str
    domain: str | None
    source: Literal["email", "url", "domain", "unknown"]
    valid_shape: bool


class DomainParseResponse(BaseModel):
    total: int
    results: list[DomainParseResult]
