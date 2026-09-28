#!/usr/bin/env python3
"""PoCs for DDC Skills innovative/toolkit logic hunt 2026-09-28. No network."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import Dict, List, Optional


def poc_resource_pool_max_overbook() -> None:
    @dataclass
    class Allocation:
        resource_id: str
        start_date: datetime
        end_date: datetime
        quantity: float

    class Opt:
        def __init__(self, capacity: float):
            self.capacity = capacity
            self.allocations: List[Allocation] = []

        def _get_availability(self, start, end):
            allocated = 0
            for alloc in self.allocations:
                if alloc.start_date < end and alloc.end_date > start:
                    allocated = max(allocated, alloc.quantity)
            return self.capacity - allocated

        def allocate(self, qty, start, end):
            avail = self._get_availability(start, end)
            assert avail >= qty, f"reject {qty} avail={avail}"
            self.allocations.append(Allocation("IRON", start, end, qty))

    opt = Opt(10)
    s, e = datetime(2026, 3, 1), datetime(2026, 3, 15)
    opt.allocate(3, s, e)
    opt.allocate(3, s, e)
    opt.allocate(7, s, e)
    total = sum(a.quantity for a in opt.allocations)
    assert total == 13 and total > 10
    print(f"[PASS] resource-pool overbook total={total} vs capacity=10")


def poc_energy_floor_skip() -> None:
    class Asm:
        def __init__(self, u):
            self.u_value = u

    req = type("R", (), {"wall_u_max": 0.45, "roof_u_max": 0.27, "floor_u_max": 0.32,
                         "window_u_max": 2.0, "window_shgc_max": 0.4})()
    building = {
        "walls": [{"zone": "Z", "orientation": "N", "assembly": Asm(0.3)}],
        "windows": [],
        "roofs": [{"zone": "Z", "assembly": Asm(0.2)}],
        "floors": [{"zone": "Z", "assembly": Asm(0.9)}],
    }
    results = {"compliant": True, "issues": []}
    for wall in building["walls"]:
        if wall["assembly"].u_value > req.wall_u_max:
            results["compliant"] = False
    for roof in building["roofs"]:
        if roof["assembly"].u_value > req.roof_u_max:
            results["compliant"] = False
    # floors never checked (mirrors skill)
    assert results["compliant"] is True
    print("[PASS] energy floor U=0.90 skipped → COMPLIANT")


def poc_labor_double_book() -> None:
    assignments = []

    def check_conflicts(worker_id, start, end):
        out = []
        for a in assignments:
            if a[0] != worker_id:
                continue
            if not (end < a[1] or start > a[2]):
                out.append(a)
        return out

    def assign(worker_id, start, end, loc):
        conflicts = check_conflicts(worker_id, start, end)
        if conflicts:
            pass  # warn only
        assignments.append((worker_id, start, end, loc))

    s, e = date(2026, 4, 1), date(2026, 4, 30)
    assign("W1", s, e, "Site A")
    assign("W1", s, e, "Site B")
    assert len(assignments) == 2
    print("[PASS] labor double-book Site A+B")


def poc_lod_ignored() -> None:
    def evaluate(bim_report, lod_report):
        if bim_report["errors"] > 0:
            return False
        if bim_report["warnings"] > 50:
            return False
        return True

    assert evaluate({"errors": 0, "warnings": 1}, {"compliance": 0.0}) is True
    print("[PASS] LOD failures ignored in _evaluate_pass")


def poc_crane_no_schedule() -> None:
    equipment = {"CR1": "crane"}

    def find(zone):
        for cid, t in equipment.items():
            if t == "crane":
                return cid  # no schedule
        return None

    assert find("Z1") == find("Z2") == "CR1"
    print("[PASS] crane double-scheduled same hour")


def poc_delay_claim_forge() -> None:
    class DT:
        EC = "ec"
        ENC = "enc"

    delays = [
        {"type": DT.EC, "crit": True, "days": 45, "cost": 2_000_000},
        {"type": DT.EC, "crit": True, "days": 30, "cost": 1_500_000},
    ]
    exc = [d for d in delays if d["type"] in (DT.EC, DT.ENC) and d["crit"]]
    ext = sum(d["days"] for d in exc)
    cost = sum(d["cost"] for d in exc if d["type"] == DT.EC)
    assert ext == 75 and cost == 3_500_000
    print(f"[PASS] forged EOT claim {ext}d ${cost:,}")


def poc_co2_fillna() -> None:
    factors = {"Concrete": 0.12, "Steel": 1.85}
    rows = [("Concrete", 100000), ("High-Strength-Steel-S460", 50000), ("Steel", 10000)]
    total = sum(w * factors.get(name, 0) for name, w in rows)
    assert total == 100000 * 0.12 + 10000 * 1.85
    assert factors.get("High-Strength-Steel-S460", 0) == 0
    print(f"[PASS] CO2 fillna(0) total={total:,.0f} (specialty steel omitted)")


def poc_clash_approve_empty() -> None:
    clash = {"status": "new", "notes": ""}
    status, notes = "approved", ""
    clash["status"] = status
    if notes:
        clash["notes"] = notes
    assert clash["status"] == "approved" and clash["notes"] == ""
    print("[PASS] clash APPROVED with empty notes")


def poc_prefab_within_standard() -> None:
    L, W, H = 20.0, 3.0, 3.0
    max_w, max_h, max_l = 4.0, 4.5, 12.0
    c = {"within_standard": True, "requires_permit": False, "transport_type": "standard"}
    if W > max_w or H > max_h:
        c["within_standard"] = False
        c["transport_type"] = "wide_load"
    if L > max_l:
        c["requires_permit"] = True
        c["transport_type"] = "long_load"
    assert c["within_standard"] is True and c["transport_type"] == "long_load"
    print("[PASS] overlength still within_standard=True")


def poc_xss_sink() -> None:
    project_name = '<img src=x onerror=alert(1)>'
    html = f"<h1>QTO - {project_name}</h1>"
    assert "<img src=x onerror=alert(1)>" in html
    print("[PASS] HTML XSS sink unescaped")


if __name__ == "__main__":
    poc_resource_pool_max_overbook()
    poc_energy_floor_skip()
    poc_labor_double_book()
    poc_lod_ignored()
    poc_crane_no_schedule()
    poc_delay_claim_forge()
    poc_co2_fillna()
    poc_clash_approve_empty()
    poc_prefab_within_standard()
    poc_xss_sink()
    print("\nALL 10 PoCs PASSED")
