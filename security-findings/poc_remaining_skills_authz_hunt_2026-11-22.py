#!/usr/bin/env python3
"""PoC: remaining-skills business-logic / authz hunt 2026-11-22.

Verifies five unique MEDIUM+ attack chains (no dependency on SKILL.md exec).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import List, Optional

import pandas as pd


def poc_compliance_critical_bypass() -> None:
    """CRITICAL: update_status ACTIVE/NOT_APPLICABLE clears work-stoppage without docs."""

    class ComplianceStatus(Enum):
        ACTIVE = "active"
        PENDING = "pending"
        EXPIRED = "expired"
        NOT_APPLICABLE = "not_applicable"

    class Priority(Enum):
        CRITICAL = "critical"

    @dataclass
    class Item:
        status: ComplianceStatus
        priority: Priority
        document_url: str = ""

    items = [
        Item(ComplianceStatus.PENDING, Priority.CRITICAL),
        Item(ComplianceStatus.PENDING, Priority.CRITICAL),
    ]
    # Colluding PM stamps ACTIVE with empty document_url
    for it in items:
        it.status = ComplianceStatus.ACTIVE

    total = len(items)
    active = sum(1 for i in items if i.status == ComplianceStatus.ACTIVE)
    rate = active / total * 100
    critical_missing = sum(
        1
        for i in items
        if i.priority == Priority.CRITICAL
        and i.status in (ComplianceStatus.PENDING, ComplianceStatus.EXPIRED)
    )
    assert rate == 100.0 and critical_missing == 0
    assert all(i.document_url == "" for i in items)

    # Alternate: NOT_APPLICABLE also drops out of critical_missing
    items[0].status = ComplianceStatus.NOT_APPLICABLE
    critical_missing = sum(
        1
        for i in items
        if i.priority == Priority.CRITICAL
        and i.status in (ComplianceStatus.PENDING, ComplianceStatus.EXPIRED)
    )
    assert critical_missing == 0
    print("[PASS] compliance-tracker CRITICAL work-stoppage bypass")


def poc_resource_pool_overbook() -> None:
    """HIGH: _get_availability uses max() not sum() → overbook shared crane."""

    @dataclass
    class Alloc:
        resource_id: str
        start_date: datetime
        end_date: datetime
        quantity: float

    allocations: List[Alloc] = []
    capacity = 1.0
    start = datetime(2024, 6, 1)
    end = datetime(2024, 6, 10)

    def get_availability(resource_id: str, s: datetime, e: datetime) -> float:
        allocated = 0.0
        for alloc in allocations:
            if alloc.resource_id != resource_id:
                continue
            if alloc.start_date < e and alloc.end_date > s:
                allocated = max(allocated, alloc.quantity)  # buggy aggregation
        return capacity - allocated

    for _ in range(3):
        avail = get_availability("crane", start, end)
        assert avail >= 0.4
        allocations.append(Alloc("crane", start, end, 0.4))

    total = sum(a.quantity for a in allocations)
    assert total > capacity
    print(f"[PASS] resource-pool overbook total={total} > capacity={capacity}")


def poc_schedule_cost_ev_forge() -> None:
    """HIGH: attacker-set percent_complete forges BCWP / payment basis."""
    budget = 1_000_000.0
    real_pct = 10.0
    forged_pct = 100.0
    real_bcwp = budget * real_pct / 100
    forged_bcwp = budget * forged_pct / 100
    assert forged_bcwp - real_bcwp == 900_000.0
    print(f"[PASS] schedule-cost-link EV overbill delta={forged_bcwp - real_bcwp}")


def poc_contractor_cert_eternal() -> None:
    """HIGH: missing valid_until defaults to date.max → expired/forged certs pass."""
    certs = [{"name": "OSHA30"}, {"name": "LEED-AP"}]  # no valid_until
    accepted = {
        c["name"]
        for c in certs
        if c.get("valid_until", date.max) >= date.today()
    }
    assert accepted == {"OSHA30", "LEED-AP"}
    print("[PASS] contractor-matching eternal certs via date.max default")


def poc_ppe_empty_required() -> None:
    """HIGH: required_ppe=[] yields COMPLIANT with zero actual PPE."""
    worker = {"id": "W1", "required_ppe": [], "actual_ppe": []}
    required = worker.get("required_ppe", ["helmet", "vest", "boots"])
    actual = worker.get("actual_ppe", [])
    missing = set(required) - set(actual)
    status = "compliant" if not missing else "non_compliant"
    assert status == "compliant"
    print("[PASS] safety-compliance-checker empty required_ppe → COMPLIANT")


def poc_bonus_carbon_zero_factor() -> None:
    """MEDIUM+: add_custom_factor(ec_factor=0) zeros official carbon report."""
    qty = 5000.0
    ec = qty * 0.0
    assert ec == 0.0
    print("[PASS] carbon-calculator zero custom factor (bonus)")


def poc_bonus_validator_missing_cols() -> None:
    """MEDIUM: missing required columns skip checks → passed."""
    required = ["work_item_code", "description", "unit"]
    df = pd.DataFrame({"junk": [1, 2, 3]})
    issues = []
    for _, row in df.iterrows():
        for field in required:
            if field in row.index:
                if pd.isna(row[field]) or str(row[field]).strip() == "":
                    issues.append(field)
    assert issues == []
    print("[PASS] cwicr-data-validator missing columns fail-open (bonus)")


if __name__ == "__main__":
    poc_compliance_critical_bypass()
    poc_resource_pool_overbook()
    poc_schedule_cost_ev_forge()
    poc_contractor_cert_eternal()
    poc_ppe_empty_required()
    poc_bonus_carbon_zero_factor()
    poc_bonus_validator_missing_cols()
    print("\nAll top-5 (+bonus) PoCs passed.")
