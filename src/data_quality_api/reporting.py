from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from data_quality_api.cleaning import clean_csv_request
from data_quality_api.models import ColumnProfile, CsvCleanRequest, CsvCleanResponse


class ReportAction(BaseModel):
    model_config = ConfigDict(frozen=True)

    priority: str
    issue: str
    action: str


class LeadQualityReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    rows_before: int = Field(ge=0)
    rows_after: int = Field(ge=0)
    columns: int = Field(ge=0)
    quality_score: float = Field(ge=0, le=100)
    duplicates_removed: int = Field(ge=0)
    invalid_email_count: int = Field(ge=0)
    invalid_phone_count: int = Field(ge=0)
    warnings: tuple[str, ...]
    column_profiles: tuple[ColumnProfile, ...]
    sample_records: tuple[dict[str, Any], ...]
    actions: tuple[ReportAction, ...]


def build_report(response: CsvCleanResponse, *, title: str) -> LeadQualityReport:
    profile = response.profile
    return LeadQualityReport(
        title=title,
        rows_before=profile.rows + response.duplicates_removed,
        rows_after=profile.rows,
        columns=profile.columns,
        quality_score=profile.quality_score,
        duplicates_removed=response.duplicates_removed,
        invalid_email_count=profile.invalid_email_count,
        invalid_phone_count=profile.invalid_phone_count,
        warnings=tuple(profile.warnings),
        column_profiles=tuple(profile.column_profiles),
        sample_records=tuple(response.cleaned_records_sample[:6]),
        actions=tuple(_recommended_actions(response)),
    )


def generate_sample_report(
    csv_path: Path,
    output_dir: Path,
    *,
    title: str = "CRM Lead List Quality Report",
    compile_pdf: bool = True,
) -> tuple[Path, Path | None]:
    csv_text = csv_path.read_text(encoding="utf-8")
    response = clean_csv_request(
        CsvCleanRequest(
            csv_text=csv_text,
            deduplicate_keys=["email"],
            neutralize_spreadsheet_formulas=True,
        )
    )
    report = build_report(response, title=title)
    output_dir.mkdir(parents=True, exist_ok=True)
    typ_path = output_dir / "lead_quality_report.typ"
    typ_path.write_text(render_typst(report), encoding="utf-8")
    pdf_path = output_dir / "lead_quality_report.pdf"
    if compile_pdf:
        typst = shutil.which("typst")
        if typst is None:
            return typ_path, None
        subprocess.run(
            [typst, "compile", typ_path.name, pdf_path.name],
            check=True,
            cwd=output_dir,
        )
        return typ_path, pdf_path
    return typ_path, None


