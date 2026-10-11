#!/usr/bin/env python3
"""PoC: under-reviewed authZ/money/safety findings (2026-10-11).

Validates four NEW chains extracted from SKILL.md implementations:
1. equipment-fleet-manager — dead maintenance gate / assign ignores REPAIR
2. incident-reporting — OSHA underclassification + CA self-complete
3. cwicr-location-factor — overwrite canonical location factors
4. cwicr-risk-calculator — unbounded min/max_factor contingency poison
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional
import json
import sys

import numpy as np


def poc_fleet() -> dict:
    class EquipmentStatus(Enum):
        AVAILABLE = "available"
        IN_USE = "in_use"
        REPAIR = "repair"

    class EquipmentType(Enum):
        CRANE = "crane"

    @dataclass
    class MaintenanceRecord:
        record_id: str
        equipment_id: str
        maintenance_type: str
        scheduled_date: date
        completed_date: Optional[date]
        cost: float

    @dataclass
    class Assignment:
        assignment_id: str
        equipment_id: str
        project: str
        location: str
        start_date: date
        end_date: Optional[date]
        operator: str = ""

    @dataclass
    class Equipment:
        equipment_id: str
        name: str
        equipment_type: EquipmentType
        make: str
        model: str
        year: int
        status: EquipmentStatus
        hourly_rate: float
        daily_rate: float
        current_hours: float = 0
        next_maintenance_hours: float = 500
        assignments: List[Assignment] = field(default_factory=list)

    class EquipmentFleetManager:
        def __init__(self):
            self.equipment: Dict[str, Equipment] = {}
            self.maintenance_records = {}
            self._equip_counter = 0
            self._assign_counter = 0

        def add_equipment(self, name, equipment_type, make, model, year, hourly_rate, daily_rate):
            self._equip_counter += 1
            eid = f"EQ-{self._equip_counter:04d}"
            eq = Equipment(eid, name, equipment_type, make, model, year,
                           EquipmentStatus.AVAILABLE, hourly_rate, daily_rate)
            self.equipment[eid] = eq
            return eq

        def assign_equipment(self, equip_id, project, location, start_date, operator=""):
            if equip_id not in self.equipment:
                return None
            self._assign_counter += 1
            asn = Assignment(f"ASN-{self._assign_counter:04d}", equip_id, project,
                             location, start_date, None, operator)
            self.equipment[equip_id].assignments.append(asn)
            self.equipment[equip_id].status = EquipmentStatus.IN_USE
            return asn

        def return_equipment(self, equip_id, hours_used):
            eq = self.equipment[equip_id]
            eq.status = EquipmentStatus.AVAILABLE
            eq.current_hours += hours_used

        def schedule_maintenance(self, equip_id, maintenance_type, scheduled_date, cost):
            rid = f"MNT-{len(self.maintenance_records) + 1:04d}"
            self.maintenance_records[rid] = MaintenanceRecord(
                rid, equip_id, maintenance_type, scheduled_date, None, cost)

        def get_available_equipment(self):
            return [e for e in self.equipment.values() if e.status == EquipmentStatus.AVAILABLE]

    fleet = EquipmentFleetManager()
    crane = fleet.add_equipment("Tower Crane #1", EquipmentType.CRANE, "L", "280", 2020, 150, 1200)
    crane.current_hours = 600
    fleet.schedule_maintenance(crane.equipment_id, "critical_brake_repair", date.today(), 5000)
    available_after_mnt = any(e.equipment_id == crane.equipment_id for e in fleet.get_available_equipment())
    crane.status = EquipmentStatus.REPAIR
    asn = fleet.assign_equipment(crane.equipment_id, "Tower", "Site", date.today(), "attacker")
    fleet.return_equipment(crane.equipment_id, -200)
    ok = available_after_mnt and asn is not None and crane.current_hours == 400
    return {
        "id": "fleet-maintenance-dead-gate",
        "ok": ok,
        "detail": {
            "available_after_mnt": available_after_mnt,
            "assign_while_repair": asn is not None,
            "status_after_assign": "in_use",
            "hours_after_neg_return": crane.current_hours,
        },
    }


def poc_incident() -> dict:
    class IncidentType(Enum):
        NEAR_MISS = "near_miss"
        LOST_TIME = "lost_time"
        MEDICAL_TREATMENT = "medical_treatment"
        FATALITY = "fatality"

    class IncidentCategory(Enum):
        FALL = "fall"

    class InvestigationStatus(Enum):
        REPORTED = "reported"
        CORRECTIVE_ACTIONS_ASSIGNED = "corrective_actions_assigned"

    @dataclass
    class Person:
        name: str
        company: str
        role: str
        contact: str

    @dataclass
    class CorrectiveAction:
        id: str
        description: str
        assigned_to: str
        due_date: datetime
        status: str = "open"
        completed_date: Optional[datetime] = None
        verification_notes: str = ""

    @dataclass
    class Incident:
        id: str
        incident_type: IncidentType
        category: IncidentCategory
        date_time: datetime
        location: str
        project_id: str
        project_name: str
        description: str
        immediate_actions: str
        injured_person: Optional[Person] = None
        reported_by: str = ""
        status: InvestigationStatus = InvestigationStatus.REPORTED
        corrective_actions: List[CorrectiveAction] = field(default_factory=list)
        osha_recordable: bool = False

    class IncidentManager:
        def __init__(self):
            self.incidents = {}
            self.corrective_actions = {}

        def report_incident(self, incident_type, category, date_time, location,
                            project_id, project_name, description, immediate_actions,
                            reported_by, injured_person=None):
            iid = f"INC-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
            injured = Person(**injured_person) if injured_person else None
            inc = Incident(iid, incident_type, category, date_time, location, project_id,
                           project_name, description, immediate_actions, injured,
                           reported_by=reported_by)
            if incident_type in [IncidentType.MEDICAL_TREATMENT, IncidentType.LOST_TIME,
                                 IncidentType.FATALITY]:
                inc.osha_recordable = True
            self.incidents[iid] = inc
            return inc

        def assign_corrective_action(self, incident_id, description, assigned_to, due_days=7):
            aid = f"CA-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
            action = CorrectiveAction(aid, description, assigned_to,
                                      datetime.now() + timedelta(days=due_days))
            self.incidents[incident_id].corrective_actions.append(action)
            self.incidents[incident_id].status = InvestigationStatus.CORRECTIVE_ACTIONS_ASSIGNED
            self.corrective_actions[aid] = action
            return action

        def complete_corrective_action(self, action_id, verification_notes):
            action = self.corrective_actions[action_id]
            action.status = "completed"
            action.completed_date = datetime.now()
            action.verification_notes = verification_notes
            return action

        def calculate_trir(self, hours_worked):
            recordables = len([i for i in self.incidents.values() if i.osha_recordable])
            return (recordables * 200000) / hours_worked if hours_worked else 0

    injured = {"name": "Bob", "company": "Sub", "role": "Laborer", "contact": "x"}
    desc = "Worker fell, broken leg, 14 days lost"
    honest = IncidentManager()
    h = honest.report_incident(IncidentType.LOST_TIME, IncidentCategory.FALL, datetime.now(),
                               "L5", "P1", "Tower", desc, "911", "Foreman", injured)
    trir_h = honest.calculate_trir(200000)

    fake = IncidentManager()
    f = fake.report_incident(IncidentType.NEAR_MISS, IncidentCategory.FALL, datetime.now(),
                             "L5", "P1", "Tower", desc, "911", "attacker", injured)
    trir_f = fake.calculate_trir(200000)
    ca = fake.assign_corrective_action(f.id, "fix harness", "attacker")
    fake.complete_corrective_action(ca.id, "self ok")

    ok = trir_h == 1.0 and trir_f == 0.0 and (not f.osha_recordable) and ca.status == "completed"
    return {
        "id": "incident-osha-underclass",
        "ok": ok,
        "detail": {
            "honest_trir": trir_h,
            "underclass_trir": trir_f,
            "honest_osha": h.osha_recordable,
            "fake_osha": f.osha_recordable,
            "ca_status": ca.status,
        },
    }


def poc_location() -> dict:
    @dataclass
    class LocationFactor:
        location_code: str
        location_name: str
        country: str
        region: str
        labor_factor: float
        material_factor: float
        equipment_factor: float
        total_factor: float

    factors = {
        "US-NAT": LocationFactor("US-NAT", "US National", "US", "National", 1.0, 1.0, 1.0, 1.0),
        "US-NYC": LocationFactor("US-NYC", "New York City", "US", "NE", 1.45, 1.20, 1.15, 1.35),
    }

    def adjust_cost(base_cost, target, table):
        base = table["US-NAT"]
        tgt = table[target]
        bd = {"labor": base_cost * 0.40, "material": base_cost * 0.45, "equipment": base_cost * 0.15}
        return (bd["labor"] * (tgt.labor_factor / base.labor_factor)
                + bd["material"] * (tgt.material_factor / base.material_factor)
                + bd["equipment"] * (tgt.equipment_factor / base.equipment_factor))

    honest = adjust_cost(1_000_000, "US-NYC", factors)
    factors["US-NYC"] = LocationFactor("US-NYC", "New York City", "US", "NE", 0.01, 0.01, 0.01, 0.01)
    poisoned = adjust_cost(1_000_000, "US-NYC", factors)
    ok = honest > 1_200_000 and poisoned < 50_000
    return {
        "id": "location-factor-overwrite",
        "ok": ok,
        "detail": {"honest_nyc": round(honest, 2), "poisoned_nyc": round(poisoned, 2)},
    }


def poc_risk() -> dict:
    class DistributionType(Enum):
        UNIFORM = "uniform"
        TRIANGULAR = "triangular"

    @dataclass
    class RiskParameters:
        base_cost: float
        distribution: DistributionType
        min_factor: float
        max_factor: float
        most_likely_factor: float = 1.0

    def sample(p: RiskParameters) -> float:
        lo = p.base_cost * p.min_factor
        hi = p.base_cost * p.max_factor
        if p.distribution == DistributionType.UNIFORM:
            return float(np.random.uniform(lo, hi))
        mode = p.base_cost * p.most_likely_factor
        return float(np.random.triangular(lo, mode, hi))

    def contingency(params: RiskParameters, iterations: int = 4000) -> float:
        samples = [sample(params) for _ in range(iterations)]
        p80 = float(np.percentile(samples, 80))
        return p80 - params.base_cost

    np.random.seed(0)
    c_honest = contingency(RiskParameters(1_000_000, DistributionType.TRIANGULAR, 0.9, 1.4))
    np.random.seed(0)
    c_zero = contingency(RiskParameters(1_000_000, DistributionType.UNIFORM, 1.0, 1.0))
    np.random.seed(0)
    c_neg = contingency(RiskParameters(1_000_000, DistributionType.UNIFORM, -2.0, -0.5))
    ok = c_honest > 100_000 and abs(c_zero) < 1 and c_neg < 0
    return {
        "id": "risk-factor-contingency-poison",
        "ok": ok,
        "detail": {
            "honest_contingency": round(c_honest, 2),
            "zeroed_contingency": round(c_zero, 2),
            "negative_contingency": round(c_neg, 2),
        },
    }


def main() -> int:
    results = [poc_fleet(), poc_incident(), poc_location(), poc_risk()]
    print(json.dumps(results, indent=2))
    if not all(r["ok"] for r in results):
        print("FAIL", file=sys.stderr)
        return 1
    print(f"ALL_POCS_PASSED {len(results)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
