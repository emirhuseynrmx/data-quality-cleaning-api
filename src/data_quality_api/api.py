from __future__ import annotations

from time import monotonic
from typing import Annotated

import uvicorn
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    Security,
    UploadFile,
)
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader

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
from data_quality_api.service_controls import (
    AuditEvent,
    AuditLog,
    AuditTailResponse,
    CachedResponse,
    FixedWindowRateLimiter,
    IdempotencyCache,
    identity_hash,
    new_request_id,
)
from data_quality_api.settings import (
    MAX_CSV_CHARS,
    RAPIDAPI_SECRET,
    RATE_LIMIT_REQUESTS,
    RATE_LIMIT_WINDOW_SECONDS,
)

rapidapi_header = APIKeyHeader(name="X-RapidAPI-Proxy-Secret", auto_error=False)


async def verify_rapidapi_secret(api_key: str = Security(rapidapi_header)) -> None:
    if RAPIDAPI_SECRET and api_key != RAPIDAPI_SECRET:
        raise HTTPException(status_code=403, detail="Invalid RapidAPI secret")

app = FastAPI(
    title="CRM Lead List Cleaning API",
    version="0.1.0",
    description=(
        "RapidAPI-ready lead-list hygiene API for CSV profiling, CSV cleaning, "
        "CSV upload cleaning, JSON record cleanup, email normalization, "
        "phone normalization, and domain parsing."
    ),
    dependencies=[Depends(verify_rapidapi_secret)],
)

IDEMPOTENCY_CACHE = IdempotencyCache()
RATE_LIMITER = FixedWindowRateLimiter(
    limit=RATE_LIMIT_REQUESTS,
    window_seconds=RATE_LIMIT_WINDOW_SECONDS,
)
AUDIT_LOG = AuditLog()


@app.middleware("http")
async def service_controls(request: Request, call_next) -> Response:
    request_id = request.headers.get("x-request-id") or new_request_id()
    started_at = monotonic()
    identity = _request_identity(request)
    allowed, retry_after = RATE_LIMITER.check(identity)
    if not allowed:
        response = JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded."},
            headers={"Retry-After": str(retry_after), "X-Request-Id": request_id},
        )
        _record_audit(request, response.status_code, started_at, identity, request_id)
        return response

    idempotency_key = request.headers.get("x-idempotency-key")
    cache_key = _idempotency_cache_key(request, identity, idempotency_key)
    if cache_key is not None:
        cached = IDEMPOTENCY_CACHE.get(cache_key)
        if cached is not None:
            headers = dict(cached.headers)
            headers["X-Idempotent-Replay"] = "true"
            headers["X-Request-Id"] = request_id
            response = Response(
                content=cached.body,
                status_code=cached.status_code,
                headers=headers,
                media_type=cached.media_type,
            )
            _record_audit(request, response.status_code, started_at, identity, request_id)
            return response

    response = await call_next(request)
    body = b""
    async for chunk in response.body_iterator:
        body += chunk
    headers = dict(response.headers)
    headers["X-Request-Id"] = request_id
    if cache_key is not None and response.status_code < 500:
        IDEMPOTENCY_CACHE.set(
            cache_key,
            CachedResponse(
                status_code=response.status_code,
                body=body,
                media_type=response.media_type,
                headers=headers,
            ),
        )
    _record_audit(request, response.status_code, started_at, identity, request_id)
    return Response(
        content=body,
        status_code=response.status_code,
        headers=headers,
        media_type=response.media_type,
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ops/audit", response_model=AuditTailResponse)
def audit_tail(limit: int = 25) -> AuditTailResponse:
    return AuditTailResponse(events=AUDIT_LOG.tail(limit=max(1, min(limit, 100))))


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


def _request_identity(request: Request) -> str:
    api_key = request.headers.get("x-api-key")
    if api_key:
        return f"api-key:{api_key}"
    client_host = request.client.host if request.client else "unknown"
    return f"client:{client_host}"


def _idempotency_cache_key(
    request: Request,
    identity: str,
    idempotency_key: str | None,
) -> str | None:
    if request.method not in {"POST", "PUT", "PATCH"} or not idempotency_key:
        return None
    return f"{identity}:{request.method}:{request.url.path}:{idempotency_key}"


def _record_audit(
    request: Request,
    status_code: int,
    started_at: float,
    identity: str,
    request_id: str,
) -> None:
    AUDIT_LOG.add(
        AuditEvent(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=status_code,
            duration_ms=round((monotonic() - started_at) * 1000, 3),
            identity_hash=identity_hash(identity),
            idempotency_key_present=bool(request.headers.get("x-idempotency-key")),
        )
    )