def render_typst(report: LeadQualityReport) -> str:
    columns = sorted(
        report.column_profiles,
        key=lambda item: (item.invalid_count, item.missing_rate),
        reverse=True,
    )
    rows = "\n".join(_column_row(column) for column in columns)
    warnings = "\n".join(f"- {_typ_text(item)}" for item in report.warnings[:6])
    if not warnings:
        warnings = "- No blocking data quality warnings were found."
    actions = "\n".join(_action_card(action) for action in report.actions)
    if not actions:
        actions = _action_card(
            ReportAction(
                priority="Monitor",
                issue="No critical issue",
                action="Keep the normal import checks in place and monitor future exports.",
            )
        )
    sample = "\n".join(_sample_row(record) for record in report.sample_records)

    score_color = _score_color(report.quality_score)
    return f"""#set page(margin: 42pt)
#set text(font: "Arial", size: 10pt)
#set heading(numbering: none)

#let accent = rgb("#1457d9")
#let good = rgb("#11845b")
#let warn = rgb("#b86b00")
#let bad = rgb("#b42318")
#let muted = rgb("#667085")
#let panel = rgb("#f6f8fb")

#let stat(label, value, color: accent) = block[
  #rect(fill: panel, radius: 5pt, inset: 10pt, width: 100%)[
    #text(size: 8pt, fill: muted, weight: "bold")[#upper(label)]
    #linebreak()
    #text(size: 18pt, fill: color, weight: "bold")[#value]
  ]
]

#let bar(label, value, color: accent) = block[
  #text(size: 8pt, fill: muted)[#label]
  #linebreak()
  #rect(width: 100%, height: 7pt, fill: rgb("#e7ebf2"), radius: 3pt)[
    #rect(width: value * 1%, height: 7pt, fill: color, radius: 3pt)
  ]
]

= {_typ_text(report.title)}

#text(fill: muted)[
  Client-ready data hygiene summary for a CRM or spreadsheet import.
  This report shows what changed, what still needs review, and which columns
  are safe enough for automation.
]

#grid(columns: (1fr, 1fr, 1fr, 1fr), gutter: 8pt)[
  #stat("Quality score", "{report.quality_score:.1f}/100", color: {score_color})
][
  #stat("Rows cleaned", "{report.rows_before} -> {report.rows_after}")
][
  #stat("Duplicates removed", "{report.duplicates_removed}", color: warn)
][
  #stat("Invalid contacts", "{report.invalid_email_count + report.invalid_phone_count}", color: bad)
]

== Import Readiness

#bar("Overall quality", {report.quality_score:.1f}, color: {_score_color(report.quality_score)})

#grid(columns: (1fr, 1fr), gutter: 12pt)[
  === Main Warnings
  {warnings}
][
  === Recommended Actions
  {actions}
]

== Column Profile

#table(
  columns: (1.4fr, .8fr, .7fr, .8fr, .8fr, .8fr),
  inset: 5pt,
  stroke: rgb("#d0d5dd"),
  [*Column*], [*Type*], [*Confidence*], [*Missing*], [*Invalid*], [*Unique*],
{rows}
)

== Cleaned Sample

#table(
  columns: (1.1fr, 1.4fr, 1.1fr, 1.2fr),
  inset: 5pt,
  stroke: rgb("#d0d5dd"),
  [*Name*], [*Email*], [*Phone*], [*Company*],
{sample}
)

== Delivery Notes

- Spreadsheet formula prefixes are neutralized before export.
- Email and phone fields are normalized only when they pass format validation.
- Duplicate removal uses the configured key list. For this sample, the key is `email`.
- This API validates and cleans CRM import data. It does not enrich private
  contacts or verify mailbox ownership.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the sample CRM lead quality report.")
    parser.add_argument("csv", type=Path, nargs="?", default=Path("data/sample_leads.csv"))
    parser.add_argument("--out", type=Path, default=Path("outputs/sample_report"))
    parser.add_argument("--title", default="CRM Lead List Quality Report")
    parser.add_argument("--no-pdf", action="store_true")
    args = parser.parse_args()

    typ_path, pdf_path = generate_sample_report(
        args.csv,
        args.out,
        title=args.title,
        compile_pdf=not args.no_pdf,
    )
    print(f"Wrote {typ_path}")
    if pdf_path is not None:
        print(f"Wrote {pdf_path}")


def _recommended_actions(response: CsvCleanResponse) -> list[ReportAction]:
    profile = response.profile
    actions: list[ReportAction] = []
    if response.duplicates_removed:
        actions.append(
            ReportAction(
                priority="High",
                issue="Duplicate leads",
                action=(
                    "Import only deduplicated rows and keep the duplicate export "
                    "for sales ops review."
                ),
            )
        )
    if profile.invalid_email_count:
        actions.append(
            ReportAction(
                priority="High",
                issue="Invalid email values",
                action=(
                    "Route invalid email rows to manual review before email "
                    "automation or CRM sync."
                ),
            )
        )
    if profile.invalid_phone_count:
        actions.append(
            ReportAction(
                priority="Medium",
                issue="Invalid phone values",
                action=(
                    "Keep cleaned E.164 numbers and request corrected phone "
                    "values for failed rows."
                ),
            )
        )
    if profile.quality_score < 85:
        actions.append(
            ReportAction(
                priority="Medium",
                issue="Import quality below target",
                action=(
                    "Run the cleaned CSV through a staging import before updating "
                    "production CRM records."
                ),
            )
        )
    return actions[:4]


def _column_row(column: ColumnProfile) -> str:
    missing = f"{column.missing_rate:.0%}"
    confidence = f"{column.confidence:.0%}"
    return (
        f"  [{_typ_text(column.name)}],"
        f" [{_typ_text(column.inferred_type)}],"
        f" [{confidence}],"
        f" [{missing}],"
        f" [{column.invalid_count}],"
        f" [{column.unique_count}],"
    )


def _sample_row(record: dict[str, Any]) -> str:
    return (
        f"  [{_typ_text(record.get('name'))}],"
        f" [{_typ_text(record.get('email'))}],"
        f" [{_typ_text(record.get('phone'))}],"
        f" [{_typ_text(record.get('company'))}],"
    )


def _action_card(action: ReportAction) -> str:
    return (
        "#block(stroke: rgb(\"#d0d5dd\"), radius: 5pt, inset: 7pt)["
        f"#text(weight: \"bold\")[{_typ_text(action.priority)}: {_typ_text(action.issue)}]"
        "#linebreak()"
        f"#text(fill: muted)[{_typ_text(action.action)}]"
        "]"
    )


def _score_color(score: float) -> str:
    if score >= 90:
        return "good"
    if score >= 75:
        return "warn"
    return "bad"


def _typ_text(value: Any) -> str:
    text = "" if value is None else str(value)
    replacements = {
        "\\": "\\\\",
        "[": "\\[",
        "]": "\\]",
        "#": "\\#",
        "$": "\\$",
        "@": "\\@",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text
