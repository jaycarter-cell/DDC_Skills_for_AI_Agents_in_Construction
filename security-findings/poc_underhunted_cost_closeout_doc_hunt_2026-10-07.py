#!/usr/bin/env python3
"""PoC: DDC Skills under-hunted cost/closeout/doc-control business-logic vulns (2026-10-07)."""
from __future__ import annotations
import re, sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] if (Path(__file__).parent.name == "security-findings") else Path("/workspace")

def exec_skill(rel: str):
    text = (ROOT / rel).read_text()
    blocks = re.findall(r"```python\n(.*?)```", text, re.S)
    ns = {}
    for i, b in enumerate(blocks):
        try:
            exec(compile(b, f"{rel}:{i}", "exec"), ns, ns)
        except Exception:
            pass
    return ns

passed = failed = 0

def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"PASS: {name} | {detail}")
    else:
        failed += 1
        print(f"FAIL: {name} | {detail}")

# 1) subcontractor-payment-tracker: PAID forge
ns = exec_skill("1_DDC_Toolkit/Cost-Management/subcontractor-payment-tracker/SKILL.md")
T, PS = ns["SubcontractorPaymentTracker"], ns["PaymentStatus"]
t = T("P"); s = t.add_subcontractor("Evil", "A", "a@a.com", "1", 100_000, "electrical", 0.10)
inv = t.record_invoice(s.sub_id, "INV-1", date.today(), 50_000)
t.record_payment(inv.payment_id, s.sub_id, "FORGED")
check("subcontractor PAID forge without APPROVED/waiver",
      inv.status == PS.PAID and inv.lien_waiver is None and s.total_paid == 45_000,
      f"status={inv.status.value} paid={s.total_paid}")

# HELD → PAID
inv2 = t.record_invoice(s.sub_id, "INV-H", date.today(), 10_000)
inv2.status = PS.HELD
t.record_payment(inv2.payment_id, s.sub_id, "X")
check("subcontractor HELD→PAID override", inv2.status == PS.PAID, inv2.status.value)

# overpay past contract
t3 = T("O"); s3 = t3.add_subcontractor("S", "A", "a@a.com", "1", 100_000, "m", 0.10)
big = t3.record_invoice(s3.sub_id, "BIG", date.today(), 500_000)
t3.record_payment(big.payment_id, s3.sub_id, "X")
check("subcontractor overpay past contract", s3.total_paid == 450_000 and s3.balance_remaining < 0,
      f"paid={s3.total_paid} bal={s3.balance_remaining}")

# 2) neg retention inflate balance
t2 = T("N"); s2 = t2.add_subcontractor("S", "A", "a@a.com", "1", 100_000, "m", 0.10)
before = s2.balance_remaining
neg = t2.record_invoice(s2.sub_id, "NEG", date.today(), -20_000)
check("subcontractor neg invoice retention inflates balance",
      neg.retention_held == -2000 and s2.balance_remaining == before + 2000,
      f"ret={neg.retention_held} bal {before}->{s2.balance_remaining}")

# 3) change-order-analysis DRAFT approve + post-approve mutate
ns = exec_skill("5_DDC_Innovative/change-order-analysis/SKILL.md")
M, COT, COS, CB = ns["ChangeOrderManager"], ns["ChangeOrderType"], ns["ChangeOrderStatus"], ns["CostBreakdown"]
m = M("PRJ", 1_000_000)
co = m.create_change_order("X", "d", COT.SCOPE_CHANGE, "attacker")
m.update_cost(co.co_id, CB(labor=5_000))
m.approve(co.co_id, "attacker")
ok1 = co.status == COS.APPROVED
m.update_cost(co.co_id, CB(labor=500_000))
check("change-order-analysis DRAFT→APPROVED + update_cost after APPROVED",
      ok1 and co.cost_breakdown.total == 500_000,
      f"status={co.status.value} total={co.cost_breakdown.total}")

