#!/usr/bin/env python3
"""PoC: failed mandatory prequal mins still enter get_qualified() via CONDITIONALLY_QUALIFIED.

Extracts the implementation block from
1_DDC_Toolkit/Procurement/subcontractor-prequalification/SKILL.md

Requires: pip install pandas
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "1_DDC_Toolkit/Procurement/subcontractor-prequalification/SKILL.md"


def extract_python(skill_path: Path) -> str:
    text = skill_path.read_text()
    blocks = re.findall(r"```python\n(.*?)```", text, re.S)
    return "\n\n".join(b for b in blocks if "class " in b and "def " in b)


def main() -> int:
    ns: dict = {}
    exec(extract_python(SKILL), ns)  # noqa: S102 — template under test

    pq = ns["SubcontractorPrequalification"]("Tower")
    app = pq.add_application(
        "Risk Sub", "Electrical", "a@b.com", 2, 100_000, 0, 2.5
    )
    # Insurance/Bonding min_score is 7; score 0 fails the gate. Pad others to total=50.
    pq.score_application(
        app.app_id,
        {
            "Safety Record": 10,
            "Financial Stability": 10,
            "Experience": 10,
            "References": 10,
            "Capacity": 10,
            "Insurance/Bonding": 0,
        },
    )
    qual = pq.get_qualified("Electrical")
    assert app.total_score == 50
    assert app.status.value == "conditionally_qualified", app.status.value
    assert any(a.app_id == app.app_id for a in qual), "failed-min app must not be in get_qualified"

    # Control: failed Insurance min and total < 50 → NOT_QUALIFIED, excluded
    app2 = pq.add_application("Low Sub", "Electrical", "c@d.com", 1, 1, 0, 3.0)
    pq.score_application(
        app2.app_id,
        {
            "Safety Record": 6,
            "Financial Stability": 5,
            "Experience": 6,
            "References": 5,
            "Capacity": 5,
            "Insurance/Bonding": 0,
        },
    )
    assert app2.total_score == 27
    assert app2.status.value == "not_qualified"
    assert not any(a.app_id == app2.app_id for a in pq.get_qualified("Electrical"))

    out = {
        "prequal_failed_min_still_get_qualified": "PASS",
        "status": app.status.value,
        "total_score": app.total_score,
        "in_get_qualified": True,
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
