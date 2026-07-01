from __future__ import annotations

import json
from dataclasses import dataclass
from time import monotonic
from typing import Annotated

from litestar import Litestar, get, post
from litestar.connection import ASGIConnection
from litestar.datastructures import UploadFile
from litestar.enums import RequestEncodingType
from litestar.exceptions import HTTPException, NotAuthorizedException
from litestar.handlers import BaseRouteHandler
from litestar.middleware import AbstractMiddleware
from litestar.params import Body
from litestar.types import Receive, Scope, Send

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

IDEMPOTENCY_CACHE = IdempotencyCache()
RATE_LIMITER = FixedWindowRateLimiter(
    limit=RATE_LIMIT_REQUESTS,
    window_seconds=RATE_LIMIT_WINDOW_SECONDS,
)
AUDIT_LOG = AuditLog()


def _verify_rapidapi_secret(connection: ASGIConnection, _: BaseRouteHandler) -> None:
    api_key = connection.headers.get("X-RapidAPI-Proxy-Secret")
    if RAPIDAPI_SECRET and api_key != RAPIDAPI_SECRET:
        raise NotAuthorizedException("Invalid RapidAPI secret")


class ServiceControlsMiddleware(AbstractMiddleware):
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        raw_headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        request_id = raw_headers.get("x-request-id") or new_request_id()
        identity = _request_identity(scope, raw_headers)
        started_at = monotonic()

        allowed, retry_after = RATE_LIMITER.check(identity)
        if not allowed:
            body = json.dumps({"detail": "Rate limit exceeded."}).encode()
            await send({
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"retry-after", str(retry_after).encode()),
                    (b"x-request-id", request_id.encode()),
                    (b"content-length", str(len(body)).encode()),
                ],
            })
            await send({"type": "http.response.body", "body": body, "more_body": False})
            _record_audit(scope, 429, started_at, identity, request_id, raw_headers)
            return

        idempotency_key = raw_headers.get("x-idempotency-key")
        method = scope.get("method", "GET")
        path = scope.get("path", "/")
        cache_key = _idempotency_cache_key(method, path, identity, idempotency_key)

        if cache_key is not None:
            cached = IDEMPOTENCY_CACHE.get(cache_key)
            if cached is not None:
                headers = dict(cached.headers)
                headers["x-idempotent-replay"] = "true"
                headers["x-request-id"] = request_id
                resp_body = cached.body
                await send({
                    "type": "http.response.start",
                    "status": cached.status_code,
                    "headers": [(k.encode(), v.encode()) for k, v in headers.items()],
                })
                await send({"type": "http.response.body", "body": resp_body, "more_body": False})
                _record_audit(
                    scope, cached.status_code, started_at, identity, request_id, raw_headers
                )
                return

        resp_status = 200
        resp_headers: list[tuple[bytes, bytes]] = []
        resp_media_type = "application/json"
        body_chunks: list[bytes] = []

        async def capture_send(message: dict) -> None:
            nonlocal resp_status, resp_headers, resp_media_type
            if message["type"] == "http.response.start":
                resp_status = message["status"]
                resp_headers = list(message.get("headers", []))
                for k, v in resp_headers:
                    if k.lower() == b"content-type":
                        resp_media_type = v.decode().split(";")[0].strip()
            elif message["type"] == "http.response.body":
                body_chunks.append(message.get("body", b""))

        await self.app(scope, receive, capture_send)
        resp_body = b"".join(body_chunks)

        headers_dict = {k.decode().lower(): v.decode() for k, v in resp_headers}
        headers_dict["x-request-id"] = request_id

        if cache_key is not None and 200 <= resp_status < 300:
            IDEMPOTENCY_CACHE.set(
                cache_key,
                CachedResponse(
                    status_code=resp_status,
                    body=resp_body,
                    media_type=resp_media_type,
                    headers=headers_dict,
                ),
            )

        _record_audit(scope, resp_status, started_at, identity, request_id, raw_headers)

        new_resp_headers = [(k.encode(), v.encode()) for k, v in headers_dict.items()]
        await send({
            "type": "http.response.start",
            "status": resp_status,
            "headers": new_resp_headers,
        })
        await send({"type": "http.response.body", "body": resp_body, "more_body": False})


@get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@get("/ops/audit")
def audit_tail(limit: int = 25) -> AuditTailResponse:
    return AuditTailResponse(events=AUDIT_LOG.tail(limit=max(1, min(limit, 100))))


@post("/v1/email/normalize", status_code=200)
def normalize_emails(data: EmailBatchRequest) -> EmailBatchResponse:
    return normalize_email_batch(data.emails)


