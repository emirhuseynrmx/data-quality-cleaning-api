from __future__ import annotations

from typing import Annotated

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from data_quality_api.cleaning import clean_csv_request, clean_record_request
from data_quality_api.domain_tools import parse_domains
from data_quality_api.email_tools import normalize_email_batch
from data_quality_api.models import (
    CsvCleanRequest,
    CsvCleanResponse,
    CsvProfileRequest,
    CsvProfileResponse,
    DomainParseRequest,
    DomainParseResponse,
    EmailBatchRequest,
    EmailBatchResponse,
    PhoneBatchRequest,
    PhoneBatchResponse,
    RecordCleanRequest,
    RecordCleanResponse,
)
from data_quality_api.phone_tools import normalize_phone_batch
from data_quality_api.profiling import profile_frame, read_csv_text
from data_quality_api.settings import MAX_CSV_CHARS

app = FastAPI(
    title="CRM Lead List Cleaning API",
    version="0.1.0",
    description=(
        "RapidAPI-ready lead-list hygiene API for CSV profiling, CSV cleaning, "
        "CSV upload cleaning, JSON record cleanup, email normalization, "
        "phone normalization, and domain parsing."
    ),
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/email/normalize", response_model=EmailBatchResponse)
def normalize_emails(request: EmailBatchRequest) -> EmailBatchResponse:
    return normalize_email_batch(request.emails)


@app.post("/v1/phone/normalize", response_model=PhoneBatchResponse)
def normalize_phones(request: PhoneBatchRequest) -> PhoneBatchResponse:
    return normalize_phone_batch(request.phones, request.default_region)


@app.post("/v1/domain/parse", response_model=DomainParseResponse)
def parse_domain_values(request: DomainParseRequest) -> DomainParseResponse:
    return parse_domains(request.values)


@app.post("/v1/csv/profile", response_model=CsvProfileResponse)
def profile_csv(request: CsvProfileRequest) -> CsvProfileResponse:
    try:
        frame = read_csv_text(request.csv_text, request.delimiter)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return CsvProfileResponse(
        profile=profile_frame(frame),
        sample_records=frame.head(request.sample_rows).to_dict(orient="records"),
    )


@app.post("/v1/csv/clean", response_model=CsvCleanResponse)
def clean_csv(request: CsvCleanRequest) -> CsvCleanResponse:
    try:
        return clean_csv_request(request)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/v1/csv/upload/profile", response_model=CsvProfileResponse)
async def profile_csv_upload(
    file: Annotated[UploadFile, File()],
    delimiter: Annotated[str, Form(min_length=1, max_length=1)] = ",",
    sample_rows: Annotated[int, Form(ge=1, le=25)] = 5,
) -> CsvProfileResponse:
    csv_text = await _read_uploaded_csv(file)
    return profile_csv(
        CsvProfileRequest(
            csv_text=csv_text,
            delimiter=delimiter,
            sample_rows=sample_rows,
        )
    )


@app.post("/v1/csv/upload/clean", response_model=CsvCleanResponse)
async def clean_csv_upload(
    file: Annotated[UploadFile, File()],
    delimiter: Annotated[str, Form(min_length=1, max_length=1)] = ",",
    trim_strings: Annotated[bool, Form()] = True,
    empty_strings_to_null: Annotated[bool, Form()] = True,
    lowercase_email_fields: Annotated[bool, Form()] = True,
    normalize_phone_fields: Annotated[bool, Form()] = True,
    default_phone_region: Annotated[str, Form(min_length=2, max_length=2)] = "US",
    neutralize_spreadsheet_formulas: Annotated[bool, Form()] = True,
    deduplicate_keys: Annotated[str, Form()] = "",
) -> CsvCleanResponse:
    csv_text = await _read_uploaded_csv(file)
    return clean_csv(
        CsvCleanRequest(
            csv_text=csv_text,
            delimiter=delimiter,
            trim_strings=trim_strings,
            empty_strings_to_null=empty_strings_to_null,
            lowercase_email_fields=lowercase_email_fields,
            normalize_phone_fields=normalize_phone_fields,
            default_phone_region=default_phone_region,
            neutralize_spreadsheet_formulas=neutralize_spreadsheet_formulas,
            deduplicate_keys=_parse_deduplicate_keys(deduplicate_keys),
        )
    )


@app.post("/v1/records/clean", response_model=RecordCleanResponse)
def clean_records(request: RecordCleanRequest) -> RecordCleanResponse:
    try:
        return clean_record_request(request)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


def main() -> None:
    uvicorn.run("data_quality_api.api:app", host="0.0.0.0", port=8000, reload=False)


async def _read_uploaded_csv(file: UploadFile) -> str:
    content = await file.read(MAX_CSV_CHARS + 1)
    if len(content) > MAX_CSV_CHARS:
        raise HTTPException(status_code=413, detail=f"CSV upload exceeds {MAX_CSV_CHARS} bytes.")
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise HTTPException(status_code=400, detail="CSV upload must be UTF-8 encoded.") from error


def _parse_deduplicate_keys(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]
