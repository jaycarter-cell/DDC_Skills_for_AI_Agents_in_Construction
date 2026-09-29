#!/usr/bin/env python3
"""PoCs for financial/contract SKILL.md business-logic findings (2026-09-29)."""
from __future__ import annotations

import re
import sys
import types
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def stub_pandas():
    pd = types.ModuleType("pandas")

    class DF:
        def __init__(self, *a, **k):
            pass

        def to_excel(self, *a, **k):
            pass

        @staticmethod
        def concat(objs, ignore_index=False):
            return DF()

    class EW:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    pd.DataFrame = DF
    pd.concat = DF.concat
    pd.ExcelWriter = EW
    sys.modules["pandas"] = pd
    sys.modules.setdefault("numpy", types.ModuleType("numpy"))
    sys.modules.setdefault("openpyxl", types.ModuleType("openpyxl"))


def load_skill_python(rel: str):
    text = (ROOT / rel).read_text()
    blocks = re.findall(r"```python\n(.*?)```", text, re.S)
    if not blocks:
        raise RuntimeError(f"no python block in {rel}")
    ns: dict = {}
    exec(blocks[0], ns)
    return ns


RESULTS = []


def check(name: str, cond: bool, detail: str = ""):
    status = "PASS" if cond else "FAIL"
    RESULTS.append((status, name, detail))
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))


