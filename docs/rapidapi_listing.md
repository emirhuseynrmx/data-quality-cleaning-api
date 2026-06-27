# RapidAPI Listing Draft

## API Name

Data Quality & CSV Cleaning API

## Tagline

Clean CSV/JSON records, normalize emails and phones, detect duplicates, infer column types, and generate data quality reports.

## Long Description

This API helps developers clean small business datasets before CRM imports, spreadsheet workflows, dashboards, lead routing, and analytics jobs.

It accepts CSV text or JSON records and returns cleaned records, duplicate counts, inferred column types, missing-value rates, warnings, and a quality score.

It is built for practical data hygiene, not enrichment. It does not scrape third-party sites, does not require account credentials, and does not call an LLM.

## Endpoints

- `POST /v1/email/normalize`
- `POST /v1/phone/normalize`
- `POST /v1/domain/parse`
- `POST /v1/csv/profile`
- `POST /v1/csv/clean`
- `POST /v1/records/clean`

## Best Customers

- CRM tools
- lead generation workflows
- spreadsheet automation tools
- no-code automation builders
- data cleaning freelancers
- small SaaS dashboards

## Suggested Pricing

- Basic/free test: 100 requests/month
- Pro: $19/month, 10k requests
- Ultra: $49/month, 75k requests
- Mega: $99/month, 300k requests

Start with the free test tier enabled so developers can verify request/response shape before paying.

## Boundaries

This API validates and normalizes data shape. It does not guarantee email deliverability and does not enrich private contact data.
