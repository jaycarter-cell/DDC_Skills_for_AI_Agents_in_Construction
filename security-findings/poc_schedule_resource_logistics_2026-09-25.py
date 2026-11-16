#!/usr/bin/env python3
"""Non-destructive PoCs for schedule/resource/logistics logic flaws (hunt 2026-09-25)."""
from __future__ import annotations

import re
import sys
import types
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]


def extract_python(path: Path) -> str:
    text = path.read_text()
    blocks = re.findall(r"```python\n(.*?)```", text, re.S)
    blocks.sort(key=lambda b: b.count("class "), reverse=True)
    return blocks[0]


def exec_skill(rel: str):
    code = extract_python(ROOT / rel)
    for m in (
        "# Example Usage",
        "# Example",
        "\ntracker =",
        "\nscheduler =",
        "\npunch =",
        "\nchecklist =",
        "\nfleet =",
        "\nassignment =",
    ):
        if m in code:
            code = code.split(m)[0]
            break
    ns: Dict[str, Any] = {}
    exec(compile(code, rel, "exec"), ns)
    return ns


def poc_as_built():
    ns = exec_skill("1_DDC_Toolkit/Closeout/as-built-tracker/SKILL.md")
    t = ns["AsBuiltTracker"]("Tower", handover_date=date.today() + timedelta(days=30))
    doc = t.add_document(
        "AB-001",
        "Structural As-Builts",
        ns["DocumentType"].STRUCTURAL,
        "Structural",
        "Steel Co",
    )
    assert doc.status == ns["DocumentStatus"].NOT_STARTED
    t.review_submission(doc.document_id, approved=True, reviewer="colluding-agent")
    summary = t.get_summary()
    assert t.documents[doc.document_id].status == ns["DocumentStatus"].APPROVED
    assert len(t.submissions) == 0
    assert summary["completion_rate"] == 100.0
    print("[PASS] as-built approve-without-submit:", summary)


def poc_look_ahead_weekly_and_forge():
    ns = exec_skill(
        "3_DDC_Insights/Schedule-Optimization/look-ahead-scheduler/SKILL.md"
    )
    start = datetime(2026, 9, 28)
    sched = ns["LookAheadScheduler"]("Tower")
    sched.import_from_master(
        [
            {
                "id": "FOUND",
                "name": "Foundation",
                "trade": "concrete",
                "location": "L1",
                "planned_start": start,
                "planned_finish": start + timedelta(days=10),
                "duration": 10,
                "labor_hours": 80,
                "crew_size": 8,
                "predecessors": [],
            },
            {
                "id": "STEEL",
                "name": "Steel Erection",
                "trade": "ironworker",
                "location": "L1",
                "planned_start": start + timedelta(days=5),
                "planned_finish": start + timedelta(days=20),
                "duration": 15,
                "labor_hours": 120,
                "crew_size": 10,
                "predecessors": ["FOUND"],
            },
        ],
        start,
        6,
    )
    sched.add_constraint(
        "STEEL",
        ns["ConstraintType"].INSPECTION,
        "Special inspection footing hold",
        "BO",
        start + timedelta(days=5),
    )
    ready = sched.analyze_make_ready()
    assert "STEEL" in ready["blocked"]
    week = sched.generate_weekly_plan(start)
    assert any(a.id == "STEEL" for a in week.activities)
    daily = sched.generate_daily_plan(start + timedelta(days=5))
    assert not any(a.id == "STEEL" for a in daily.activities)
    print("[PASS] weekly includes blocked STEEL; daily excludes it")

    # Forge inspection on a no-pred activity
    sched2 = ns["LookAheadScheduler"]("T2")
    sched2.import_from_master(
        [
            {
                "id": "STEEL",
                "name": "Steel Erection",
                "trade": "ironworker",
                "location": "L2",
                "planned_start": start,
                "planned_finish": start + timedelta(days=5),
                "duration": 5,
                "labor_hours": 40,
                "crew_size": 6,
                "predecessors": [],
            }
        ],
        start,
        3,
    )
    c = sched2.add_constraint(
        "STEEL", ns["ConstraintType"].INSPECTION, "Hold", "AHJ", start
    )
    assert "STEEL" in sched2.analyze_make_ready()["not_ready"]
    sched2.update_constraint(c.id, ns["ConstraintStatus"].RESOLVED, notes="forged clear")
    assert "STEEL" in sched2.analyze_make_ready()["ready"]
    d2 = sched2.generate_daily_plan(start)
    assert any(a.id == "STEEL" for a in d2.activities)
    print("[PASS] forged INSPECTION RESOLVED → daily STEEL")

    # Crew over-allocation
    sched3 = ns["LookAheadScheduler"]("T3")
    acts = [
        {
            "id": f"S{i}",
            "name": f"Steel Pick {i}",
            "trade": "ironworker",
            "location": f"L{i}",
            "planned_start": start,
            "planned_finish": start + timedelta(days=1),
            "duration": 1,
            "labor_hours": 80,
            "crew_size": 10,
            "predecessors": [],
        }
        for i in range(5)
    ]
    sched3.import_from_master(acts, start, 2)
    sched3.analyze_make_ready()
    d3 = sched3.generate_daily_plan(start)
    assert d3.labor_by_trade["ironworker"] == 50
    print("[PASS] daily labor_by_trade ironworker=50 with no capacity gate")


