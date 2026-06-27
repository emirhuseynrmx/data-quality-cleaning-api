from __future__ import annotations

from email_validator import EmailNotValidError, validate_email

from data_quality_api.models import EmailBatchResponse, EmailResult
from data_quality_api.settings import DISPOSABLE_DOMAINS


def normalize_email_batch(emails: list[str]) -> EmailBatchResponse:
    results = [normalize_email(value) for value in emails]
    valid = sum(result.valid_format for result in results)
    return EmailBatchResponse(
        total=len(results),
        valid=valid,
        invalid=len(results) - valid,
        results=results,
    )


def normalize_email(value: str) -> EmailResult:
    raw = value.strip()
    try:
        validated = validate_email(raw, check_deliverability=False)
    except EmailNotValidError as error:
        return EmailResult(
            input=value,
            normalized=None,
            valid_format=False,
            domain=None,
            username=None,
            disposable_domain=False,
            reason=str(error),
        )
    normalized = validated.normalized.lower()
    username, domain = normalized.rsplit("@", 1)
    return EmailResult(
        input=value,
        normalized=normalized,
        valid_format=True,
        domain=domain,
        username=username,
        disposable_domain=domain in DISPOSABLE_DOMAINS,
    )


def looks_like_email_column(column: str) -> bool:
    normalized = column.lower()
    return "email" in normalized or normalized in {"mail", "e_mail"}
