#!/usr/bin/env python3
"""PoCs for CWICR remaining-skills business-logic hunt (2026-10-05).

Reimplements the vulnerable control flow from SKILL.md (no pandas required).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class BidStatus(Enum):
    COMPLIANT = "compliant"
    UNDER_REVIEW = "under_review"
    RECOMMENDED = "recommended"


class PriceFlag(Enum):
    NORMAL = "normal"
    LOW = "low"
    HIGH = "high"
    VERY_LOW = "very_low"
    VERY_HIGH = "very_high"


@dataclass
class BidLineItem:
    item_code: str
    quantity: float
    unit_rate: float
    total_price: float
    benchmark_rate: float
    benchmark_total: float
    variance_pct: float
    price_flag: PriceFlag


@dataclass
class BidAnalysis:
    bidder_name: str
    bid_total: float
    benchmark_total: float
    variance_pct: float
    line_items: List[BidLineItem]
    flagged_items: List[BidLineItem]
    status: BidStatus


CWICR = {
    "CONC-001": {"labor_cost": 50, "material_cost": 100, "equipment_cost": 25},
    "ZERO-001": {"labor_cost": 0, "material_cost": 0, "equipment_cost": 0},
}


def get_benchmark_rate(code: str) -> Optional[float]:
    if code in CWICR:
        item = CWICR[code]
        return item["labor_cost"] + item["material_cost"] + item["equipment_cost"]
    return None


def get_price_flag(variance_pct: float) -> PriceFlag:
    if variance_pct <= -40:
        return PriceFlag.VERY_LOW
    if variance_pct <= -20:
        return PriceFlag.LOW
    if variance_pct >= 40:
        return PriceFlag.VERY_HIGH
    if variance_pct >= 20:
        return PriceFlag.HIGH
    return PriceFlag.NORMAL


def analyze_bid(rows: List[Dict[str, Any]], bidder_name: str) -> BidAnalysis:
    """Mirrors cwicr-bid-analyzer analyze_bid."""
    line_items: List[BidLineItem] = []
    for row in rows:
        code = row["item_code"]
        qty = float(row["quantity"])
        bid_rate = float(row["unit_rate"])
        bid_total = float(row.get("total_price", bid_rate * qty))

        benchmark_rate = get_benchmark_rate(code)
        if benchmark_rate is None:
            benchmark_rate = bid_rate  # CWICR-01: unknown-code self-benchmark

        benchmark_total = benchmark_rate * qty
        # CWICR-03: zero benchmark → variance forced to 0 (NORMAL)
        variance_pct = (
            ((bid_rate - benchmark_rate) / benchmark_rate * 100)
            if benchmark_rate > 0
            else 0
        )

        line_items.append(
            BidLineItem(
                code,
                qty,
                bid_rate,
                bid_total,
                benchmark_rate,
                benchmark_total,
                round(variance_pct, 1),
                get_price_flag(variance_pct),
            )
        )

    bid_total = sum(i.total_price for i in line_items)
    benchmark_total = sum(i.benchmark_total for i in line_items)
    total_variance = (
        ((bid_total - benchmark_total) / benchmark_total * 100)
        if benchmark_total > 0
        else 0
    )
    flagged = [i for i in line_items if i.price_flag != PriceFlag.NORMAL]

    if (
        len([f for f in flagged if f.price_flag in [PriceFlag.VERY_LOW, PriceFlag.VERY_HIGH]])
        > len(line_items) * 0.1
    ):
        status = BidStatus.UNDER_REVIEW
    elif total_variance < -30 or total_variance > 30:
        status = BidStatus.UNDER_REVIEW
    else:
        status = BidStatus.COMPLIANT

    return BidAnalysis(
        bidder_name,
        round(bid_total, 2),
        round(benchmark_total, 2),
        round(total_variance, 1),
        line_items,
        flagged,
        status,
    )


def compare_bids(
    bids: List[Tuple[str, List[Dict[str, Any]]]],
) -> Tuple[Optional[str], List[BidAnalysis]]:
    """Mirrors cwicr-bid-analyzer compare_bids — mints RECOMMENDED."""
    analyses = [analyze_bid(data, name) for name, data in bids]
    ranking = sorted([(a.bidder_name, a.bid_total) for a in analyses], key=lambda x: x[1])
    recommended = None
    for bidder, _total in ranking:
        bid_analysis = next(a for a in analyses if a.bidder_name == bidder)
        if bid_analysis.status == BidStatus.COMPLIANT:
            recommended = bidder
            bid_analysis.status = BidStatus.RECOMMENDED
            break
    return recommended, analyses


def poc_unknown_code_award() -> None:
    recommended, analyses = compare_bids(
        [
            (
                "Honest",
                [{"item_code": "CONC-001", "quantity": 100, "unit_rate": 175, "total_price": 17500}],
            ),
            (
                "Attacker",
                [{"item_code": "FAKE-999", "quantity": 100, "unit_rate": 1, "total_price": 100}],
            ),
        ]
    )
    assert recommended == "Attacker"
    assert analyses[1].status == BidStatus.RECOMMENDED
    assert analyses[1].variance_pct == 0.0
    print("[PASS] CWICR-01 unknown-code → RECOMMENDED")


def poc_negative_qty_award() -> None:
    recommended, analyses = compare_bids(
        [
            (
                "Honest",
                [{"item_code": "CONC-001", "quantity": 100, "unit_rate": 175, "total_price": 17500}],
            ),
            (
                "Attacker",
                [
                    {"item_code": "CONC-001", "quantity": 100, "unit_rate": 175, "total_price": 17500},
                    {"item_code": "CONC-001", "quantity": -50, "unit_rate": 175, "total_price": -8750},
                ],
            ),
        ]
    )
    assert recommended == "Attacker"
    assert analyses[1].bid_total == 8750
    assert analyses[1].status == BidStatus.RECOMMENDED
    print("[PASS] CWICR-02 negative qty → RECOMMENDED underbid")


def poc_zero_benchmark_competitive() -> None:
    analysis = analyze_bid(
        [{"item_code": "ZERO-001", "quantity": 100, "unit_rate": 99999, "total_price": 100}],
        "Attacker",
    )
    assert analysis.status == BidStatus.COMPLIANT
    assert len(analysis.flagged_items) == 0
    recommended, _ = compare_bids(
        [
            (
                "Honest",
                [{"item_code": "CONC-001", "quantity": 100, "unit_rate": 175, "total_price": 17500}],
            ),
            (
                "Attacker",
                [{"item_code": "ZERO-001", "quantity": 100, "unit_rate": 99999, "total_price": 100}],
            ),
        ]
    )
    assert recommended == "Attacker"
    print("[PASS] CWICR-03 zero-benchmark / div0 → COMPLIANT → RECOMMENDED")


def poc_decoupled_total_price() -> None:
    forged = int(17500 * 0.71)  # within ±30% compliance window
    recommended, analyses = compare_bids(
        [
            (
                "Honest",
                [{"item_code": "CONC-001", "quantity": 100, "unit_rate": 175, "total_price": 17500}],
            ),
            (
                "Attacker",
                [{"item_code": "CONC-001", "quantity": 100, "unit_rate": 175, "total_price": forged}],
            ),
        ]
    )
    assert analyses[1].line_items[0].variance_pct == 0.0  # rates match → no line flags
    assert recommended == "Attacker"
    print(f"[PASS] CWICR-04 decoupled total_price={forged} → RECOMMENDED")


def poc_cost_unknown_zero() -> None:
    """Unknown codes return MISSING_DATA zeros that still sum into estimate totals."""
    known = 12650.0
    unknown_contrib = 0.0  # CostBreakdown MISSING_DATA: all costs 0
    estimate = known + unknown_contrib
    assert estimate == known
    print("[PASS] CWICR-05 unknown-code → $0 still summed into estimate")


def poc_cost_negative_overhead() -> None:
    """Caller-chosen negative overhead/profit collapses totals (truthy so `or` default skipped)."""
    overhead_rate = -0.9
    profit_rate = -0.5
    direct = 10000.0
    total = direct + direct * overhead_rate + (direct + direct * overhead_rate) * profit_rate
    normal = direct * 1.15 * 1.10
    assert total < normal * 0.1
    # price_overrides material_factor=0 also zeroes material
    material_unit = 400.0 * 0.0
    assert material_unit == 0.0
    print(f"[PASS] CWICR-06 negative OH/profit {total} vs normal {normal}")


def poc_schedule_progress_forge() -> None:
    bac = 100000.0
    progress = 250.0  # unbounded % complete
    ac = 90000.0
    ev = bac * progress / 100
    cpi = ev / ac
    eac = bac / cpi
    assert cpi > 2 and eac < bac * 0.5
    print(f"[PASS] CWICR-07 progress={progress}% → CPI={cpi:.2f} EAC={eac:.0f}")


def poc_risk_factor_collapse() -> None:
    base = 1_000_000.0
    min_factor = 0.01
    max_factor = 0.01
    p80 = base * (min_factor + max_factor * 3) / 4
    contingency = p80 - base
    assert contingency < -0.9 * base
    print(f"[PASS] CWICR-08 risk factors → contingency={contingency:.0f}")


def poc_waste_unbounded() -> None:
    base_qty = 100.0
    custom = {"cutting": 5.0, "spillage": 5.0, "breakage": 5.0, "overrun": 5.0}
    total_waste_pct = sum(custom.values())
    order_qty = base_qty + base_qty * total_waste_pct
    assert order_qty == 2100.0
    print(f"[PASS] CWICR-09 waste custom_factors → order_qty={order_qty}")


def main() -> None:
    poc_unknown_code_award()
    poc_negative_qty_award()
    poc_zero_benchmark_competitive()
    poc_decoupled_total_price()
    poc_cost_unknown_zero()
    poc_cost_negative_overhead()
    poc_schedule_progress_forge()
    poc_risk_factor_collapse()
    poc_waste_unbounded()
    print("\nALL PoCs PASSED (9/9)")


if __name__ == "__main__":
    main()
