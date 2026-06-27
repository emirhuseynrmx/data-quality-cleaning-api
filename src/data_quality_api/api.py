from __future__ import annotations

import uvicorn
from fastapi import FastAPI, HTTPException

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

app = FastAPI(
    title="Data Quality Cleaning API",
    version="0.1.0",
    description=(
        "RapidAPI-ready data hygiene API for CSV profiling, CSV cleaning, "
        "JSON record cleanup, email normalization, phone normalization, and domain parsing."
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


@app.post("/v1/records/clean", response_model=RecordCleanResponse)
def clean_records(request: RecordCleanRequest) -> RecordCleanResponse:
    try:
        return clean_record_request(request)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


def main() -> None:
    uvicorn.run("data_quality_api.api:app", host="0.0.0.0", port=8000, reload=False)
