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
            csv_text=(
                "name,email,phone,note\n"
                " Alice ,ALICE@Example.COM,(415) 555-0199,=SUM(A1:A2)\n"
                "Alice,alice@example.com,+14155550199,+cmd\n"
            ),
            deduplicate_keys=["email"],
        )
    )

    assert response.duplicates_removed == 1
    assert "alice@example.com" in response.cleaned_csv
    assert "+14155550199" in response.cleaned_csv
    assert "'=SUM(A1:A2)" in response.cleaned_csv
    assert response.profile.duplicate_key_summary[0].duplicate_records == 2


def test_profile_reports_confidence_and_invalid_counts() -> None:
    frame = read_csv_text(
        "email,phone\n"
        "alice@example.com,(415) 555-0199\n"
        "bad-email,not-a-phone\n"
    )
    profile = profile_frame(frame)

    email_profile = next(column for column in profile.column_profiles if column.name == "email")
    phone_profile = next(column for column in profile.column_profiles if column.name == "phone")

    assert email_profile.confidence == 0.5
    assert email_profile.invalid_count == 1
    assert phone_profile.confidence == 0.5
    assert phone_profile.invalid_count == 1
    assert profile.invalid_email_count == 1
    assert profile.invalid_phone_count == 1
