from __future__ import annotations

from pathlib import Path

from data_quality_api.cleaning import clean_csv_request
from data_quality_api.models import CsvCleanRequest
from data_quality_api.reporting import build_report, generate_sample_report, render_typst


def test_build_report_prioritizes_client_actions() -> None:
    response = clean_csv_request(
        CsvCleanRequest(
            csv_text=(
                "name,email,phone\n"
                "Alice,ALICE@Example.COM,(415) 555-0199\n"
                "Alice,alice@example.com,+14155550199\n"
                "Bob,bad-email,not-a-phone\n"
            ),
            deduplicate_keys=["email"],
        )
    )

    report = build_report(response, title="Lead Quality")

    assert report.title == "Lead Quality"
    assert report.duplicates_removed == 1
    assert any(action.issue == "Duplicate leads" for action in report.actions)
    assert any(action.issue == "Invalid email values" for action in report.actions)


def test_render_typst_contains_import_readiness_sections() -> None:
    response = clean_csv_request(
        CsvCleanRequest(csv_text="name,email\nAlice,alice@example.com\n")
    )
    typst = render_typst(build_report(response, title="Lead Quality"))

    assert "= Lead Quality" in typst
    assert "Import Readiness" in typst
    assert "Column Profile" in typst
    assert "Cleaned Sample" in typst


def test_generate_sample_report_writes_typst_without_pdf(tmp_path: Path) -> None:
    csv_path = tmp_path / "leads.csv"
    csv_path.write_text("name,email\nAlice,alice@example.com\n", encoding="utf-8")

    typ_path, pdf_path = generate_sample_report(csv_path, tmp_path / "out", compile_pdf=False)

    assert typ_path.exists()
    assert pdf_path is None
    assert "Lead List Quality Report" in typ_path.read_text(encoding="utf-8")
