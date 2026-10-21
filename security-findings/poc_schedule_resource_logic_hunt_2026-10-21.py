#!/usr/bin/env python3
"""Non-destructive PoCs for schedule/resource/safety business-logic bugs.

Validates 7 HIGH findings in DDC Skills SKILL.md Python templates.
Run: python3 security-findings/poc_schedule_resource_logic_hunt_2026-10-21.py
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
PASS = 0
FAIL = 0


def ok(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"PASS  {name}" + (f" — {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"FAIL  {name}" + (f" — {detail}" if detail else ""))


def extract_python(skill_md: Path) -> str:
    text = skill_md.read_text()
    blocks = re.findall(r"```python\n(.*?)```", text, re.S)
    return "\n\n".join(blocks)


def load_ns(skill_rel: str, block_slice: slice | None = None) -> dict:
    src = extract_python(ROOT / skill_rel)
    if block_slice is not None:
        parts = re.split(r"\n(?=from |import |class |# )", src)  # unused
        parts = src.split("\n\n")
        # Prefer splitting on natural class boundaries via full exec of first N chars
        blocks = re.findall(
            r"```python\n(.*?)```",
            (ROOT / skill_rel).read_text(),
            re.S,
        )
        src = "\n\n".join(blocks[block_slice])
    ns: dict = {}
    exec(src, ns)
    return ns


# ---------------------------------------------------------------------------
# 1. Look-ahead: missing predecessors fail open
# ---------------------------------------------------------------------------
def poc_look_ahead() -> None:
    # Minimal faithful copy of the gate
    class ActivityStatus(Enum):
        NOT_STARTED = "not_started"
        COMPLETE = "complete"

    class ConstraintStatus(Enum):
        RESOLVED = "resolved"

    @dataclass
    class LookAheadActivity:
        id: str
        predecessors: List[str] = field(default_factory=list)
        status: ActivityStatus = ActivityStatus.NOT_STARTED
        constraints: list = field(default_factory=list)
        can_start: bool = False

    activities = {
        # Predecessor A050 (foundation) outside look-ahead window / omitted
        "A200": LookAheadActivity("A200", predecessors=["A050"]),
    }

    for act in activities.values():
        pred_complete = all(
            activities.get(p, {}).status == ActivityStatus.COMPLETE
            for p in act.predecessors
            if p in activities
        )
        open_constraints = [
            c for c in act.constraints if c.status != ConstraintStatus.RESOLVED
        ]
        if not pred_complete:
            act.can_start = False
        elif open_constraints:
            act.can_start = False
        else:
            act.can_start = True

    ok(
        "look-ahead missing predecessor → can_start",
        activities["A200"].can_start is True,
        "A050 not in window; all([]) is True",
    )


# ---------------------------------------------------------------------------
# 2. Resource leveling ignores FS / starts pred after succ
# ---------------------------------------------------------------------------
def poc_resource_leveling() -> None:
    blocks = re.findall(
        r"```python\n(.*?)```",
        (ROOT / "3_DDC_Insights/Schedule-Optimization/resource-allocation-optimizer/SKILL.md").read_text(),
        re.S,
    )
    ns: dict = {}
    exec(blocks[0], ns)
    opt = ns["ResourceOptimizer"]()
    opt.add_resource("CRANE", "Crane", "equipment", capacity=1, cost_per_unit=1000)
    # Conceptual FS: A before B. A has float; B critical (not shifted).
    opt.add_activity(
        "A", "Foundation", duration=10, early_start=0, late_start=25,
        resource_requirements={"CRANE": 1}, is_critical=False,
    )
    opt.add_activity(
        "B", "Steel", duration=10, early_start=5, late_start=5,
        resource_requirements={"CRANE": 1}, is_critical=True,
    )
    result = opt.level_resources()
    starts = {"A": 0, "B": 5}
    for aid, _old, new in result.activities_shifted:
        starts[aid] = new
    ok(
        "resource leveling pred starts after succ",
        starts["A"] > starts["B"],
        f"starts={starts} shifts={result.activities_shifted}",
    )


# ---------------------------------------------------------------------------
# 3. Schedule compression forges achieved_reduction / duration
# ---------------------------------------------------------------------------
def poc_schedule_compression() -> None:
    blocks = re.findall(
        r"```python\n(.*?)```",
        (ROOT / "3_DDC_Insights/Schedule-Optimization/schedule-compression/SKILL.md").read_text(),
        re.S,
    )
    ns: dict = {}
    exec(blocks[0], ns)
    SC = ns["ScheduleCompressor"]

    c = SC()
    c.add_activity("A", "P1", 20, 10, 100, 200, is_critical=True)
    c.add_activity("B", "P1e", 5, 5, 50, 50, predecessors=["A"], is_critical=True)
    c.add_activity("C", "P2", 20, 10, 100, 200, is_critical=True)
    c.add_activity("D", "P2e", 5, 5, 50, 50, predecessors=["C"], is_critical=True)
    orig = c.calculate_project_duration()
    plan = c.crash_schedule(10)
    actual = orig - plan.new_project_duration
    ok(
        "compression crash inflates achieved_reduction",
        plan.achieved_reduction > actual,
        f"claimed={plan.achieved_reduction} actual_drop={actual} new={plan.new_project_duration}",
    )

    c2 = SC()
    c2.add_activity("A", "Found", 20, 15, 100, 130, is_critical=True)
    c2.add_activity("B", "Steel", 30, 22, 200, 260, predecessors=["A"], is_critical=True)
    c2.add_fast_track_option("A", "B", 25, "low", "x")
    c2.calculate_project_duration()
    ft = c2.fast_track_schedule(25, max_risk="low")
    ok(
        "fast-track forges duration without network change",
        ft.new_project_duration == c2.project_duration - 25
        and c2.activities["A"].current_duration == 20,
        f"reported_new={ft.new_project_duration} cpm_still={c2.project_duration}",
    )


# ---------------------------------------------------------------------------
# 4. Fleet: double-book + assign from MAINTENANCE
# ---------------------------------------------------------------------------
def poc_fleet() -> None:
    blocks = re.findall(
        r"```python\n(.*?)```",
        (ROOT / "1_DDC_Toolkit/Resource-Management/equipment-fleet-manager/SKILL.md").read_text(),
        re.S,
    )
    ns: dict = {}
    exec(blocks[0], ns)
    fleet = ns["EquipmentFleetManager"]("Co")
    crane = fleet.add_equipment(
        "Tower", ns["EquipmentType"].CRANE, "L", "1", 2020, 100, 1000
    )
    fleet.assign_equipment(crane.equipment_id, "SiteA", "A", date.today(), "Op1")
    fleet.assign_equipment(crane.equipment_id, "SiteB", "B", date.today(), "Op2")
    ok(
        "fleet double-assigns IN_USE crane",
        len(crane.assignments) == 2,
        f"projects={[a.project for a in crane.assignments]}",
    )
    crane.status = ns["EquipmentStatus"].MAINTENANCE
    a3 = fleet.assign_equipment(crane.equipment_id, "SiteC", "C", date.today())
    ok(
        "fleet assigns equipment from MAINTENANCE",
        a3 is not None and crane.status == ns["EquipmentStatus"].IN_USE,
        f"status={crane.status}",
    )


# ---------------------------------------------------------------------------
# 5. Labor: conflict warning only
# ---------------------------------------------------------------------------
def poc_labor() -> None:
    blocks = re.findall(
        r"```python\n(.*?)```",
        (ROOT / "1_DDC_Toolkit/Resource-Management/labor-allocation/SKILL.md").read_text(),
        re.S,
    )
    ns: dict = {}
    exec(blocks[0], ns)
    labor = ns["LaborAllocation"]("P")
    labor.add_worker(
        "W1", "Joe", ns["Trade"].IRONWORKER, ns["SkillLevel"].JOURNEYMAN, 50, "Co"
    )
    labor.assign_worker(
        "W1", "A1", "Steel A", date.today(), date.today() + timedelta(5), 8, "ZoneA"
    )
    labor.assign_worker(
        "W1", "A2", "Steel B", date.today(), date.today() + timedelta(5), 8, "ZoneB"
    )
    roster = labor.get_daily_roster(date.today())
    ok(
        "labor keeps conflicting assignments on roster",
        len(labor.assignments) == 2 and len(roster) == 2,
        f"activities={roster['Activity'].tolist()}",
    )


# ---------------------------------------------------------------------------
# 6. Telematics: CRITICAL fault still "operating"
# ---------------------------------------------------------------------------
def poc_telematics() -> None:
    blocks = re.findall(
        r"```python\n(.*?)```",
        (ROOT / "5_DDC_Innovative/equipment-telematics/SKILL.md").read_text(),
        re.S,
    )
    ns: dict = {}
    exec(blocks[0], ns)
    tel = ns["EquipmentTelematics"]("Fleet")
    tel.register_equipment(
        "CR1", "Crane", ns["EquipmentType"].CRANE, "L", "1", 2021, "SN", 200, 300
    )
    loc = ns["GPSLocation"](40.0, -74.0, speed=0, timestamp=datetime.now())
    tel.ingest_reading(
        "CR1", loc, engine_hours=100, fuel_level=50, fuel_rate=12,
        engine_rpm=1500, hydraulic_temp=80, coolant_temp=120,
        load_percentage=80, operator_id="OP",
    )
    st = tel.get_current_status("CR1")
    crit = [
        f for f in tel.faults
        if not f.resolved and f.severity == ns["FaultSeverity"].CRITICAL
    ]
    ok(
        "telematics CRITICAL still status=operating",
        st["status"] == "operating" and len(crit) >= 1,
        f"status={st['status']} faults={[f.code for f in crit]}",
    )
    # FAULT/SHUTDOWN enums never applied by ingest
    ok(
        "telematics never sets OperatingStatus.FAULT",
        ns["OperatingStatus"].FAULT not in {
            r.operating_status for r in tel.readings
        },
        "status derived only from RPM/load",
    )


# ---------------------------------------------------------------------------
# 7. Punch: accept OPEN critical without completion
# ---------------------------------------------------------------------------
def poc_punch() -> None:
    blocks = re.findall(
        r"```python\n(.*?)```",
        (ROOT / "1_DDC_Toolkit/Field-Operations/punch-list-manager/SKILL.md").read_text(),
        re.S,
    )
    ns: dict = {}
    exec(blocks[0] + "\n" + blocks[1], ns)
    mgr = ns["PunchListManager"]("P")
    pl = mgr.create_punch_list("Final", date.today(), ["PM"], list_type="Final")
    item = mgr.add_item(
        pl.list_id,
        "Missing fire damper",
        "Mech",
        ns["TradeCategory"].FIRE_PROTECTION,
        ns["PunchItemPriority"].CRITICAL,
    )
    mgr.verify_item(item.item_id, "PM", accepted=True, notes="waived")
    stats = mgr.get_statistics()
    ok(
        "punch accepts OPEN CRITICAL without mark_complete",
        item.status == ns["PunchItemStatus"].ACCEPTED
        and stats["completion_rate"] == 100.0,
        f"status={item.status.value} completion={stats['completion_rate']}",
    )


def main() -> int:
    poc_look_ahead()
    poc_resource_leveling()
    poc_schedule_compression()
    poc_fleet()
    poc_labor()
    poc_telematics()
    poc_punch()
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
