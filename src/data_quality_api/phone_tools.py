from __future__ import annotations

import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat

from data_quality_api.models import PhoneBatchResponse, PhoneResult


def normalize_phone_batch(phones: list[str], default_region: str) -> PhoneBatchResponse:
    results = [normalize_phone(value, default_region) for value in phones]
    valid = sum(result.valid for result in results)
    return PhoneBatchResponse(
        total=len(results),
        valid=valid,
        invalid=len(results) - valid,
        results=results,
    )


def normalize_phone(value: str, default_region: str = "US") -> PhoneResult:
    raw = value.strip()
    try:
        parsed = phonenumbers.parse(raw, default_region.upper())
    except NumberParseException as error:
        return PhoneResult(
            input=value,
            e164=None,
            national=None,
            valid=False,
            country_code=None,
            reason=str(error),
        )
    valid = phonenumbers.is_valid_number(parsed)
    if not valid:
        return PhoneResult(
            input=value,
            e164=None,
            national=None,
            valid=False,
            country_code=parsed.country_code,
            reason="Invalid phone number for region.",
        )
    return PhoneResult(
        input=value,
        e164=phonenumbers.format_number(parsed, PhoneNumberFormat.E164),
        national=phonenumbers.format_number(parsed, PhoneNumberFormat.NATIONAL),
        valid=True,
        country_code=parsed.country_code,
    )


def looks_like_phone_column(column: str) -> bool:
    normalized = column.lower()
    return any(token in normalized for token in ["phone", "mobile", "tel", "whatsapp"])
