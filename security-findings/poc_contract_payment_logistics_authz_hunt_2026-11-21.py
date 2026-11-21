#!/usr/bin/env python3
"""Non-destructive PoCs for contract/payment/logistics authz hunt 2026-11-21."""
from __future__ import annotations

import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def blocks(skill: str):
    text = (ROOT / skill / "SKILL.md").read_text()
    return re.findall(r"```(?:python|py)\n(.*?)```", text, re.S | re.I)


def pass_(name: str, detail: str):
    print(f"PASS {name}: {detail}")


def fail(name: str, detail: str):
    print(f"FAIL {name}: {detail}")
    sys.exit(1)


def poc_change_order_processor():
    ns: dict = {}
    exec(blocks("1_DDC_Toolkit/Cost-Management/change-order-processor")[0], ns)
    proc = ns["ChangeOrderProcessor"]("Tower", 5_000_000)
    ct = list(ns["ChangeType"])[0]
    co = proc.create_change_order("Extra steel", "add", ct, "attacker")
    proc.add_cost_item(co.co_number, "steel", 100, "ton", 2500, "materials")
    proc.approve_change_order(co.co_number, "attacker", "anyone")
    co = proc.change_orders[co.co_number]
    if co.status.value != "approved" or co.total_cost < 300000:
        fail("COP", f"{co.status} {co.total_cost}")
    co2 = proc.create_change_order("Bad", "x", ct, "a")
    proc.reject_change_order(co2.co_number, "pm", "no")
    proc.approve_change_order(co2.co_number, "attacker", "Owner")
    if proc.change_orders[co2.co_number].status.value != "approved":
        fail("COP-reject", "not approved")
    pass_("COP", f"DRAFT→APPROVED ${co.total_cost:.0f}; REJECTED→APPROVED")


def poc_change_order_manager():
    ns: dict = {}
    exec(blocks("4_DDC_Curated/Contract-Legal/change-order-manager")[0], ns)
    mgr = ns["ChangeOrderManager"]("P1", "Tower", 1_000_000)
    co = mgr.create_change_order("Bogus", "no backup", ns["ChangeType"].OWNER_DIRECTED, "attacker")
    mgr.approve_change_order(co.id, approved_amount=2_500_000, approved_time=120)
    co = mgr.change_orders[co.id]
    s = mgr.get_summary()
    if co.status.value != "approved" or s.get("total_approved") != 2_500_000:
        fail("COM", str(s))
    if co.photo_attachments or co.backup_documents:
        fail("COM-docs", "expected empty evidence")
    pass_("COM", f"DRAFT→APPROVED ${co.approved_amount}; revised={s.get('revised_contract')}")


def poc_lien_waiver():
    ns: dict = {}
    exec(blocks("4_DDC_Curated/Contract-Legal/lien-waiver-tracker")[0], ns)
    t = ns["LienWaiverTracker"]("P1", "Tower")
    t.add_subcontractor("SUB-001", "Risky", "Structural", 500000, "A", "a@x.com")
    t.create_payment_application(1, datetime.now(), "SUB-001", 100000)
    t.receive_waiver("LW-SUB-001-1", file_path="")
    rel = t.can_release_payment("SUB-001", 1)
    if not rel.get("can_release"):
        fail("LIEN", str(rel))
    t2 = ns["LienWaiverTracker"]("P2", "Tower")
    t2.add_subcontractor("SUB-001", "Risky", "Structural", 500000, "A", "a@x.com")
    t2.create_payment_application(1, datetime.now(), "SUB-001", 50000)
    t2.verify_waiver("LW-SUB-001-1", "forger")
    rel2 = t2.can_release_payment("SUB-001", 1)
    if not rel2.get("can_release") or t2.waivers["LW-SUB-001-1"].file_path:
        fail("LIEN-verify", str(rel2))
    pass_("LIEN", f"empty RECEIVED release={rel['amount']}; skip-file VERIFIED release={rel2['amount']}")


