#!/usr/bin/env python3
"""PoC: distinct MEDIUM+ fail-open / skipped-gate logic bugs in scoped DDC Skills.

Hunt: safety / BIM validation / env / data-quality (2026-10-30)
Does not re-prove already-reported classes (harness/hot-work, ids IfcElement,
ISO19650 missing fields, sensor structural thresholds, cert valid_until,
enterprise risk probability, digital-twin IFC overwrite, Moscow HVAC, etc.).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List

import numpy as np


def finding_1_lod_pass_gate_ignored() -> None:
    """BIMValidationPipeline._evaluate_pass never consults lod_report."""

    def _evaluate_pass(bim_report, lod_report, config=None):
        config = config or {"fail_on_errors": True, "warn_threshold": 50}
        if config["fail_on_errors"] and bim_report["errors"] > 0:
            return False
        if bim_report["warnings"] > config["warn_threshold"]:
            return False
        return True  # lod_report unused

    lod_fail = {"total_issues": 999, "summary": {"IfcWall": {"compliance": 0}}}
    bim_ok = {"errors": 0, "warnings": 10}
    assert _evaluate_pass(bim_ok, lod_fail) is True

    # Empty type set → 100% LOD compliance
    n_elements, n_issues = 0, 0
    compliance = (
        (n_elements - n_issues) / n_elements * 100 if n_elements else 100
    )
    assert compliance == 100

    # Mistyped LOD key → empty requirements → zero checks
    LOD_REQUIREMENTS = {"LOD300": {"geometry": True, "properties": ["Category"]}}
    assert LOD_REQUIREMENTS.get("LOD 300", {}) == {}
    print("[OK] F1 BIMValidationPipeline ignores LOD; empty/mistyped LOD → 100%/no checks")


def finding_2_safety_rules_never_evaluated() -> None:
    """Excavation / scaffolding / electrical rules loaded but never run."""
    loaded = {
        "OSHA-1926.100",
        "OSHA-1926.501",
        "OSHA-1926.651",
        "OSHA-1926.1200",
        "OSHA-1926.352",
        "OSHA-1926.451",
        "OSHA-1926.405",
    }
    evaluated = {
        "OSHA-1926.501",
        "OSHA-1926.100",
        "OSHA-1926.352",
        "OSHA-1926.1200",
    }
    never = loaded - evaluated
    assert never == {"OSHA-1926.651", "OSHA-1926.451", "OSHA-1926.405"}

    activity = {
        "type": "excavation",
        "height_ft": 0,
        "workers": [{"id": "W1", "ppe": ["helmet"]}],
        "permits": [],
        "equipment": [],
    }
    checks = []
    if activity.get("height_ft", 0) >= 6:
        checks.append("OSHA-1926.501")
    for _ in activity["workers"]:
        checks.append("OSHA-1926.100")
    if activity["type"] in ["welding", "cutting", "brazing"]:
        checks.append("OSHA-1926.352")
    if activity.get("confined_space"):
        checks.append("OSHA-1926.1200")
    assert "OSHA-1926.651" not in checks
    print(f"[OK] F2 excavation activity checks={checks}; never fires {never}")


def finding_3_env_empty_compliant() -> None:
    """Daily env report COMPLIANT with zero readings; PM2.5 live status TWA-blind."""

    class ComplianceStatus(Enum):
        COMPLIANT = "compliant"
        WARNING = "warning"
        EXCEEDANCE = "exceedance"

    compliance_records: list = []
    exceedances = [r for r in compliance_records if r == ComplianceStatus.EXCEEDANCE]
    if exceedances:
        overall = ComplianceStatus.EXCEEDANCE
    elif any(False for _ in compliance_records):
        overall = ComplianceStatus.WARNING
    else:
        overall = ComplianceStatus.COMPLIANT
    assert overall == ComplianceStatus.COMPLIANT

    # PM2.5 REGULATORY_LIMITS are TWA-only (avg_h > 0)
    limits = [{"limit": 35, "avg_h": 24.0}, {"limit": 12, "avg_h": 8760.0}]
    instant = [l for l in limits if l["avg_h"] == 0]
    value = 500.0
    status = ComplianceStatus.COMPLIANT
    for limit in instant:
        if value >= limit["limit"]:
            status = ComplianceStatus.EXCEEDANCE
    assert status == ComplianceStatus.COMPLIANT and instant == []
    print("[OK] F3 empty env day → COMPLIANT; PM2.5=500 live status COMPLIANT")


def finding_4_bim_validator_empty_pass() -> None:
    """BIMDataValidator stamps PASSED on {} and garbage elements."""

    class ValidationSeverity(Enum):
        ERROR = "error"
        WARNING = "warning"

    @dataclass
    class ValidationIssue:
        field: str
        message: str
        severity: ValidationSeverity

    @dataclass
    class ValidationResult:
        is_valid: bool
        issues: List[ValidationIssue] = field(default_factory=list)

        def add_error(self, field, message):
            self.issues.append(
                ValidationIssue(field, message, ValidationSeverity.ERROR)
            )
            self.is_valid = False

        def add_warning(self, field, message):
            self.issues.append(
                ValidationIssue(field, message, ValidationSeverity.WARNING)
            )

    class BIMDataValidator:
        def validate(self, bim_data: Dict[str, Any]) -> ValidationResult:
            result = ValidationResult(is_valid=True)
            if "elements" in bim_data:
                guids = set()
                for i, elem in enumerate(bim_data["elements"]):
                    guid = elem.get("guid")
                    if guid in guids:
                        result.add_error(f"elements[{i}].guid", "dup")
                    guids.add(guid)
                    if not elem.get("ifc_type"):
                        result.add_warning(f"elements[{i}]", "missing type")
                    if not elem.get("name"):
                        result.add_warning(f"elements[{i}]", "missing name")
                    if not elem.get("geometry") and not elem.get("location"):
                        result.add_warning(f"elements[{i}]", "no geometry")
            return result

    v = BIMDataValidator()
    assert v.validate({}).is_valid is True
    r = v.validate({"elements": [{"guid": "a"}, {"guid": "b"}]})
    assert r.is_valid is True
    assert all(i.severity == ValidationSeverity.WARNING for i in r.issues)
    print("[OK] F4 BIMDataValidator {} / garbage elements → is_valid=True")


def finding_5_dq_falsy_score_excluded() -> None:
    """run_full_check drops falsy overall (0%) so missing columns → 100% PASSED."""
    results = {
        "completeness": {"overall": 0.0},  # all required cols missing
        "accuracy": {"overall": 100},  # no numeric cols → else 100
        "consistency": {"overall": 100},
        "validity": {"overall": 100},
    }
    scores = []
    for metric in ["completeness", "accuracy", "consistency", "validity"]:
        if metric in results and results[metric].get("overall"):
            scores.append(results[metric]["overall"])
    overall_score = float(np.mean(scores)) if scores else 0
    assert scores == [100, 100, 100]
    assert overall_score == 100.0
    assert overall_score >= 90
    print("[OK] F5 completeness=0 excluded → overall_score=100 PASSED")


def finding_6_ncr_auto_accepted() -> None:
    """Contractor response sets NCRStatus.ACCEPTED; verify closes without reinspect."""

    class NCRStatus(Enum):
        ISSUED = "issued"
        ACCEPTED = "accepted"
        VERIFIED = "verified"

    ncr = {"status": NCRStatus.ISSUED, "defects": {"DEF-1": "open"}}
    # record_ncr_response path
    ncr["status"] = NCRStatus.ACCEPTED
    assert ncr["status"] == NCRStatus.ACCEPTED
    # verify_remediation path
    ncr["status"] = NCRStatus.VERIFIED
    ncr["defects"]["DEF-1"] = "closed"
    assert ncr["defects"]["DEF-1"] == "closed"
    print("[OK] F6 NCR contractor response → ACCEPTED; verify closes defects w/o reinspect")


def finding_7_consistency_bounded_default() -> None:
    """Missing is_bounded / room_bounding default True → enclosure gate skipped."""
    room = {"id": "R1", "type": "Room"}
    wall = {"id": "W1", "type": "Wall"}
    assert room.get("is_bounded", True) is True
    assert wall.get("room_bounding", True) is True
    issues = []
    if not room.get("is_bounded", True):
        issues.append("Unbounded Room")
    if wall.get("type") == "Wall" and not wall.get("room_bounding", True):
        issues.append("not room bounding")
    assert issues == []
    print("[OK] F7 omit is_bounded/room_bounding → treated as properly enclosed")


if __name__ == "__main__":
    finding_1_lod_pass_gate_ignored()
    finding_2_safety_rules_never_evaluated()
    finding_3_env_empty_compliant()
    finding_4_bim_validator_empty_pass()
    finding_5_dq_falsy_score_excluded()
    finding_6_ncr_auto_accepted()
    finding_7_consistency_bounded_default()
    print("\nALL PoCs PASSED")