def poc_punch_forge_complete():
    ns = exec_skill("1_DDC_Toolkit/Project-Closeout/punch-list-manager/SKILL.md")
    punch = ns["PunchListManager"](
        "Tower", target_closeout_date=date.today() + timedelta(days=14)
    )
    item = punch.add_item(
        location="Shaft Floor 12",
        description="Missing firestopping - life safety",
        category=ns["PunchItemCategory"].FIRE_PROTECTION,
        priority=ns["PunchItemPriority"].CRITICAL,
        assigned_to="ABC Fire",
        due_date=date.today() - timedelta(days=5),
    )
    punch.update_status(item.item_id, ns["PunchItemStatus"].VERIFIED, verified_by="")
    forecast = punch.forecast_completion()
    summary = punch.get_summary()
    assert forecast["status"] == "COMPLETE" and forecast["on_track"] is True
    assert summary.completion_rate == 100.0 and summary.overdue_count == 0
    print("[PASS] punch forge VERIFIED → forecast COMPLETE:", forecast)


def poc_storage_restrictions():
    import numpy as np

    scipy = types.ModuleType("scipy")
    optimize = types.ModuleType("scipy.optimize")
    optimize.linear_sum_assignment = lambda cost: (
        np.arange(cost.shape[0]),
        np.arange(min(cost.shape)),
    )
    optimize.minimize = lambda *a, **k: types.SimpleNamespace(x=[0.0, 0.0])
    scipy.optimize = optimize
    sys.modules["scipy"] = scipy
    sys.modules["scipy.optimize"] = optimize

    text = (ROOT / "5_DDC_Innovative/site-logistics-optimization/SKILL.md").read_text()
    blocks = re.findall(r"```python\n(.*?)```", text, re.S)
    model_block = [b for b in blocks if "class SiteLogisticsModel" in b][0]
    storage_block = [b for b in blocks if "class StorageOptimizer" in b][0]
    ns: Dict[str, Any] = {"np": np, "numpy": np}
    exec(compile(model_block, "model", "exec"), ns)
    exec(compile(storage_block, "storage", "exec"), ns)
    SiteZone, ZoneType = ns["SiteZone"], ns["ZoneType"]
    site = ns["SiteLogisticsModel"]("Jobsite")
    site.add_zone(
        SiteZone(
            "STOR1",
            ZoneType.STORAGE,
            area_sqm=200,
            capacity=100.0,
            position=(0.0, 0.0),
            restrictions=["flammable", "hazmat"],
        )
    )
    site.add_zone(
        SiteZone(
            "STOR2",
            ZoneType.STORAGE,
            area_sqm=100,
            capacity=20.0,
            position=(100.0, 0.0),
            restrictions=[],
        )
    )
    site.add_zone(
        SiteZone(
            "PAD",
            ZoneType.CONSTRUCTION,
            area_sqm=500,
            capacity=0.0,
            position=(1.0, 0.0),
        )
    )
    opt = ns["StorageOptimizer"](site)
    alloc1 = opt.allocate_storage(
        [
            {
                "material_id": "M1",
                "material_type": "flammable",
                "quantity": 30,
                "destination_zone": "PAD",
                "arrival_date": date.today(),
            },
            {
                "material_id": "M2",
                "material_type": "flammable",
                "quantity": 40,
                "destination_zone": "PAD",
                "arrival_date": date.today(),
            },
        ]
    )
    util = opt.get_storage_utilization()
    assert alloc1["M1"] == "STOR1" and util["STOR1"]["used"] == 0
    alloc2 = opt.allocate_storage(
        [
            {
                "material_id": "M3",
                "material_type": "steel",
                "quantity": 90,
                "destination_zone": "PAD",
                "arrival_date": date.today(),
            }
        ]
    )
    assert alloc2.get("M3") == "STOR1"
    print("[PASS] restricted flammable→STOR1; usage not persisted; overfill M3")


