#!/usr/bin/env python3
"""PoCs for Safety/Quality business-logic hunt (2026-10-14)."""

from __future__ import annotations

import pathlib
import sys
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


def _load_skill_class(skill_path: str, marker: str):
    text = pathlib.Path(skill_path).read_text()
    blocks, cur = [], None
    for line in text.splitlines():
        if line.strip() == "```python":
            cur = []
        elif line.strip() == "```" and cur is not None:
            blocks.append("\n".join(cur))
            cur = None
        elif cur is not None:
            cur.append(line)
    code = next(b for b in blocks if marker in b)
    ns: dict = {}
    exec(code, ns)
    return ns


def poc_env_backdated_twa_suppress() -> None:
    ns = _load_skill_class(
        "/workspace/5_DDC_Innovative/environmental-monitoring/SKILL.md",
        "class EnvironmentalMonitor",
    )
    EnvironmentalMonitor = ns["EnvironmentalMonitor"]
    ParameterType = ns["ParameterType"]

    now = datetime.now()

    control = EnvironmentalMonitor("control")
    control.add_station("S1", "Gate", {}, [ParameterType.NOISE])
    control.record_reading("S1", ParameterType.NOISE, 100, "dBA", timestamp=now)
    assert any(a.alert_type.value == "threshold_exceedance" for a in control.alerts), control.alerts

    attack = EnvironmentalMonitor("attack")
    attack.add_station("S1", "Gate", {}, [ParameterType.NOISE])
    attack.record_reading(
        "S1", ParameterType.NOISE, 100, "dBA", timestamp=now - timedelta(hours=10)
    )
    assert attack.alerts == [], f"expected no alerts, got {attack.alerts}"

    # Instantaneous vibration still alerts when backdated (control contrast)
    attack.record_reading(
        "S1", ParameterType.VIBRATION, 30, "mm/s", timestamp=now - timedelta(hours=10)
    )
    assert any(a.parameter.value == "vibration" for a in attack.alerts)

    print("PASS env_backdated_twa_suppress")


def poc_defect_severity_ignores_physical_mm() -> None:
    class DefectType(Enum):
        CRACK = "crack"

    class SeverityLevel(Enum):
        MINOR = "minor"
        MODERATE = "moderate"
        SEVERE = "severe"
        CRITICAL = "critical"

    @dataclass
    class BoundingBox:
        x1: int
        y1: int
        x2: int
        y2: int

        @property
        def width(self) -> int:
            return self.x2 - self.x1

        @property
        def height(self) -> int:
            return self.y2 - self.y1

        @property
        def area(self) -> int:
            return self.width * self.height

    @dataclass
    class DetectedDefect:
        defect_type: DefectType
        severity: SeverityLevel
        bounding_box: BoundingBox
        dimensions_mm: Optional[Tuple[float, float]]
        confidence: float = 0.95

    def classify_severity(defect_type, bbox, image_size):
        # Mirrors DefectDetectionModel._classify_severity
        image_area = image_size[0] * image_size[1]
        defect_ratio = bbox.area / image_area
        t = {"critical": 0.1, "severe": 0.05, "moderate": 0.02}
        if defect_ratio >= t["critical"]:
            return SeverityLevel.CRITICAL
        if defect_ratio >= t["severe"]:
            return SeverityLevel.SEVERE
        if defect_ratio >= t["moderate"]:
            return SeverityLevel.MODERATE
        return SeverityLevel.MINOR

    def assess(defects: List[DetectedDefect]) -> str:
        if not defects:
            return "Good"
        scores = {
            SeverityLevel.MINOR: 1,
            SeverityLevel.MODERATE: 2,
            SeverityLevel.SEVERE: 3,
            SeverityLevel.CRITICAL: 4,
        }
        max_severity = max(scores[d.severity] for d in defects)
        if max_severity >= 4 or len(defects) > 10:
            return "Critical - Immediate attention required"
        if max_severity >= 3 or len(defects) > 5:
            return "Poor - Repairs needed"
        if max_severity >= 2 or len(defects) > 2:
            return "Fair - Monitor and plan repairs"
        return "Good - Minor issues only"

    def recommendations(defects: List[DetectedDefect]) -> List[str]:
        out = []
        groups: Dict = {}
        for d in defects:
            groups.setdefault(d.defect_type, []).append(d)
        for defect_type, group in groups.items():
            max_sev = max(d.severity for d in group)
            if defect_type == DefectType.CRACK:
                if max_sev in (SeverityLevel.CRITICAL, SeverityLevel.SEVERE):
                    out.append("STRUCTURAL_ENGINEER")
                else:
                    out.append("SEALANT_ONLY")
        return out

    pixels_per_mm = 2.0
    bbox = BoundingBox(100, 100, 300, 120)  # 200×20 px → 100mm × 10mm
    dimensions_mm = (bbox.width / pixels_per_mm, bbox.height / pixels_per_mm)
    severity = classify_severity(DefectType.CRACK, bbox, (4000, 3000))
    defect = DetectedDefect(DefectType.CRACK, severity, bbox, dimensions_mm)

    assert dimensions_mm[0] == 100.0 and dimensions_mm[1] == 10.0
    assert severity == SeverityLevel.MINOR
    assert assess([defect]) == "Good - Minor issues only"
    assert recommendations([defect]) == ["SEALANT_ONLY"]

    print("PASS defect_severity_ignores_physical_mm")


def main() -> int:
    poc_env_backdated_twa_suppress()
    poc_defect_severity_ignores_physical_mm()
    print("ALL_POCS_PASSED 2")
    return 0


if __name__ == "__main__":
    sys.exit(main())