# 4) permit DRAFT→ISSUED
ns = exec_skill("5_DDC_Innovative/permit-tracking-automation/SKILL.md")
PT, PType, PStatus, Jur = ns["PermitTracker"], ns["PermitType"], ns["PermitStatus"], ns["Jurisdiction"]
pt = PT("P"); pt.add_jurisdiction(Jur("J1", "City", "CA", "US"))
app = pt.create_application(PType.BUILDING, "J1", "Tower", "123 Main")
docs_ok = app.get_document_status()["complete"]
pt.update_status(app.application_id, PStatus.ISSUED, notes="forged", reviewer="attacker")
check("permit update_status DRAFT→ISSUED without docs",
      app.status == PStatus.ISSUED and app.permit_number and not docs_ok,
      f"status={app.status.value} permit={app.permit_number} docs_complete={docs_ok}")

# 5) warranty claim forge
ns = exec_skill("1_DDC_Toolkit/Closeout/warranty-tracker/SKILL.md")
WT, WTy, BS, CS = ns["WarrantyTracker"], ns["WarrantyType"], ns["BuildingSystem"], ns["ClaimStatus"]
wt = WT("Tower", date.today() - timedelta(days=30))
w = wt.add_warranty("HVAC", BS.HVAC, WTy.MANUFACTURER, "Carrier", "ABC", 2, "parts", "v@v.com")
claim = wt.file_claim(w.warranty_id, "broken", date.today(), "attacker")
wt.update_claim_status(claim.claim_id, CS.APPROVED, resolution="pay", cost_covered=999_999)
ok = claim.status == CS.APPROVED and claim.cost_covered == 999_999
wt.update_claim_status(claim.claim_id, CS.DENIED)
wt.update_claim_status(claim.claim_id, CS.APPROVED, cost_covered=1)
check("warranty update_claim_status APPROVED forge + DENIED→APPROVED",
      ok and claim.status == CS.APPROVED, f"cost={claim.cost_covered} status={claim.status.value}")

# 6) punch-list OPEN→ACCEPTED + neg back_charge
ns = exec_skill("1_DDC_Toolkit/Field-Operations/punch-list-manager/SKILL.md")
PM, Trade, Pri, St = ns["PunchListManager"], ns["TradeCategory"], ns["PunchItemPriority"], ns["PunchItemStatus"]
pm = PM("PRJ")
pl = pm.create_punch_list(name="Final", walk_date=date.today(), attendees=["A"])
pl_id = pl.list_id
item = pm.add_item(pl_id, description="crack", location="wall", trade=Trade.ELECTRICAL, priority=Pri.HIGH)
assert item.status == St.OPEN
pm.verify_item(item.item_id, verified_by="attacker", accepted=True)
pm.add_back_charge(item.item_id, amount=-50_000, reference="fraud")
check("punch verify OPEN→ACCEPTED + neg back_charge",
      item.status == St.ACCEPTED and item.back_charge_amount == -50_000,
      f"status={item.status.value} bc={item.back_charge_amount}")

# 7) curated budget use_contingency unbounded/neg
ns = exec_skill("4_DDC_Curated/Financial-Management/budget-variance-analyzer/SKILL.md")
BVA, CC = ns["BudgetVarianceAnalyzer"], ns["CostCategory"]
b = BVA("Proj", 1_000_000)
code = b.add_cost_code("01", "General", list(CC)[0], 100_000)
b.use_contingency(5_000_000, "01", "forge")
inflated = code.revised_budget == 5_100_000
b.use_contingency(-6_000_000, "01", "wipe")
check("curated budget use_contingency unbounded + negative wipe",
      inflated and code.revised_budget < 0,
      f"budget={code.revised_budget} used={b.contingency_used}")

# 8) submittal DRAFT→APPROVED
ns = exec_skill("1_DDC_Toolkit/Document-Control/submittal-tracker/SKILL.md")
ST, SS, STy = ns["SubmittalTracker"], ns["SubmittalStatus"], ns["SubmittalType"]
st = ST("P")
sub = st.create_submittal("03 30 00", "Concrete", list(STy)[0], "Sub", date.today() + timedelta(days=7))
st.review(sub.submittal_id, SS.APPROVED, "attacker")
check("submittal review DRAFT→APPROVED without submit/files",
      sub.status == SS.APPROVED and sub.approved_date is not None and not sub.files,
      f"status={sub.status.value} files={sub.files}")

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
