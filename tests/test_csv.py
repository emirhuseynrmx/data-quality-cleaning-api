from __future__ import annotations

from data_quality_api.cleaning import clean_csv_request
from data_quality_api.models import CsvCleanRequest
from data_quality_api.profiling import profile_frame, read_csv_text


def test_profile_csv_text() -> None:
    frame = read_csv_text("name,email\nAlice,alice@example.com\nBob,\n")
    profile = profile_frame(frame)

    assert profile.rows == 2
    assert profile.columns == 2
    assert profile.column_profiles[1].inferred_type == "email"


def test_clean_csv_request_outputs_csv() -> None:
    response = clean_csv_request(
        CsvCleanRequest(
            csv_text="name,email\n Alice ,ALICE@Example.COM\nAlice,alice@example.com\n",
            deduplicate_keys=["email"],
        )
    )

    assert response.duplicates_removed == 1
    assert "alice@example.com" in response.cleaned_csv
