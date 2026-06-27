from __future__ import annotations

import json
from pathlib import Path

from data_quality_api.api import app


def main() -> None:
    output_path = Path("docs/openapi.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(app.openapi(), indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
