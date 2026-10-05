#!/usr/bin/env python3
"""PoC: 3_DDC_Insights remaining Schedule/Safety logic flaws (2026-10-05)."""
from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_skill_python(rel: str, block_index: int = 0):
    text = (ROOT / rel).read_text()
    blocks = re.findall(r"```python\n(.*?)```", text, re.S)
    ns: dict = {}
    exec(compile(blocks[block_index], rel, "exec"), ns)
    return ns


def test_negative_resource_units_hide_crane_overallocation():
    ns = load_skill_python(
        "3_DDC_Insights/Schedule-Optimization/resource-allocation-optimizer/SKILL.md"
    )
    opt = ns["ResourceOptimizer"]()
    opt.add_resource("CRANE", "Tower Crane", "equipment", capacity=1)
    opt.add_activity(
        "STEEL1", "Steel pick 1", 5, 0, 0, {"CRANE": 1}, is_critical=True
    )
    opt.add_activity(
        "STEEL2", "Steel pick 2", 5, 0, 0, {"CRANE": 1}, is_critical=True
    )
    before = opt.identify_overallocations()
    assert "CRANE" in before and before["CRANE"][0][1] == 1.0

    # Phantom credit activity with negative crane demand cancels the overload
    opt.add_activity(
        "PHANTOM", "Credit", 5, 0, 10, {"CRANE": -1}, is_critical=True
    )
    after = opt.identify_overallocations()
    peak = opt.calculate_resource_profile("CRANE").peak_usage
    assert after == {}, after
    assert peak == 1.0, peak
    print("PASS negative resource units hide crane overallocation")


def test_negative_crash_slope_pays_attacker():
    ns = load_skill_python(
        "3_DDC_Insights/Schedule-Optimization/schedule-compression/SKILL.md"
    )
    c = ns["ScheduleCompressor"]()
    c.add_activity(
        "A",
        "Foundation",
        normal_duration=20,
        crash_duration=10,
        normal_cost=100_000,
        crash_cost=0,  # cheaper than normal → negative slope
        is_critical=True,
    )
    c.add_activity(
        "B",
        "Steel",
        normal_duration=30,
        crash_duration=20,
        normal_cost=200_000,
        crash_cost=250_000,
        predecessors=["A"],
        is_critical=True,
    )
    assert c.activities["A"].crash_slope == -10_000.0
    plan = c.crash_schedule(target_days=5)
    assert plan.achieved_reduction == 5
    assert plan.total_additional_cost == -50_000.0, plan.total_additional_cost
    print("PASS negative crash_slope invents -$50k compression 'savings'")


def test_cpa_negative_zero_duration_understates_project():
    ns = load_skill_python(
        "3_DDC_Insights/Schedule-Optimization/critical-path-analyzer/SKILL.md"
    )
    honest = ns["CriticalPathAnalyzer"]()
    honest.import_schedule(
        [
            {"id": "F", "name": "Found", "duration": 30, "predecessors": []},
            {"id": "S", "name": "Steel", "duration": 40, "predecessors": ["F"]},
            {"id": "R", "name": "Roof", "duration": 20, "predecessors": ["S"]},
        ]
    )
    honest_dur = honest.calculate_critical_path().project_duration
    assert honest_dur == 90

    zero = ns["CriticalPathAnalyzer"]()
    zero.import_schedule(
        [
            {"id": "F", "name": "Found", "duration": 30, "predecessors": []},
            {"id": "S", "name": "Steel", "duration": 0, "predecessors": ["F"]},
            {"id": "R", "name": "Roof", "duration": 20, "predecessors": ["S"]},
        ]
    )
    zero_dur = zero.calculate_critical_path().project_duration
    assert zero_dur == 50, zero_dur

    neg = ns["CriticalPathAnalyzer"]()
    neg.import_schedule(
        [
            {"id": "F", "name": "Found", "duration": 30, "predecessors": []},
            {"id": "S", "name": "Steel", "duration": -10, "predecessors": ["F"]},
            {"id": "R", "name": "Roof", "duration": 20, "predecessors": ["S"]},
        ]
    )
    neg_dur = neg.calculate_critical_path().project_duration
    assert neg_dur == 40, neg_dur
    print(
        f"PASS CPA duration understate honest={honest_dur} zero={zero_dur} neg={neg_dur}"
    )


def test_ncr_negative_cost_schedule_impact():
    ns = load_skill_python(
        "3_DDC_Insights/Safety-Quality/quality-control-workflow/SKILL.md"
    )
    mgr = ns["QualityControlManager"]("P1", "Tower")
    mgr.create_itp("WP", [{"name": "rebar", "criteria": "cover"}])
    insp = mgr.schedule_inspection(
        list(mgr.inspection_points)[0], "L3", datetime.now(), "insp"
    )
    mgr.conduct_inspection(insp.id, "fail")
    d = mgr.record_defect(
        insp.id,
        "bad cover",
        "L3",
        ns["DefectSeverity"].CRITICAL,
        "03 20 00",
    )
    ncr = mgr.create_ncr([d.id], "Cover NCR", "Sub A")
    mgr.record_ncr_response(
        ncr.id, "ok", "fix", cost_impact=-500_000, schedule_impact=-30
    )
    metrics = mgr.get_quality_metrics()
    assert ncr.status == ns["NCRStatus"].ACCEPTED
    assert metrics["total_cost_impact"] == -500_000
    assert metrics["total_schedule_impact"] == -30
    report = mgr.generate_qc_report()
    assert "-500,000" in report or "$-500,000" in report
    print("PASS NCR negative cost/schedule impact understates QC metrics")


def main() -> int:
    test_negative_resource_units_hide_crane_overallocation()
    test_negative_crash_slope_pays_attacker()
    test_cpa_negative_zero_duration_understates_project()
    test_ncr_negative_cost_schedule_impact()
    print("ALL 4 PoCs PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
