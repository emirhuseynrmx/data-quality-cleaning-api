from __future__ import annotations

from fastapi.testclient import TestClient

from data_quality_api.api import app

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
