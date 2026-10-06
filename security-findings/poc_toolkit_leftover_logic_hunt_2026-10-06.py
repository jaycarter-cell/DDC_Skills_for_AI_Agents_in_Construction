#!/usr/bin/env python3
"""PoC: 1_DDC_Toolkit leftover skills business-logic hunt (2026-10-06).

Validates 5 MEDIUM+ findings. Run: python3 security-findings/poc_toolkit_leftover_logic_hunt_2026-10-06.py
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


passed = 0
failed = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, failed
    if cond:
        passed += 1
        print(f"PASS: {name}" + (f" ({detail})" if detail else ""))
    else:
        failed += 1
        print(f"FAIL: {name}" + (f" ({detail})" if detail else ""))


# ---------------------------------------------------------------------------
# F1 + F2: material-tracker (from SKILL.md)
# ---------------------------------------------------------------------------
class OrderStatus(Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    DELIVERED = "delivered"
    PARTIAL = "partial"
    CANCELLED = "cancelled"


class PriorityLevel(Enum):
    NORMAL = "normal"


@dataclass
class MaterialOrder:
    order_id: str
    material_code: str
    material_name: str
    supplier: str
    quantity: float
    unit: str
    unit_cost: float
    total_cost: float
    order_date: date
    required_date: date
    expected_delivery: date
    actual_delivery: Optional[date]
    status: OrderStatus
    priority: PriorityLevel
    delivered_qty: float = 0
    notes: str = ""


@dataclass
class InventoryItem:
    material_code: str
    material_name: str
    current_stock: float
    unit: str
    min_stock: float
    max_stock: float
    reorder_point: float
    location: str
    last_updated: date


@dataclass
class Delivery:
    delivery_id: str
    order_id: str
    delivery_date: date
    quantity: float
    received_by: str
    condition: str
    notes: str = ""


class MaterialTracker:
    def __init__(self, project_name: str):
        self.project_name = project_name
        self.orders: Dict[str, MaterialOrder] = {}
        self.inventory: Dict[str, InventoryItem] = {}
        self.deliveries: List[Delivery] = []

    def create_order(
        self,
        order_id: str,
        material_code: str,
        material_name: str,
        supplier: str,
        quantity: float,
        unit: str,
        unit_cost: float,
        required_date: date,
        lead_time_days: int = 14,
        priority: PriorityLevel = PriorityLevel.NORMAL,
    ) -> MaterialOrder:
        order = MaterialOrder(
            order_id=order_id,
            material_code=material_code,
            material_name=material_name,
            supplier=supplier,
            quantity=quantity,
            unit=unit,
            unit_cost=unit_cost,
            total_cost=round(quantity * unit_cost, 2),
            order_date=date.today(),
            required_date=required_date,
            expected_delivery=date.today() + timedelta(days=lead_time_days),
            actual_delivery=None,
            status=OrderStatus.DRAFT,
            priority=priority,
        )
        self.orders[order_id] = order
        return order

    def update_order_status(self, order_id: str, status: OrderStatus) -> None:
        if order_id in self.orders:
            self.orders[order_id].status = status

    def record_delivery(
        self,
        order_id: str,
        quantity: float,
        received_by: str,
        condition: str = "good",
        notes: str = "",
    ) -> Optional[Delivery]:
        if order_id not in self.orders:
            return None
        order = self.orders[order_id]
        delivery = Delivery(
            delivery_id=f"DEL-{len(self.deliveries)+1:04d}",
            order_id=order_id,
            delivery_date=date.today(),
            quantity=quantity,
            received_by=received_by,
            condition=condition,
            notes=notes,
        )
        self.deliveries.append(delivery)
        order.delivered_qty += quantity
        order.actual_delivery = date.today()
        if order.delivered_qty >= order.quantity:
            order.status = OrderStatus.DELIVERED
        else:
            order.status = OrderStatus.PARTIAL
        if order.material_code in self.inventory:
            self.inventory[order.material_code].current_stock += quantity
            self.inventory[order.material_code].last_updated = date.today()
        return delivery

    def add_inventory_item(
        self,
        material_code: str,
        material_name: str,
        current_stock: float,
        unit: str,
        min_stock: float,
        max_stock: float,
        location: str,
    ) -> None:
        reorder_point = min_stock + (max_stock - min_stock) * 0.3
        self.inventory[material_code] = InventoryItem(
            material_code=material_code,
            material_name=material_name,
            current_stock=current_stock,
            unit=unit,
            min_stock=min_stock,
            max_stock=max_stock,
            reorder_point=reorder_point,
            location=location,
            last_updated=date.today(),
        )

    def consume_material(self, material_code: str, quantity: float, activity: str = "") -> bool:
        if material_code not in self.inventory:
            return False
        item = self.inventory[material_code]
        if item.current_stock < quantity:
            return False
        item.current_stock -= quantity
        item.last_updated = date.today()
        return True


def poc_f1_consume_negative() -> None:
    t = MaterialTracker("PoC")
    t.add_inventory_item("STEEL", "Steel", 100.0, "ton", 10, 200, "Yard")
    ok = t.consume_material("STEEL", -500)
    check(
        "F1 consume_material(-500) inflates stock 100→600",
        ok is True and t.inventory["STEEL"].current_stock == 600.0,
        f"stock={t.inventory['STEEL'].current_stock}",
    )


def poc_f2_create_order_overwrite() -> None:
    t = MaterialTracker("PoC")
    t.create_order(
        "PO-001", "CONC", "Concrete", "VendorA", 200, "m3", 150, date.today() + timedelta(days=10)
    )
    t.update_order_status("PO-001", OrderStatus.CONFIRMED)
    t.record_delivery("PO-001", 200, "Recv")
    assert t.orders["PO-001"].status == OrderStatus.DELIVERED
    t.create_order(
        "PO-001", "CONC", "Cheap", "Attacker", 1, "m3", 1, date.today() + timedelta(days=10)
    )
    o = t.orders["PO-001"]
    check(
        "F2 create_order overwrites DELIVERED PO → DRAFT $1",
        o.status == OrderStatus.DRAFT
        and o.total_cost == 1.0
        and o.delivered_qty == 0
        and o.supplier == "Attacker",
        f"status={o.status.value} cost={o.total_cost} supplier={o.supplier}",
    )


# ---------------------------------------------------------------------------
# F3: material-procurement-tracker issue_po
# ---------------------------------------------------------------------------
class ProcurementStatus(Enum):
    REQUISITIONED = "requisitioned"
    PO_ISSUED = "po_issued"
    DELIVERED = "delivered"


class Priority(Enum):
    NORMAL = "normal"


@dataclass
class ProcurementItem:
    item_id: str
    description: str
    spec_section: str
    quantity: float
    unit: str
    required_date: date
    lead_time_days: int
    status: ProcurementStatus
    priority: Priority
    vendor: str = ""
    po_number: str = ""
    po_amount: float = 0.0
    order_date: Optional[date] = None
    expected_delivery: Optional[date] = None
    actual_delivery: Optional[date] = None


class MaterialProcurementTracker:
    def __init__(self, project_name: str):
        self.project_name = project_name
        self.items: Dict[str, ProcurementItem] = {}
        self._counter = 0

    def add_item(
        self,
        description: str,
        spec_section: str,
        quantity: float,
        unit: str,
        required_date: date,
        lead_time_days: int,
        priority: Priority = Priority.NORMAL,
    ) -> ProcurementItem:
        self._counter += 1
        item_id = f"PROC-{self._counter:04d}"
        item = ProcurementItem(
            item_id=item_id,
            description=description,
            spec_section=spec_section,
            quantity=quantity,
            unit=unit,
            required_date=required_date,
            lead_time_days=lead_time_days,
            status=ProcurementStatus.REQUISITIONED,
            priority=priority,
        )
        self.items[item_id] = item
        return item

    def issue_po(
        self,
        item_id: str,
        vendor: str,
        po_number: str,
        amount: float,
        expected_delivery: date,
    ) -> None:
        if item_id in self.items:
            item = self.items[item_id]
            item.status = ProcurementStatus.PO_ISSUED
            item.vendor = vendor
            item.po_number = po_number
            item.po_amount = amount
            item.order_date = date.today()
            item.expected_delivery = expected_delivery

    def get_summary(self) -> Dict[str, Any]:
        return {"total_po_value": sum(i.po_amount for i in self.items.values())}


def poc_f3_issue_po() -> None:
    mp = MaterialProcurementTracker("PoC")
    item = mp.add_item("Steel", "05", 100, "TON", date(2024, 6, 1), 90)
    mp.issue_po(item.item_id, "GoodVendor", "PO-1", 450000, date(2024, 5, 15))
    mp.issue_po(item.item_id, "Attacker", "PO-FAKE", -450000, date(2024, 5, 15))
    check(
        "F3a re-issue_po with negative amount wipes commitment",
        mp.items[item.item_id].po_amount == -450000
        and mp.get_summary()["total_po_value"] == -450000
        and mp.items[item.item_id].vendor == "Attacker",
        f"amount={mp.items[item.item_id].po_amount}",
    )

    mp2 = MaterialProcurementTracker("PoC")
    item2 = mp2.add_item("Steel", "05", 100, "TON", date(2024, 6, 1), 90)
    mp2.issue_po(item2.item_id, "Attacker", "PO-X", 9_999_999, date(2024, 5, 1))
    check(
        "F3b issue_po from REQUISITIONED with unbounded amount",
        mp2.items[item2.item_id].status == ProcurementStatus.PO_ISSUED
        and mp2.get_summary()["total_po_value"] == 9_999_999,
        f"status={mp2.items[item2.item_id].status.value}",
    )


# ---------------------------------------------------------------------------
# F4: subcontractor-prequalification EMR + documents ignored
# ---------------------------------------------------------------------------
class QualificationStatus(Enum):
    PENDING = "pending"
    QUALIFIED = "qualified"
    CONDITIONALLY_QUALIFIED = "conditionally_qualified"
    NOT_QUALIFIED = "not_qualified"


@dataclass
class PrequalificationCriteria:
    name: str
    weight: float
    min_score: int
    max_score: int = 10


@dataclass
class SubcontractorApplication:
    app_id: str
    company_name: str
    trade: str
    contact_email: str
    years_in_business: int
    annual_revenue: float
    bonding_capacity: float
    emr_rate: float
    status: QualificationStatus
    scores: Dict[str, int] = field(default_factory=dict)
    documents_received: List[str] = field(default_factory=list)
    notes: str = ""

    @property
    def total_score(self) -> float:
        return sum(self.scores.values())


class SubcontractorPrequalification:
    def __init__(self, project_name: str):
        self.project_name = project_name
        self.applications: Dict[str, SubcontractorApplication] = {}
        self.criteria = self._default_criteria()
        self._counter = 0

    def _default_criteria(self) -> List[PrequalificationCriteria]:
        return [
            PrequalificationCriteria("Safety Record", 0.25, 6),
            PrequalificationCriteria("Financial Stability", 0.20, 5),
            PrequalificationCriteria("Experience", 0.20, 6),
            PrequalificationCriteria("References", 0.15, 5),
            PrequalificationCriteria("Capacity", 0.10, 5),
            PrequalificationCriteria("Insurance/Bonding", 0.10, 7),
        ]

    def add_application(
        self,
        company_name: str,
        trade: str,
        contact_email: str,
        years_in_business: int,
        annual_revenue: float,
        bonding_capacity: float,
        emr_rate: float,
    ) -> SubcontractorApplication:
        self._counter += 1
        app_id = f"PQ-{self._counter:03d}"
        app = SubcontractorApplication(
            app_id=app_id,
            company_name=company_name,
            trade=trade,
            contact_email=contact_email,
            years_in_business=years_in_business,
            annual_revenue=annual_revenue,
            bonding_capacity=bonding_capacity,
            emr_rate=emr_rate,
            status=QualificationStatus.PENDING,
        )
        self.applications[app_id] = app
        return app

    def score_application(self, app_id: str, scores: Dict[str, int]) -> None:
        if app_id not in self.applications:
            return
        app = self.applications[app_id]
        app.scores = scores
        self._evaluate_qualification(app)

    def _evaluate_qualification(self, app: SubcontractorApplication) -> None:
        passed = True
        for criteria in self.criteria:
            score = app.scores.get(criteria.name, 0)
            if score < criteria.min_score:
                passed = False
                break
        if passed and app.total_score >= 60:
            app.status = QualificationStatus.QUALIFIED
        elif app.total_score >= 50:
            app.status = QualificationStatus.CONDITIONALLY_QUALIFIED
        else:
            app.status = QualificationStatus.NOT_QUALIFIED


def poc_f4_prequal_emr_docs() -> None:
    pq = SubcontractorPrequalification("PoC")
    app = pq.add_application(
        "DangerousCo", "Electrical", "a@b.com", 1, 1, 1, emr_rate=5.0
    )
    pq.score_application(
        app.app_id,
        {
            "Safety Record": 10,
            "Financial Stability": 10,
            "Experience": 10,
            "References": 10,
            "Capacity": 10,
            "Insurance/Bonding": 10,
        },
    )
    check(
        "F4 EMR=5.0 + empty documents still QUALIFIED",
        app.status == QualificationStatus.QUALIFIED
        and app.emr_rate == 5.0
        and app.documents_received == [],
        f"status={app.status.value} emr={app.emr_rate} docs={app.documents_received}",
    )


# ---------------------------------------------------------------------------
# F5: bim-clash-detection resolve_clash
# ---------------------------------------------------------------------------
class ClashType(Enum):
    HARD = "hard"


class ClashStatus(Enum):
    NEW = "new"
    RESOLVED = "resolved"


class ClashSeverity(Enum):
    CRITICAL = "critical"


class Discipline(Enum):
    MECHANICAL = "mechanical"
    STRUCTURAL = "structural"


@dataclass
class BoundingBox:
    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float


@dataclass
class BIMElement:
    element_id: str
    name: str
    discipline: Discipline
    category: str
    level: str
    bounding_box: BoundingBox


@dataclass
class Clash:
    clash_id: str
    element_a: BIMElement
    element_b: BIMElement
    clash_type: ClashType
    severity: ClashSeverity
    status: ClashStatus
    distance: float
    location: Tuple[float, float, float]
    detected_at: datetime
    resolved_at: Optional[datetime] = None
    notes: str = ""


class BIMClashDetector:
    def __init__(self) -> None:
        self.clashes: List[Clash] = []

    def resolve_clash(self, clash_id: str, resolution_note: str) -> None:
        for clash in self.clashes:
            if clash.clash_id == clash_id:
                clash.status = ClashStatus.RESOLVED
                clash.resolved_at = datetime.now()
                clash.notes = resolution_note
                break

    def get_summary(self) -> Dict[str, Any]:
        by_status: Dict[str, int] = {}
        for clash in self.clashes:
            by_status[clash.status.value] = by_status.get(clash.status.value, 0) + 1
        return {"by_status": by_status}


def poc_f5_clash_resolve() -> None:
    det = BIMClashDetector()
    ea = BIMElement(
        "D1", "Duct", Discipline.MECHANICAL, "Duct", "L2", BoundingBox(0, 0, 0, 1, 1, 1)
    )
    eb = BIMElement(
        "B1", "Beam", Discipline.STRUCTURAL, "Beam", "L2", BoundingBox(0.5, 0.5, 0.5, 1.5, 1.5, 1.5)
    )
    det.clashes.append(
        Clash(
            "CLH-1",
            ea,
            eb,
            ClashType.HARD,
            ClashSeverity.CRITICAL,
            ClashStatus.NEW,
            0.05,
            (0.7, 0.7, 0.7),
            datetime.now(),
        )
    )
    det.resolve_clash("CLH-1", "looks fine")
    check(
        "F5 CRITICAL NEW clash forged to RESOLVED with free-text note",
        det.clashes[0].status == ClashStatus.RESOLVED
        and det.get_summary()["by_status"].get("resolved") == 1,
        f"status={det.clashes[0].status.value}",
    )


if __name__ == "__main__":
    poc_f1_consume_negative()
    poc_f2_create_order_overwrite()
    poc_f3_issue_po()
    poc_f4_prequal_emr_docs()
    poc_f5_clash_resolve()
    print(f"\nRESULT: {passed} passed, {failed} failed")
    raise SystemExit(0 if failed == 0 else 1)