def poc_sub_payment():
    ns: dict = {}
    exec(blocks("1_DDC_Toolkit/Cost-Management/subcontractor-payment-tracker")[0], ns)
    tr = ns["SubcontractorPaymentTracker"]("Tower")
    sub = tr.add_subcontractor("Bad Co", "X", "x@x.com", "555", 500000, "Steel")
    pay = tr.record_invoice(sub.sub_id, "INV-1", date.today(), 450000)
    tr.record_payment(pay.payment_id, sub.sub_id, "CHK-1")
    pay2 = tr.record_invoice(sub.sub_id, "INV-2", date.today(), 450000)
    tr.record_payment(pay2.payment_id, sub.sub_id, "CHK-2")
    s = tr.subcontractors[sub.sub_id]
    if s.total_paid <= s.contract_amount or s.payments[0].lien_waiver is not None:
        fail("SUBPAY", f"paid={s.total_paid}")
    if s.insurance_expiry is not None:
        fail("SUBPAY-ins", "insurance set")
    pass_("SUBPAY", f"PAID ${s.total_paid} on ${s.contract_amount}; missing_waivers={len(tr.get_missing_waivers())}")


def poc_crane():
    pre = (
        "from dataclasses import dataclass, field\nfrom typing import *\n"
        "from datetime import datetime, date, timedelta\nfrom enum import Enum\nimport numpy as np\n"
    )
    bs = blocks("5_DDC_Innovative/site-logistics-optimization")
    ns: dict = {}
    exec(pre + bs[1] + "\n" + bs[2], ns)
    site = ns["SiteLogisticsModel"]("Site")
    site.add_zone(ns["SiteZone"]("Z1", ns["ZoneType"].STORAGE, 100, 100, position=(50, 0)))
    site.add_equipment(ns["Equipment"]("CR1", "crane", max_reach=100, capacity=5.0, position=(0, 0)))
    d1 = ns["DeliveryRequest"](
        "D1", "structural_steel", 40, "tons", date.today() + timedelta(1),
        (8, 16), 60, "truck", "Z1", 1, True,
    )
    d2 = ns["DeliveryRequest"](
        "D2", "steel2", 35, "tons", date.today() + timedelta(1),
        (8, 16), 90, "truck", "Z1", 1, True,
    )
    sched = ns["DeliveryScheduler"](site)
    out = sched.schedule_deliveries([d1, d2])
    if not out or out[0].assigned_crane != "CR1" or out[0].delivery.quantity > site.equipment["CR1"].capacity:
        # assignment of under-capacity crane is the bug — assert that happened
        pass
    if out[0].assigned_crane != "CR1" or out[0].delivery.quantity != 40:
        fail("CRANE", str(out))
    if site.equipment["CR1"].capacity >= 40:
        fail("CRANE-setup", "capacity should be 5")
    pass_("CRANE", f"5t crane assigned to {out[0].delivery.quantity}t and {out[1].delivery.quantity}t")


def poc_material_sub():
    import pandas as pd

    ns: dict = {}
    exec(blocks("1_DDC_Toolkit/CWICR-Database/cwicr-material-substitution")[0], ns)
    df = pd.DataFrame(
        [
            {"work_item_code": "C40", "description": "Concrete C40 structural", "material_cost": 120, "unit": "m3"},
            {"work_item_code": "C20", "description": "Concrete C20 lean", "material_cost": 70, "unit": "m3"},
            {"work_item_code": "S355", "description": "Steel S355 beam", "material_cost": 900, "unit": "t"},
            {"work_item_code": "S235", "description": "Steel S235 beam", "material_cost": 700, "unit": "t"},
        ]
    )
    finder = ns["CWICRMaterialSubstitution"](df)
    batch = finder.batch_substitution(
        [{"code": "C40", "quantity": 500}, {"code": "S355", "quantity": 200}]
    )
    codes = {m["code"]: m["best_substitute"] for m in batch["materials"]}
    if codes.get("C40") != "C20" or codes.get("S355") != "S235":
        fail("SUB", str(codes))
    pass_("SUB", f"best_substitutes={codes}; savings=${batch['total_potential_savings']}")


