#!/usr/bin/env python3
"""PoC: DDC Skills money/authZ hunt 2026-10-31

Validates:
1) payment-application-generator — materials presently-stored folded into work previous
2) payment-application-generator — previous_certificates sums cumulative earned (G702 underpay)
3) payment-application-processor (curated) — same materials fold into previous_completed
4) cwicr-quantity-matcher — unknown BIM↔CWICR units convert at 1.0 → cost-linked QTO overbill

Non-destructive: executes extracted SKILL.md Python only.
"""
from __future__ import annotations

import re
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def extract_python(skill_rel: str, predicate) -> str:
    text = (ROOT / skill_rel).read_text(encoding="utf-8")
    blocks = re.findall(r"```python\n(.*?)```", text, re.S)
    for b in blocks:
        if predicate(b):
            return b
    raise RuntimeError(f"no matching python block in {skill_rel}")


def test_paygen_materials_double_count() -> None:
    code = extract_python(
        "1_DDC_Toolkit/Cost-Management/payment-application-generator/SKILL.md",
        lambda b: "class PaymentApplicationGenerator" in b,
    )
    ns: dict = {}
    exec(code, ns)
    G = ns["PaymentApplicationGenerator"]
    g = G("Tower", "GC", "Owner", 1_000_000, retainage=0.10)
    g.setup_sov([{"number": "01", "description": "Concrete", "value": 500_000}])

    g.create_application(date(2024, 1, 1), date(2024, 1, 31), {"01": {"work": 100_000, "materials": 50_000}})
    app2 = g.create_application(
        date(2024, 2, 1), date(2024, 2, 29), {"01": {"work": 0, "materials": 50_000}}
    )
    due2 = g.calculate_payment_due(app2)["current_payment_due"]
    item = app2.items[0]

    assert item.work_completed_previous == 150_000, item.work_completed_previous
    assert item.materials_stored_previous == 0, item.materials_stored_previous
    assert app2.total_completed_to_date == 200_000, app2.total_completed_to_date
    assert due2 == 45_000.0, due2
    print(
        "[PASS] paygen materials fold: honest 150k → billed 200k; app2 due +45k "
        f"(wp={item.work_completed_previous}, mc={item.materials_stored_current})"
    )


def test_paygen_previous_certificates_sum() -> None:
    code = extract_python(
        "1_DDC_Toolkit/Cost-Management/payment-application-generator/SKILL.md",
        lambda b: "class PaymentApplicationGenerator" in b,
    )
    ns: dict = {}
    exec(code, ns)
    G = ns["PaymentApplicationGenerator"]
    g = G("Tower", "GC", "Owner", 1_000_000, retainage=0.10)
    g.setup_sov([{"number": "01", "description": "Concrete", "value": 500_000}])

    dues = []
    for i, work in enumerate([100_000, 50_000, 50_000, 50_000], start=1):
        app = g.create_application(date(2024, i, 1), date(2024, i, 28), {"01": {"work": work}})
        g702 = g.generate_g702(app)
        dues.append(g702["current_payment_due"])

    assert dues[0] == 90_000.0, dues
    assert dues[1] == 45_000.0, dues
    assert dues[2] == -45_000.0, dues
    assert dues[3] == -180_000.0, dues
    print(
        "[PASS] paygen previous_certificates SUM of cumulative earned → "
        f"G702 dues {dues} (honest would be [90000, 45000, 45000, 45000])"
    )


def test_curated_payproc_materials_fold() -> None:
    code = extract_python(
        "4_DDC_Curated/Financial-Management/payment-application-processor/SKILL.md",
        lambda b: "class PaymentApplicationProcessor" in b,
    )
    ns: dict = {}
    exec(code, ns)
    P = ns["PaymentApplicationProcessor"]
    p = P("Tower", "GC", 1_000_000)
    p.import_sov([{"number": "01", "description": "Concrete", "value": 500_000}])
    p.create_pay_app(datetime(2024, 1, 1), datetime(2024, 1, 31))
    p.update_line_item(1, "01", current_completed=100_000, materials_stored=50_000)
    p.create_pay_app(datetime(2024, 2, 1), datetime(2024, 2, 28))
    prev = next(i for i in p.pay_apps[2].line_items if i.number == "01").previous_completed
    p.update_line_item(2, "01", current_completed=0, materials_stored=50_000)
    total2 = p.pay_apps[2].total_completed
    net2 = p.pay_apps[2].net_amount_due

    assert prev == 150_000.0, prev
    assert total2 == 200_000.0, total2
    assert net2 == 45_000.0, net2
    print(
        f"[PASS] curated payproc materials fold: prev_completed={prev} "
        f"total={total2} net_due={net2} (honest total 150k)"
    )


def test_quantity_matcher_unit_failopen() -> None:
    import pandas as pd

    code = extract_python(
        "1_DDC_Toolkit/CWICR-Database/cwicr-quantity-matcher/SKILL.md",
        lambda b: "class CWICRQuantityMatcher" in b,
    )
    preamble = (
        "from dataclasses import dataclass, field\n"
        "from typing import *\n"
        "from enum import Enum\n"
        "import re\n"
        "from difflib import SequenceMatcher\n"
        "import pandas as pd\n"
    )
    ns: dict = {}
    exec(preamble + code, ns)
    M = ns["CWICRQuantityMatcher"]
    MR = ns["MatchingResult"]

    cwicr = pd.DataFrame(
        [
            {
                "work_item_code": "PIPE-001",
                "description": "Copper pipe installation",
                "unit": "m",
                "labor_cost": 40,
                "material_cost": 20,
                "equipment_cost": 5,
            }
        ]
    )
    m = M(cwicr)
    assert m._get_unit_conversion("sf", "m2") == 0.092903
    assert m._get_unit_conversion("mm", "m") == 1.0
    assert m._get_unit_conversion("m3", "m2") == 1.0

    el = {
        "ElementId": "1",
        "Category": "pipes",
        "Description": "Copper pipe installation",
        "Quantity": 12_000,
        "Unit": "mm",
    }
    match = m.match_element(el)
    assert match is not None
    assert match.unit_conversion_factor == 1.0
    result = MR(1, 1, 0, 1, 0, [match], [])
    qto = m.generate_cost_linked_qto(result)
    total = float(qto["Total Cost"].sum())
    assert total == 780_000.0, total
    print(
        f"[PASS] quantity-matcher mm→m factor=1.0 → Total Cost ${total:,.0f} "
        f"(correct 12m×$65=${12*65:,.0f}; 1000× overbill)"
    )


def main() -> int:
    tests = [
        test_paygen_materials_double_count,
        test_paygen_previous_certificates_sum,
        test_curated_payproc_materials_fold,
        test_quantity_matcher_unit_failopen,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as e:
            failed += 1
            print(f"[FAIL] {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
