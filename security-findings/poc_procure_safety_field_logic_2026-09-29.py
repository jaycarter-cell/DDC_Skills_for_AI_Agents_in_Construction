#!/usr/bin/env python3
"""PoC: NEW logic bugs in procure/safety/field/closeout SKILL templates (2026-09-29)."""
from datetime import date, datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

passed = failed = 0

def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"PASS {name}: {detail}")
    else:
        failed += 1
        print(f"FAIL {name}: {detail}")

# --- 1 CRITICAL: QC acceptance_criteria ignored ---
class QCStatus(Enum):
    PASSED = "passed"; FAILED = "failed"; PENDING = "pending"

@dataclass
class InspectionPoint:
    id: str; name: str; spec_reference: str; acceptance_criteria: str
    inspection_method: str; hold_point: bool = False

@dataclass
class QCInspection:
    id: str; inspection_point: InspectionPoint; location: str
    scheduled_date: datetime; inspector: str
    status: QCStatus = QCStatus.PENDING
    measurements: Dict[str, float] = field(default_factory=dict)
    result: str = ""

def conduct_inspection(inspection, result, measurements=None):
    # Mirrors SKILL.md:165-179 — status from result string only
    inspection.result = result
    inspection.measurements = measurements or {}
    inspection.status = QCStatus.PASSED if result == "pass" else QCStatus.FAILED
    return inspection

ip = InspectionPoint("CONC-001", "Slump", "03300", "Slump 4-6 inches", "Test")
insp = QCInspection("QCI-1", ip, "L3", datetime.now(), "QC")
conduct_inspection(insp, "pass", {"slump_inches": 12.0})
check("qc-criteria-ignored",
      insp.status == QCStatus.PASSED and insp.measurements["slump_inches"] == 12.0,
      f"status={insp.status.value} slump=12 criteria={ip.acceptance_criteria}")

# --- 2 HIGH: material-delivery forge DELIVERED ---
class DeliveryStatus(Enum):
    SCHEDULED = "scheduled"; DELIVERED = "delivered"; DELAYED = "delayed"
    IN_TRANSIT = "in_transit"

@dataclass
class MaterialItem:
    item_id: str; quantity_ordered: float; quantity_received: float = 0
    @property
    def is_complete(self):
        return self.quantity_received >= self.quantity_ordered

@dataclass
class Delivery:
    delivery_id: str; scheduled_date: date; status: DeliveryStatus
    items: List[MaterialItem]

def get_delayed(deliveries):
    today = date.today()
    return [d for d in deliveries
            if d.status in [DeliveryStatus.SCHEDULED, DeliveryStatus.IN_TRANSIT, DeliveryStatus.DELAYED]
            and d.scheduled_date < today]

d1 = Delivery("DEL-1", date.today() - timedelta(days=10), DeliveryStatus.SCHEDULED,
              [MaterialItem("DEL-1-001", 500)])
assert len(get_delayed([d1])) == 1
d1.status = DeliveryStatus.DELIVERED  # update_status forge
check("delivery-forge-status",
      len(get_delayed([d1])) == 0 and d1.items[0].quantity_received == 0,
      f"status={d1.status.value} qty_recv=0 overdue=0")

d2 = Delivery("DEL-2", date.today(), DeliveryStatus.SCHEDULED, [])
# receive_delivery vacuous all([])
all_complete = all(i.is_complete for i in d2.items)
d2.status = DeliveryStatus.DELIVERED if all_complete else DeliveryStatus.SCHEDULED
check("delivery-empty-vacuous", d2.status == DeliveryStatus.DELIVERED and len(d2.items) == 0,
      "empty items → DELIVERED")

# --- 3 HIGH: damaged stocks inventory ---
stock = 100.0
condition = "damaged"
quantity = 50.0
# record_delivery always adds qty
stock += quantity
check("damaged-stocks-inventory", stock == 150.0 and condition == "damaged",
      f"stock={stock} condition={condition}")

# --- 4 HIGH: warranty pre-start claim ---
start = date(2024, 6, 1)
end = start + timedelta(days=5 * 365)
today = date.today()
status = "expired" if today > end else ("expiring_soon" if (end - today).days <= 90 else "active")
issue_date = start - timedelta(days=400)
# file_claim only blocks EXPIRED
accepted = status != "expired"
check("warranty-prestart-claim",
      accepted and issue_date < start and status == "active",
      f"issue={issue_date} start={start} warranty_status={status}")

# --- 5 HIGH: RFI impact forge from DRAFT ---
rfi_status = "Draft"
cost_amount = 5_000_000.0
schedule_days = 365
# respond_to_rfi: no status gate
rfi_status = "Answered"
total_cost = cost_amount
total_days = schedule_days
check("rfi-draft-impact-forge",
      rfi_status == "Answered" and total_cost == 5_000_000 and total_days == 365,
      f"DRAFT→Answered cost={total_cost} days={total_days}")

print(f"\nRESULT: {passed} passed, {failed} failed")
raise SystemExit(0 if failed == 0 else 1)
