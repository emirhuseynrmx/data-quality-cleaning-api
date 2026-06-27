from __future__ import annotations

from data_quality_api.cleaning import clean_record_request
from data_quality_api.models import RecordCleanRequest


def test_clean_record_request_normalizes_and_deduplicates() -> None:
    request = RecordCleanRequest(
        records=[
            {"email": " ALICE@Example.COM ", "phone": "(415) 555-0199", "name": " Alice "},
            {"email": "alice@example.com", "phone": "+14155550199", "name": "Alice"},
            {"email": "bad-email", "phone": "bad", "name": ""},
        ],
        deduplicate_keys=["email"],
    )

    response = clean_record_request(request)

    assert response.duplicates_removed == 1
    assert response.cleaned_records[0]["email"] == "alice@example.com"
    assert response.cleaned_records[0]["phone"] == "+14155550199"
    assert response.profile.rows == 2