@post("/v1/phone/normalize", status_code=200)
def normalize_phones(data: PhoneBatchRequest) -> PhoneBatchResponse:
    return normalize_phone_batch(data.phones, data.default_region)


@post("/v1/domain/parse", status_code=200)
def parse_domain_values(data: DomainParseRequest) -> DomainParseResponse:
    return parse_domains(data.values)


def _csv_profile_logic(request: CsvProfileRequest) -> CsvProfileResponse:
    try:
        frame = read_csv_text(request.csv_text, request.delimiter)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return CsvProfileResponse(
        profile=profile_frame(frame),
        sample_records=frame.head(request.sample_rows).to_dict(orient="records"),
    )


def _csv_clean_logic(request: CsvCleanRequest) -> CsvCleanResponse:
    try:
        return clean_csv_request(request)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@post("/v1/csv/profile", status_code=200)
def csv_profile(data: CsvProfileRequest) -> CsvProfileResponse:
    return _csv_profile_logic(data)


@post("/v1/csv/clean", status_code=200)
def csv_clean(data: CsvCleanRequest) -> CsvCleanResponse:
    return _csv_clean_logic(data)


@dataclass
class ProfileUploadForm:
    file: UploadFile
    delimiter: str = ","
    sample_rows: int = 5


@dataclass
class CleanUploadForm:
    file: UploadFile
    delimiter: str = ","
    trim_strings: bool = True
    empty_strings_to_null: bool = True
    lowercase_email_fields: bool = True
    normalize_phone_fields: bool = True
    default_phone_region: str = "US"
    neutralize_spreadsheet_formulas: bool = True
    deduplicate_keys: str = ""


@post("/v1/csv/upload/profile", status_code=200)
async def csv_upload_profile(
    data: Annotated[ProfileUploadForm, Body(media_type=RequestEncodingType.MULTI_PART)],
) -> CsvProfileResponse:
    csv_text = await _read_uploaded_csv(data.file)
    return _csv_profile_logic(
        CsvProfileRequest(
            csv_text=csv_text,
            delimiter=data.delimiter,
            sample_rows=data.sample_rows,
        )
    )


@post("/v1/csv/upload/clean", status_code=200)
async def csv_upload_clean(
    data: Annotated[CleanUploadForm, Body(media_type=RequestEncodingType.MULTI_PART)],
) -> CsvCleanResponse:
    csv_text = await _read_uploaded_csv(data.file)
    return _csv_clean_logic(
        CsvCleanRequest(
            csv_text=csv_text,
            delimiter=data.delimiter,
            trim_strings=data.trim_strings,
            empty_strings_to_null=data.empty_strings_to_null,
            lowercase_email_fields=data.lowercase_email_fields,
            normalize_phone_fields=data.normalize_phone_fields,
            default_phone_region=data.default_phone_region,
            neutralize_spreadsheet_formulas=data.neutralize_spreadsheet_formulas,
            deduplicate_keys=_parse_deduplicate_keys(data.deduplicate_keys),
        )
    )


@post("/v1/records/clean", status_code=200)
def records_clean(data: RecordCleanRequest) -> RecordCleanResponse:
    try:
        return clean_record_request(data)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


app = Litestar(
    route_handlers=[
        health,
        audit_tail,
        normalize_emails,
        normalize_phones,
        parse_domain_values,
        csv_profile,
        csv_clean,
        csv_upload_profile,
        csv_upload_clean,
        records_clean,
    ],
    middleware=[ServiceControlsMiddleware],
    guards=[_verify_rapidapi_secret],
)


def main() -> None:
    import uvicorn
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


def _request_identity(scope: dict, headers: dict) -> str:
    api_key = headers.get("x-api-key")
    if api_key:
        return f"api-key:{api_key}"
    client = scope.get("client")
    client_host = client[0] if client else "unknown"
    return f"client:{client_host}"


def _idempotency_cache_key(
    method: str,
    path: str,
    identity: str,
    idempotency_key: str | None,
) -> str | None:
    if method not in {"POST", "PUT", "PATCH"} or not idempotency_key:
        return None
    return f"{identity}:{method}:{path}:{idempotency_key}"


def _record_audit(
    scope: dict,
    status_code: int,
    started_at: float,
    identity: str,
    request_id: str,
    headers: dict,
) -> None:
    AUDIT_LOG.add(
        AuditEvent(
            request_id=request_id,
            method=scope.get("method", "GET"),
            path=scope.get("path", "/"),
            status_code=status_code,
            duration_ms=round((monotonic() - started_at) * 1000, 3),
            identity_hash=identity_hash(identity),
            idempotency_key_present=bool(headers.get("x-idempotency-key")),
        )
    )
