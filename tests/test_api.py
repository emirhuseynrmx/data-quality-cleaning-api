from __future__ import annotations

from fastapi.testclient import TestClient

from data_quality_api.api import AUDIT_LOG, IDEMPOTENCY_CACHE, app
from data_quality_api.service_controls import FixedWindowRateLimiter

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_records_clean_endpoint() -> None:
    response = client.post(
        "/v1/records/clean",
        json={
            "records": [
                {"email": "ALICE@Example.COM", "phone": "(415) 555-0199"},
                {"email": "alice@example.com", "phone": "+14155550199"},
            ],
            "deduplicate_keys": ["email"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["duplicates_removed"] == 1
    assert payload["cleaned_records"][0]["email"] == "alice@example.com"


def test_csv_profile_endpoint() -> None:
    response = client.post(
        "/v1/csv/profile",
        json={"csv_text": "name,email\nAlice,alice@example.com\n"},
    )

    assert response.status_code == 200
    assert response.json()["profile"]["rows"] == 1


def test_csv_clean_bad_deduplicate_key_returns_400() -> None:
    response = client.post(
        "/v1/csv/clean",
        json={
            "csv_text": "name,email\nAlice,alice@example.com\n",
            "deduplicate_keys": ["missing"],
        },
    )

    assert response.status_code == 400


def test_csv_upload_clean_endpoint() -> None:
    response = client.post(
        "/v1/csv/upload/clean",
        files={
            "file": (
                "leads.csv",
                b"email,phone\nALICE@Example.COM,(415) 555-0199\nalice@example.com,+14155550199\n",
                "text/csv",
            )
        },
        data={"deduplicate_keys": "email"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["duplicates_removed"] == 1
    assert "+14155550199" in payload["cleaned_csv"]


def test_post_endpoint_supports_idempotency_replay() -> None:
    IDEMPOTENCY_CACHE.clear()
    headers = {"X-Idempotency-Key": "clean-001", "X-API-Key": "idempotency-test"}
    body = {
        "records": [{"email": "ALICE@Example.COM", "phone": "(415) 555-0199"}],
    }

    first = client.post("/v1/records/clean", json=body, headers=headers)
    second = client.post("/v1/records/clean", json=body, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.headers["X-Idempotent-Replay"] == "true"
    assert first.json() == second.json()


def test_audit_tail_records_request_metadata() -> None:
    AUDIT_LOG.clear()

    response = client.get("/health", headers={"X-API-Key": "audit-test"})
    audit = client.get("/ops/audit", headers={"X-API-Key": "audit-test"})

    assert response.status_code == 200
    assert audit.status_code == 200
    events = audit.json()["events"]
    assert any(event["path"] == "/health" for event in events)
    assert all("identity_hash" in event for event in events)


def test_fixed_window_rate_limiter_rejects_after_limit() -> None:
    limiter = FixedWindowRateLimiter(limit=2, window_seconds=60)

    assert limiter.check("client-a", now=100.0) == (True, 0)
    assert limiter.check("client-a", now=101.0) == (True, 0)
    allowed, retry_after = limiter.check("client-a", now=102.0)

    assert allowed is False
    assert retry_after > 0