def poc_safety():
    bs = blocks("1_DDC_Toolkit/Field-Operations/safety-inspection")
    ns: dict = {}
    exec("\n\n".join(bs), ns)
    sm = ns["SafetyManager"]("P1")
    ins = sm.create_inspection(ns["InspectionType"].DAILY_PREWORK, "attacker", "Shaft")
    stats = sm.get_statistics(30)
    h = sm.add_hazard(ins.inspection_id, "Missing fall protection", ns["HazardSeverity"].CRITICAL, "Shaft")
    sm.correct_hazard(h.hazard_id, "done", "attacker")
    sm.verify_hazard_closure(h.hazard_id, "attacker")
    h2 = sm.hazards[h.hazard_id]
    checklist_done = all(i["result"] for i in ins.checklist_items)
    if stats["inspections_completed"] != 1 or checklist_done or h2.photo_urls:
        fail("SAFETY", f"{stats} {checklist_done} {h2.photo_urls}")
    pass_("SAFETY", f"inspections_completed=1 checklist_done=False; CRITICAL {h2.status.value} photos=[]")


def poc_env():
    ns: dict = {}
    exec(blocks("5_DDC_Innovative/environmental-monitoring")[0], ns)
    mon = ns["EnvironmentalMonitor"]("Site")
    params = list(ns["ParameterType"])[:2]
    mon.add_station("S1", "North", {"lat": 0, "lon": 0}, params)
    rep = mon.generate_daily_report()
    n = mon.record_batch(
        [{"station_id": "NOPE", "parameter": params[0].value, "value": 999, "unit": "x"}]
    )
    if rep.compliance_status.value != "compliant" or rep.readings_collected != 0 or n != 0:
        fail("ENV", f"{rep.compliance_status} readings={rep.readings_collected} swallowed={n}")
    pass_("ENV", "0 readings → compliant; bad batch swallowed")


def poc_delivery():
    ns: dict = {}
    exec(blocks("1_DDC_Toolkit/Cost-Management/material-delivery-tracker")[0], ns)
    tr = ns["MaterialDeliveryTracker"]("Tower")
    d = tr.schedule_delivery("PO-1", "Vendor", date.today(), "Gate", "Yard")
    tr.add_item(d.delivery_id, "W14", 100, "ton", list(ns["MaterialCategory"])[0])
    tr.update_status(d.delivery_id, ns["DeliveryStatus"].DELIVERED)
    dd = tr.deliveries[d.delivery_id]
    if dd.status.value != "delivered" or dd.receiver or dd.items[0].quantity_received:
        fail("DELIV", str(dd))
    pass_("DELIV", "DELIVERED with empty receiver and qty_received=0")


def poc_procure():
    ns: dict = {}
    exec(blocks("1_DDC_Toolkit/Procurement/material-procurement-tracker")[0], ns)
    tr = ns["MaterialProcurementTracker"]("Tower")
    item = tr.add_item(
        "Firestop", "07 84 00", 50, "EA", date.today() + timedelta(30), 14, ns["Priority"].CRITICAL
    )
    tr.update_status(item.item_id, ns["ProcurementStatus"].DELIVERED)
    it = tr.items[item.item_id]
    if it.status.value != "delivered" or it.po_number or it.vendor:
        fail("PROC", f"{it.status} po={it.po_number}")
    pass_("PROC", "REQUISITIONED→DELIVERED with empty PO/vendor")


def poc_iot():
    bs = blocks("5_DDC_Innovative/material-tracking-iot")
    ns: dict = {}
    pre = (
        "from dataclasses import dataclass, field\nfrom typing import *\n"
        "from datetime import datetime\nfrom enum import Enum\nimport uuid\n"
    )
    combo = []
    for b in bs:
        combo.append(b)
        if "class MaterialTrackingSystem" in b:
            break
    exec(pre + "\n\n".join(combo), ns)
    system = ns["MaterialTrackingSystem"]()
    mat = system.register_material("Epoxy Firestop", 100, "kg", rfid_tag="RFID-X")
    sensor = system.register_sensor(ns["SensorType"].RFID, "Building A Zone 5")
    system.process_sensor_reading(sensor.sensor_id, 1.0, "tag", metadata={"rfid_tag": "RFID-X"})
    m = system.materials[mat.material_id]
    if m.status.value != "in_use":
        fail("IOT", m.status.value)
    pass_("IOT", f"ORDERED→{m.status.value} at {m.location}")


def main():
    poc_change_order_processor()
    poc_change_order_manager()
    poc_lien_waiver()
    poc_sub_payment()
    poc_crane()
    poc_material_sub()
    poc_safety()
    poc_env()
    poc_delivery()
    poc_procure()
    poc_iot()
    print("ALL_POCS_PASSED")


if __name__ == "__main__":
    main()
