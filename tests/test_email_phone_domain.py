from __future__ import annotations

from data_quality_api.domain_tools import parse_domains
from data_quality_api.email_tools import normalize_email_batch
from data_quality_api.phone_tools import normalize_phone_batch


def test_normalize_email_batch() -> None:
    response = normalize_email_batch([" ALICE@Example.COM ", "bad-email"])

    assert response.total == 2
    assert response.valid == 1
    assert response.results[0].normalized == "alice@example.com"
    assert response.results[1].valid_format is False


def test_normalize_phone_batch() -> None:
    response = normalize_phone_batch(["(415) 555-0199", "nope"], "US")

    assert response.valid == 1
    assert response.results[0].e164 == "+14155550199"
    assert response.results[1].valid is False


def test_parse_domains_from_mixed_values() -> None:
    response = parse_domains(["alice@example.com", "https://www.openai.com/blog", "bad value"])

    assert response.results[0].domain == "example.com"
    assert response.results[1].domain == "openai.com"
    assert response.results[2].valid_shape is False