def poc_weather_wind_default():
    ns = exec_skill(
        "1_DDC_Toolkit/Schedule-Integration/weather-impact-scheduler/SKILL.md"
    )
    w = ns["WeatherImpactScheduler"]("Tower")
    act = w.add_activity(
        "CRANE1",
        "Tower Crane Pick",
        date(2026, 9, 28),
        date(2026, 9, 28),
        ns["ActivitySensitivity"].HIGH,
        outdoor=True,
    )
    assert act.max_wind == 50.0
    w.add_forecast(
        date(2026, 9, 28),
        ns["WeatherCondition"].CLEAR,
        20,
        10,
        0,
        45,
    )
    assert w.analyze_impacts() == []
    w2 = ns["WeatherImpactScheduler"]("Tower")
    w2.add_activity(
        "CRANE1",
        "Tower Crane Pick",
        date(2026, 9, 28),
        date(2026, 9, 28),
        ns["ActivitySensitivity"].HIGH,
    )
    w2.add_forecast(
        date(2026, 9, 28),
        ns["WeatherCondition"].CLEAR,
        20,
        10,
        0,
        55,
    )
    assert len(w2.analyze_impacts()) == 1
    print("[PASS] default max_wind=50 misses 45 km/h crane hold")


def poc_fleet_overdue_maintenance():
    ns = exec_skill(
        "1_DDC_Toolkit/Resource-Management/equipment-fleet-manager/SKILL.md"
    )
    fleet = ns["EquipmentFleetManager"]("Co")
    crane = fleet.add_equipment(
        "Tower Crane",
        ns["EquipmentType"].CRANE,
        "Liebherr",
        "280EC",
        2020,
        150,
        1200,
    )
    fleet.assign_equipment(crane.equipment_id, "Tower", "Site", date.today(), "Op")
    fleet.return_equipment(crane.equipment_id, hours_used=600)
    crane = fleet.equipment[crane.equipment_id]
    assert crane.status == ns["EquipmentStatus"].AVAILABLE
    assert crane.current_hours > crane.next_maintenance_hours
    assert crane.equipment_id in [
        e.equipment_id for e in fleet.get_available_equipment()
    ]
    print(
        "[PASS] overdue maintenance crane AVAILABLE:",
        crane.current_hours,
        ">",
        crane.next_maintenance_hours,
    )


def main():
    poc_as_built()
    poc_look_ahead_weekly_and_forge()
    poc_punch_forge_complete()
    poc_storage_restrictions()
    poc_weather_wind_default()
    poc_fleet_overdue_maintenance()
    print("\nAll PoCs passed.")


if __name__ == "__main__":
    main()
