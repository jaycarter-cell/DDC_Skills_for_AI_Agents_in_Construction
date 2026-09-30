#!/usr/bin/env python3
"""PoC: distinct HIGH/CRITICAL logic bugs in 5_DDC_Innovative skill templates.

Reimplements the vulnerable functions from SKILL.md (non-destructive).
Expected: 6/6 PASS.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional
import os

results = []


def check(name: str, cond: bool, detail: str = "") -> None:
    results.append((name, bool(cond), detail))
    print(("PASS" if cond else "FAIL"), name, detail)


# ---------- 1. change-order-analysis ----------
class ChangeOrderType(Enum):
    SCOPE_CHANGE = "scope_change"


class ChangeOrderStatus(Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"


class ImpactSeverity(Enum):
    MINOR = "minor"
    MODERATE = "moderate"
    MAJOR = "major"
    CRITICAL = "critical"


@dataclass
class CostBreakdown:
    labor: float = 0
    materials: float = 0
    equipment: float = 0
    subcontractor: float = 0
    overhead: float = 0
    profit: float = 0

    @property
    def total(self) -> float:
        return (
            self.labor
            + self.materials
            + self.equipment
            + self.subcontractor
            + self.overhead
            + self.profit
        )


@dataclass
class ScheduleImpact:
    direct_days: int
    ripple_days: int
    critical_path_affected: bool
    affected_activities: List[str] = field(default_factory=list)

    @property
    def total_days(self) -> int:
        return self.direct_days + self.ripple_days


@dataclass
class ChangeOrderDetail:
    co_id: str
    co_number: str
    title: str
    description: str
    justification: str
    co_type: ChangeOrderType
    initiated_by: str
    responsibility: str
    status: ChangeOrderStatus
    submitted_date: date
    approved_date: Optional[date] = None
    cost_breakdown: CostBreakdown = field(default_factory=CostBreakdown)
    schedule_impact: Optional[ScheduleImpact] = None
    severity: ImpactSeverity = ImpactSeverity.MINOR
    approvals: List[Dict] = field(default_factory=list)


class ChangeOrderManager:
    def __init__(self, project_id: str, contract_value: float):
        self.project_id = project_id
        self.contract_value = contract_value
        self.change_orders: Dict[str, ChangeOrderDetail] = {}
        self.co_counter = 0

    def create_change_order(self, title, description, co_type, initiated_by):
        self.co_counter += 1
        co_id = f"CO-{self.project_id}-{self.co_counter:04d}"
        co = ChangeOrderDetail(
            co_id=co_id,
            co_number=f"CO-{self.co_counter:04d}",
            title=title,
            description=description,
            justification="",
            co_type=co_type,
            initiated_by=initiated_by,
            responsibility="TBD",
            status=ChangeOrderStatus.DRAFT,
            submitted_date=date.today(),
        )
        self.change_orders[co_id] = co
        return co

    def update_cost(self, co_id, cost_breakdown):
        co = self.change_orders.get(co_id)
        if co:
            co.cost_breakdown = cost_breakdown

    def approve(self, co_id, approver, comments=""):
        co = self.change_orders.get(co_id)
        if co:
            co.approvals.append(
                {
                    "approver": approver,
                    "action": "approved",
                    "date": date.today().isoformat(),
                    "comments": comments,
                }
            )
            co.status = ChangeOrderStatus.APPROVED
            co.approved_date = date.today()

    def get_summary(self):
        total_cost = sum(co.cost_breakdown.total for co in self.change_orders.values())
        return {"total_cost_impact": total_cost}


mgr = ChangeOrderManager("P1", 10_000_000)
co = mgr.create_change_order("Steel", "d", ChangeOrderType.SCOPE_CHANGE, "contractor")
mgr.update_cost(co.co_id, CostBreakdown(materials=50_000))
mgr.approve(co.co_id, "Forged Owner")  # DRAFT → APPROVED
mgr.update_cost(co.co_id, CostBreakdown(materials=5_000_000, profit=500_000))  # post-approve
co2 = mgr.create_change_order("Credit", "d", ChangeOrderType.SCOPE_CHANGE, "contractor")
mgr.update_cost(co2.co_id, CostBreakdown(labor=-2_000_000))
mgr.approve(co2.co_id, "Forged Owner")
s = mgr.get_summary()
check(
    "CO-analysis approve DRAFT + post-mutate + negative",
    co.status == ChangeOrderStatus.APPROVED
    and co.cost_breakdown.total == 5_500_000
    and s["total_cost_impact"] == 3_500_000,
    f"status={co.status.value} mutated={co.cost_breakdown.total} summary={s['total_cost_impact']}",
)


# ---------- 2. equipment-telematics utilization ----------
class EquipmentType(Enum):
    CRANE = "crane"


class OperatingStatus(Enum):
    OPERATING = "operating"
    IDLE = "idle"
    OFF = "off"


@dataclass
class GPSLocation:
    latitude: float
    longitude: float
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class TelematicsReading:
    equipment_id: str
    timestamp: datetime
    location: GPSLocation
    engine_hours: float
    fuel_rate: float
    operating_status: OperatingStatus


@dataclass
class Equipment:
    id: str
    name: str
    equipment_type: EquipmentType
    current_hours: float = 0


class EquipmentTelematics:
    def __init__(self):
        self.equipment = {}
        self.readings = []

    def register_equipment(self, id, name, equipment_type):
        self.equipment[id] = Equipment(id, name, equipment_type)

    def ingest_reading(
        self, equipment_id, location, engine_hours, fuel_rate, engine_rpm, load_percentage=0
    ):
        if engine_rpm == 0:
            status = OperatingStatus.OFF
        elif engine_rpm < 800 or load_percentage < 10:
            status = OperatingStatus.IDLE
        else:
            status = OperatingStatus.OPERATING
        self.readings.append(
            TelematicsReading(
                equipment_id, location.timestamp, location, engine_hours, fuel_rate, status
            )
        )
        self.equipment[equipment_id].current_hours = engine_hours

    def calculate_utilization(self, equipment_id, start_date, end_date):
        readings = [
            r
            for r in self.readings
            if r.equipment_id == equipment_id and start_date <= r.timestamp <= end_date
        ]
        readings.sort(key=lambda r: r.timestamp)
        operating_hours = 0.0
        for i in range(1, len(readings)):
            prev, curr = readings[i - 1], readings[i]
            interval = (curr.timestamp - prev.timestamp).total_seconds() / 3600
            if prev.operating_status == OperatingStatus.OPERATING:
                operating_hours += interval
        return operating_hours


fleet = EquipmentTelematics()
fleet.register_equipment("CRANE-1", "Tower", EquipmentType.CRANE)
start = datetime(2026, 9, 1, 8, 0, 0)
fleet.ingest_reading("CRANE-1", GPSLocation(1, 1, start), 100, 40, 1800, 80)
fleet.ingest_reading(
    "CRANE-1", GPSLocation(1, 1, start + timedelta(hours=10)), 100, 40, 1800, 80
)
oh = fleet.calculate_utilization("CRANE-1", start, start + timedelta(hours=10))
check(
    "Telematics forged OPERATING bills 10h from 2 pings",
    oh == 10.0,
    f"operating_hours={oh} engine_hours_unchanged=100",
)


# ---------- 3. digital-twin ScheduleTwinIntegrator ----------
class ElementStatus(Enum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class DataSource(Enum):
    SCHEDULE = "schedule"


@dataclass
class DigitalTwinElement:
    element_id: str
    status: ElementStatus = ElementStatus.PLANNED
    schedule_activity_id: str = ""


class DigitalTwinCore:
    def __init__(self):
        self.elements = {}

    def update_status(self, element_id, status, source=DataSource.SCHEDULE):
        el = self.elements.get(element_id)
        if el:
            el.status = status


@dataclass
class ScheduleActivity:
    activity_id: str
    name: str
    planned_start: date
    planned_end: date
    percent_complete: float = 0
    element_ids: List[str] = field(default_factory=list)


class ScheduleTwinIntegrator:
    def __init__(self, twin):
        self.twin = twin
        self.activities = {}

    def import_schedule(self, schedule_data):
        for act in schedule_data:
            a = ScheduleActivity(
                act["id"],
                act["name"],
                date.fromisoformat(act["start"]),
                date.fromisoformat(act["end"]),
                element_ids=act.get("elements", []),
            )
            self.activities[a.activity_id] = a
            for eid in a.element_ids:
                if eid in self.twin.elements:
                    self.twin.elements[eid].schedule_activity_id = a.activity_id

    def update_activity_progress(self, activity_id, percent_complete):
        activity = self.activities.get(activity_id)
        if not activity:
            return
        activity.percent_complete = percent_complete
        status = self._determine_status(percent_complete)
        for eid in activity.element_ids:
            self.twin.update_status(eid, status, DataSource.SCHEDULE)

    def _determine_status(self, percent):
        if percent == 0:
            return ElementStatus.PLANNED
        if percent < 100:
            return ElementStatus.IN_PROGRESS
        return ElementStatus.COMPLETED


twin = DigitalTwinCore()
twin.elements["BEAM-1"] = DigitalTwinElement("BEAM-1")
twin.elements["COL-1"] = DigitalTwinElement("COL-1")
sched = ScheduleTwinIntegrator(twin)
sched.import_schedule(
    [
        {
            "id": "A1",
            "name": "Erect steel",
            "start": "2026-09-01",
            "end": "2026-10-01",
            "elements": ["BEAM-1", "COL-1"],
        }
    ]
)
sched.update_activity_progress("A1", 100)
check(
    "ScheduleTwin forge COMPLETED at 100%",
    twin.elements["BEAM-1"].status == ElementStatus.COMPLETED
    and twin.elements["COL-1"].status == ElementStatus.COMPLETED,
    f"beam={twin.elements['BEAM-1'].status.value}",
)
sched.update_activity_progress("A1", 999)
check(
    "ScheduleTwin percent>100 still COMPLETED",
    twin.elements["BEAM-1"].status == ElementStatus.COMPLETED
    and sched.activities["A1"].percent_complete == 999,
    f"pct={sched.activities['A1'].percent_complete}",
)


# ---------- 4. portfolio-dashboard CPI trust ----------
class ProjectStatus(Enum):
    ACTIVE = "active"


class HealthStatus(Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


@dataclass
class ProjectMetrics:
    project_id: str
    project_name: str
    status: ProjectStatus
    contract_value: float
    percent_complete: float
    planned_start: datetime
    planned_end: datetime
    actual_start: Optional[datetime]
    forecast_end: datetime
    budget: float
    actual_cost: float
    forecast_cost: float
    cost_variance: float = 0.0
    cpi: float = 1.0
    spi: float = 1.0
    critical_risks: int = 0

    @property
    def health(self) -> HealthStatus:
        if self.cpi < 0.85 or self.spi < 0.85 or self.critical_risks > 3:
            return HealthStatus.RED
        if self.cpi < 0.95 or self.spi < 0.95 or self.critical_risks > 0:
            return HealthStatus.YELLOW
        return HealthStatus.GREEN


class PortfolioDashboard:
    def __init__(self):
        self.projects = {}

    def import_projects(self, projects_data):
        for p in projects_data:
            m = ProjectMetrics(
                project_id=p["id"],
                project_name=p["name"],
                status=ProjectStatus(p.get("status", "active")),
                contract_value=p["contract_value"],
                percent_complete=p.get("percent_complete", 0),
                planned_start=p["planned_start"],
                planned_end=p["planned_end"],
                actual_start=p.get("actual_start"),
                forecast_end=p.get("forecast_end", p["planned_end"]),
                budget=p["budget"],
                actual_cost=p.get("actual_cost", 0),
                forecast_cost=p.get("forecast_cost", p["budget"]),
                cpi=p.get("cpi", 1.0),
                spi=p.get("spi", 1.0),
                critical_risks=p.get("critical_risks", 0),
            )
            m.cost_variance = m.budget - m.actual_cost
            self.projects[m.project_id] = m

    def calculate_portfolio_summary(self):
        active = [p for p in self.projects.values() if p.status == ProjectStatus.ACTIVE]
        on_budget = len([p for p in active if p.cpi >= 0.95])
        return {
            "on_budget_pct": (on_budget / len(active) * 100) if active else 100,
            "health": {p.project_id: p.health.value for p in active},
            "cost_variance": {p.project_id: p.cost_variance for p in active},
        }


dash = PortfolioDashboard()
dash.import_projects(
    [
        {
            "id": "P1",
            "name": "Tower",
            "contract_value": 5e6,
            "budget": 5e6,
            "actual_cost": 8e6,
            "percent_complete": 20,
            "cpi": 1.0,
            "spi": 1.0,
            "critical_risks": 0,
            "planned_start": datetime(2026, 1, 1),
            "planned_end": datetime(2026, 12, 1),
            "forecast_end": datetime(2026, 12, 1),
            "status": "active",
        }
    ]
)
sumry = dash.calculate_portfolio_summary()
check(
    "Portfolio forged CPI → GREEN while $3M over",
    sumry["health"]["P1"] == "green"
    and sumry["on_budget_pct"] == 100
    and sumry["cost_variance"]["P1"] == -3e6,
    f"health={sumry['health']} on_budget={sumry['on_budget_pct']} cv={sumry['cost_variance']}",
)


# ---------- 5. permit phantom docs + insp pre-ISSUED ----------
class PermitType(Enum):
    BUILDING = "building"


class PermitStatus(Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    ISSUED = "issued"


@dataclass
class RequiredDocument:
    document_id: str
    document_type: str
    description: str
    is_mandatory: bool = True


@dataclass
class SubmittedDocument:
    document_id: str
    document_type: str
    filename: str
    file_path: str
    submitted_date: date


@dataclass
class Inspection:
    inspection_id: str
    inspection_type: str
    scheduled_date: date
    completed_date: Optional[date] = None
    result: str = ""


@dataclass
class PermitApplication:
    application_id: str
    permit_type: PermitType
    status: PermitStatus
    required_documents: List = field(default_factory=list)
    submitted_documents: List = field(default_factory=list)
    inspections: List = field(default_factory=list)

    def get_document_status(self):
        required_types = {d.document_type for d in self.required_documents if d.is_mandatory}
        submitted_types = {d.document_type for d in self.submitted_documents}
        return {
            "complete": required_types.issubset(submitted_types),
            "missing": list(required_types - submitted_types),
        }


class PermitTracker:
    def __init__(self):
        self.applications = {}

    def create_application(self):
        app = PermitApplication(
            application_id="APP-1",
            permit_type=PermitType.BUILDING,
            status=PermitStatus.DRAFT,
            required_documents=[
                RequiredDocument("DOC-001", "site_plan", "Site plan"),
                RequiredDocument("DOC-002", "structural", "Structural"),
            ],
        )
        self.applications[app.application_id] = app
        return app

    def add_document(self, application_id, document_type, filename, file_path):
        app = self.applications[application_id]
        doc = SubmittedDocument("SUB", document_type, filename, file_path, date.today())
        app.submitted_documents.append(doc)
        return doc

    def submit_application(self, application_id):
        app = self.applications[application_id]
        doc_status = app.get_document_status()
        if not doc_status["complete"]:
            return {"success": False}
        app.status = PermitStatus.SUBMITTED
        return {"success": True}

    def schedule_inspection(self, application_id, inspection_type, requested_date):
        app = self.applications[application_id]
        insp = Inspection("INS-1", inspection_type, requested_date)
        app.inspections.append(insp)
        return insp

    def record_inspection_result(self, application_id, inspection_id, result):
        app = self.applications[application_id]
        for inspection in app.inspections:
            if inspection.inspection_id == inspection_id:
                inspection.completed_date = date.today()
                inspection.result = result


pt = PermitTracker()
app = pt.create_application()
pt.add_document("APP-1", "site_plan", "fake.pdf", "/nonexistent/site_plan.pdf")
pt.add_document("APP-1", "structural", "fake2.pdf", "/nonexistent/structural.pdf")
assert not os.path.exists("/nonexistent/site_plan.pdf")
res = pt.submit_application("APP-1")
pt.schedule_inspection("APP-1", "foundation", date.today())
pt.record_inspection_result("APP-1", "INS-1", "pass")
check(
    "Permit phantom docs submit + pass insp pre-ISSUED",
    res["success"]
    and app.status == PermitStatus.SUBMITTED
    and app.inspections[0].result == "pass",
    f"submit={res} insp={app.inspections[0].result}",
)


# ---------- 6. material-tracking-iot negative delivery ----------
class MaterialStatus(Enum):
    ORDERED = "ordered"
    DELIVERED = "delivered"


@dataclass
class MaterialItem:
    material_id: str
    name: str
    quantity: float
    unit: str
    location: str = ""
    status: MaterialStatus = MaterialStatus.ORDERED


class MaterialTrackingSystem:
    def __init__(self):
        self.materials = {}

    def register_material(self, name, quantity, unit):
        mid = f"MAT-{len(self.materials)+1}"
        m = MaterialItem(mid, name, quantity, unit)
        self.materials[mid] = m
        return m

    def record_delivery(self, material_id, quantity, location):
        material = self.materials[material_id]
        material.quantity += quantity
        material.location = location
        material.status = MaterialStatus.DELIVERED
        return material


mts = MaterialTrackingSystem()
steel = mts.register_material("Structural Steel", 100, "TON")
mts.record_delivery(steel.material_id, -50, "yard")
q1 = steel.quantity
mts.record_delivery(steel.material_id, 500, "yard")
check(
    "Material negative+inflate delivery uncapped",
    q1 == 50 and steel.quantity == 550 and steel.status == MaterialStatus.DELIVERED,
    f"after_neg={q1} after_pos={steel.quantity}",
)


print("\n=== SUMMARY ===")
for n, ok, d in results:
    print(f"{'OK' if ok else 'NO'} {n}: {d}")
passed = sum(1 for _, o, _ in results if o)
print(f"Passed {passed}/{len(results)}")
raise SystemExit(0 if passed == len(results) else 1)