def main():
    stub_pandas()

    # 1. CO-manager forge APPROVED
    ns = load_skill_python("4_DDC_Curated/Contract-Legal/change-order-manager/SKILL.md")
    mgr = ns["ChangeOrderManager"]("P1", "Tower", 2_000_000)
    co = mgr.create_change_order("Phantom", "nothing", list(ns["ChangeType"])[0], "attacker")
    mgr.approve_change_order(co.id, approved_amount=5_000_000, approved_time=90)
    s = mgr.get_summary()
    check(
        "CO-manager forge APPROVED $5M from empty DRAFT",
        co.status == ns["ChangeOrderStatus"].APPROVED and s["revised_contract"] == 7_000_000,
        f"revised={s['revised_contract']} proposed={co.proposed_amount}",
    )

    # 2. CO-processor DRAFT→APPROVED bypass
    ns = load_skill_python("1_DDC_Toolkit/Cost-Management/change-order-processor/SKILL.md")
    proc = ns["ChangeOrderProcessor"]("Proj", 1_000_000)
    co = proc.create_change_order("Fake", "scope", list(ns["ChangeType"])[0], "attacker")
    proc.add_cost_item(co.co_number, "labor", 100, "hr", 5000, "labor", 0.15)
    assert co.status == ns["ChangeOrderStatus"].DRAFT
    proc.approve_change_order(co.co_number, "attacker", "Owner")
    summary = proc.get_summary()
    check(
        "CO-processor approve DRAFT→APPROVED bypasses review",
        co.status == ns["ChangeOrderStatus"].APPROVED and summary["approved_changes"] > 500_000,
        f"approved={summary['approved_changes']} current={summary['current_contract']}",
    )

    # 3. PayApp negative retainage
    ns = load_skill_python(
        "4_DDC_Curated/Financial-Management/payment-application-processor/SKILL.md"
    )
    p = ns["PaymentApplicationProcessor"]("Tower", "GC Inc", 1_000_000)
    p.add_sov_item("01", "Steel", 500_000)
    p.set_retainage_rates(-0.50)
    app = p.create_pay_app(datetime(2026, 1, 1), datetime(2026, 1, 31))
    p.update_line_item(app.application_number, "01", current_completed=500_000)
    check(
        "PayApp negative retainage inflates net due",
        app.retainage < 0 and app.net_amount_due == 750_000,
        f"retainage={app.retainage} net={app.net_amount_due}",
    )

    # 4. PayApp forge approved_amount from DRAFT
    p2 = ns["PaymentApplicationProcessor"]("Tower", "GC", 1_000_000)
    p2.add_sov_item("01", "Work", 100_000)
    app2 = p2.create_pay_app(datetime(2026, 1, 1), datetime(2026, 1, 31))
    p2.update_line_item(app2.application_number, "01", current_completed=10_000)
    p2.approve_pay_app(app2.application_number, approved_amount=9_000_000)
    check(
        "PayApp approve DRAFT with forged $9M amount",
        app2.status == ns["PayAppStatus"].APPROVED
        and app2.approved_amount == 9_000_000
        and app2.net_amount_due == 9_000,
        f"approved={app2.approved_amount} net={app2.net_amount_due}",
    )

    # 5. PayApp overbill + mutate after APPROVED
    p3 = ns["PaymentApplicationProcessor"]("Tower", "GC", 100_000)
    p3.add_sov_item("01", "Work", 100_000)
    app3 = p3.create_pay_app(datetime(2026, 1, 1), datetime(2026, 1, 31))
    p3.update_line_item(app3.application_number, "01", current_completed=250_000)
    check(
        "PayApp unbounded current_completed overbills past SOV",
        app3.total_completed == 250_000 and app3.net_amount_due == 225_000,
        f"total={app3.total_completed} net={app3.net_amount_due}",
    )

    p4 = ns["PaymentApplicationProcessor"]("Tower", "GC", 100_000)
    p4.add_sov_item("01", "Work", 100_000)
    app4 = p4.create_pay_app(datetime(2026, 1, 1), datetime(2026, 1, 31))
    p4.update_line_item(app4.application_number, "01", current_completed=10_000)
    p4.submit_pay_app(app4.application_number)
    p4.approve_pay_app(app4.application_number)
    approved_at = app4.approved_amount
    p4.update_line_item(app4.application_number, "01", current_completed=100_000)
    g702 = p4.generate_g702(app4.application_number, "Owner", "Architect")
    check(
        "PayApp update_line_item after APPROVED inflates G702 due",
        app4.status == ns["PayAppStatus"].APPROVED
        and g702.current_payment_due == 90_000
        and approved_at == 9_000,
        f"approved_frozen={approved_at} g702_due={g702.current_payment_due}",
    )

    # 6. Retention negative release overpay
    ns = load_skill_python("4_DDC_Curated/Financial-Management/retention-tracker/SKILL.md")
    rt = ns["RetentionTracker"]("Tower")
    rt.add_subcontractor("S1", "Elec Co", "Electrical", 1_000_000, 0.10)
    rt.record_billing("S1", 1, datetime(2026, 1, 15), 200_000)
    held_before = rt.subcontractors["S1"].balance_held
    rt.release_retention(
        "S1", ns["ReleaseMilestone"].SUBSTANTIAL_COMPLETION, amount=-50_000, approved_by="attacker"
    )
    held_mid = rt.subcontractors["S1"].balance_held
    rt.release_retention(
        "S1", ns["ReleaseMilestone"].FINAL_COMPLETION, amount=held_mid, approved_by="attacker"
    )
    positive_paid = sum(r.amount for r in rt.subcontractors["S1"].releases if r.amount > 0)
    check(
        "Retention negative release enables $70k payout on $20k held",
        held_before == 20_000 and held_mid == 70_000 and positive_paid == 70_000,
        f"before={held_before} mid={held_mid} positive_paid={positive_paid}",
    )

    # 7. Retention ignores conditions
    rt2 = ns["RetentionTracker"]("Tower")
    rt2.add_subcontractor("S1", "Elec", "E", 500_000)
    rt2.record_billing("S1", 1, datetime.now(), 500_000)
    conds = rt2.check_release_conditions("S1")
    rel = rt2.release_retention(
        "S1",
        ns["ReleaseMilestone"].FINAL_COMPLETION,
        amount=50_000,
        approved_by="",
        lien_waivers=False,
        consent_of_surety=False,
    )
    check(
        "Retention release ignores unmet conditions",
        (not conds["ready_for_release"]) and rel.amount == 50_000,
        f"ready={conds['ready_for_release']} released={rel.amount}",
    )

    # 8. SubPay over-invoice + skip APPROVED + negative retention
    ns = load_skill_python("1_DDC_Toolkit/Cost-Management/subcontractor-payment-tracker/SKILL.md")
    tr = ns["SubcontractorPaymentTracker"]("Tower")
    sub = tr.add_subcontractor(
        "Evil Sub", "Bob", "b@x.com", "555", 100_000, "Demo", retention_percent=-0.5
    )
    pay = tr.record_invoice(sub.sub_id, "INV-1", date.today(), gross_amount=100_000)
    check(
        "SubPay negative retention_percent inflates net 1.5x",
        abs(pay.amount - 150_000) < 0.01,
        f"net={pay.amount} retention={pay.retention_held}",
    )

    tr2 = ns["SubcontractorPaymentTracker"]("Tower")
    sub2 = tr2.add_subcontractor("Sub", "A", "a@x.com", "1", 100_000, "Trade")
    pay2 = tr2.record_invoice(sub2.sub_id, "INV-1", date.today(), gross_amount=500_000)
    tr2.record_payment(pay2.payment_id, sub2.sub_id, "CHK-1")
    check(
        "SubPay 5x contract invoice PAID skipping APPROVED",
        pay2.status == ns["PaymentStatus"].PAID and sub2.total_paid == 450_000 > sub2.contract_amount,
        f"paid={sub2.total_paid} contract={sub2.contract_amount}",
    )

    # 9-10. Claims forge settlement + mutate after submit
    ns = load_skill_python("4_DDC_Curated/Contract-Legal/claims-documentation/SKILL.md")
    CM = [v for k, v in ns.items() if isinstance(v, type) and hasattr(v, "create_claim")][0]
    cm = CM("Tower", datetime(2025, 1, 1))
    claim = cm.create_claim(list(ns["ClaimType"])[0], "Delay", "weather", datetime(2026, 1, 1), "Owner")
    cm.record_settlement(claim.id, time_awarded=120, amount_awarded=2_500_000, notes="forged")
    check(
        "Claims record_settlement from DRAFT forges $2.5M award",
        claim.status == ns["ClaimStatus"].SETTLED and claim.amount_awarded == 2_500_000,
        f"status={claim.status.value} awarded={claim.amount_awarded}",
    )

    claim2 = cm.create_claim(list(ns["ClaimType"])[0], "Extra", "work", datetime(2026, 2, 1), "Owner")
    cm.add_damage_calculation(claim2.id, "Labor", "crew", 100_000, "T&M")
    cm.submit_claim(claim2.id)
    cm.add_damage_calculation(claim2.id, "Phantom", "pad", 900_000, "made up")
    check(
        "Claims add_damage_calculation after SUBMITTED inflates cost_claimed",
        claim2.status == ns["ClaimStatus"].SUBMITTED and claim2.cost_claimed == 1_000_000,
        f"cost_claimed={claim2.cost_claimed}",
    )

    # 11. PayAppGen negative retainage
    ns = load_skill_python("1_DDC_Toolkit/Cost-Management/payment-application-generator/SKILL.md")
    gen = ns["PaymentApplicationGenerator"]("Tower", "GC", "Owner", 1_000_000, retainage=-0.5)
    gen.setup_sov([{"number": "01", "description": "Steel", "value": 500_000}])
    app = gen.create_application(date(2026, 1, 1), date(2026, 1, 31), {"01": {"work": 500_000}})
    due = gen.calculate_payment_due(app)
    check(
        "PayAppGen negative retainage inflates current_payment_due",
        app.retainage_amount == -250_000 and due["current_payment_due"] == 750_000,
        f"retainage={app.retainage_amount} due={due['current_payment_due']}",
    )

    # 12. Toolkit budget adjust_budget
    ns = load_skill_python("1_DDC_Toolkit/Cost-Management/budget-variance-analyzer/SKILL.md")
    ba = ns["BudgetVarianceAnalyzer"]("Tower", 1_000_000)
    ba.add_budget_item(
        "01", "Concrete", list(ns["CostCategory"])[0], 100_000, actual=180_000, percent_complete=100
    )
    before = ba.items["01"].variance_amount
    ba.adjust_budget("01", 100_000, "fake approved change")
    after = ba.items["01"].variance_amount
    check(
        "Toolkit budget adjust_budget hides overrun without approval gate",
        before == -80_000 and after == 20_000,
        f"var_before={before} var_after={after}",
    )

    # 13. Lien RECEIVED (empty file) unlocks release
    ns = load_skill_python("4_DDC_Curated/Contract-Legal/lien-waiver-tracker/SKILL.md")
    lw = ns["LienWaiverTracker"]("P1", "Tower")
    lw.add_subcontractor("S1", "Sub", "E", 500_000, "A", "a@x.com")
    lw.create_payment_application(1, datetime(2026, 1, 31), "S1", 100_000)
    before = lw.can_release_payment("S1", 1)
    lw.receive_waiver("LW-S1-1", file_path="")
    after = lw.can_release_payment("S1", 1)
    check(
        "LienWaiver RECEIVED (empty file) unlocks can_release without VERIFIED",
        before["can_release"] is False and after["can_release"] is True,
        f"before={before['can_release']} after={after}",
    )

    failed = [r for r in RESULTS if r[0] == "FAIL"]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
