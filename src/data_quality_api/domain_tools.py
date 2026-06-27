from __future__ import annotations

import re
from urllib.parse import urlparse

from data_quality_api.models import DomainParseResponse, DomainParseResult

DOMAIN_RE = re.compile(r"^(?!-)[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def parse_domains(values: list[str]) -> DomainParseResponse:
    results = [_parse_domain(value) for value in values]
    return DomainParseResponse(total=len(results), results=results)


def _parse_domain(value: str) -> DomainParseResult:
    raw = value.strip()
    if "@" in raw:
        domain = raw.rsplit("@", 1)[-1].lower()
        return DomainParseResult(
            input=value,
            domain=domain,
            source="email",
            valid_shape=bool(DOMAIN_RE.match(domain)),
        )
    if raw.startswith(("http://", "https://")):
        parsed = urlparse(raw)
        domain = parsed.netloc.lower().removeprefix("www.")
        return DomainParseResult(
            input=value,
            domain=domain or None,
            source="url",
            valid_shape=bool(domain and DOMAIN_RE.match(domain)),
        )
    domain = raw.lower().removeprefix("www.")
    if DOMAIN_RE.match(domain):
        return DomainParseResult(input=value, domain=domain, source="domain", valid_shape=True)
    return DomainParseResult(input=value, domain=None, source="unknown", valid_shape=False)
