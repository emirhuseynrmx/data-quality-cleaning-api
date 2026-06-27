# Data Quality Cleaning API

[![CI](https://github.com/emirhuseynrmx/data-quality-cleaning-api/actions/workflows/ci.yml/badge.svg)](https://github.com/emirhuseynrmx/data-quality-cleaning-api/actions)
[![Python](https://img.shields.io/badge/python-3.10--3.12-blue)](https://www.python.org/)

FastAPI service for cleaning and profiling small CSV/JSON datasets before they go into a CRM, spreadsheet, dashboard, lead workflow, or import job.

This is designed as a RapidAPI-style utility: stateless, cheap to run, no LLM cost, no external data provider, no account credentials.

## Endpoints

```text
GET  /health
POST /v1/email/normalize
POST /v1/phone/normalize
POST /v1/domain/parse
POST /v1/csv/profile
POST /v1/csv/clean
POST /v1/records/clean
```

## Use Cases

- clean lead lists before CRM import
- normalize email and phone fields
- profile CSV files before analytics work
- remove duplicate records by selected keys
- get missing-value and type summaries
- return cleaned CSV from messy user uploads

## Run

```bash
pip install -e ".[dev]"
uvicorn data_quality_api.api:app --reload
```

Docker:

```bash
docker build -t data-quality-api .
docker run --rm -p 8000:8000 data-quality-api
```

Export OpenAPI for RapidAPI import:

```bash
python scripts/export_openapi.py
```

## Example

```bash
curl -X POST http://localhost:8000/v1/records/clean \
  -H "Content-Type: application/json" \
  -d @examples/records_clean_request.json
```

Sample output: [examples/records_clean_response.json](examples/records_clean_response.json)

## Response Shape

`/v1/records/clean` returns:

- cleaned records
- duplicate count
- row/column count
- inferred column types
- missing-value rates
- quality score
- warnings

## RapidAPI Positioning

Suggested title:

```text
Data Quality & CSV Cleaning API
```

Suggested short description:

```text
Clean CSV/JSON records, normalize emails and phones, detect duplicates, infer column types, and generate data quality reports.
```

Suggested pricing:

- Basic/free test: 100 requests/month
- Pro: $19/month, 10k requests
- Ultra: $49/month, 75k requests
- Mega: $99/month, 300k requests

## Limits

- max CSV size: 1 MB
- max JSON records per request: 5,000
- max email/phone/domain batch size: 2,000

This API does not verify email inbox deliverability. It validates and normalizes format-level data for import and reporting workflows.
