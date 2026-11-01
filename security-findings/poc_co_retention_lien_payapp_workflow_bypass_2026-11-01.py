#!/usr/bin/env python3
"""PoC: Cost/Contract/Financial workflow-gate bypasses (HIGH).

Validates:
1) change-order-processor.approve_change_order skips DRAFT→REVIEW→APPROVAL gates
2) change-order-manager.approve_change_order from DRAFT + uncapped amount → execute
3) retention-tracker.release_retention ignores check_release_conditions / lien waivers
4) lien-waiver-tracker treats RECEIVED as VERIFIED for can_release / waivers_complete
5) payment-application-processor.approve_pay_app from DRAFT with uncapped approved_amount
6) subcontractor-payment-tracker.record_payment without APPROVED or lien waiver
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# 1) change-order-processor approve from DRAFT
# ---------------------------------------------------------------------------
class COPStatus(Enum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"


@dataclass
class COPApproval:
    approver_name: str
    approver_role: str
    action: str
    action_date: datetime
    comments: str = ""


@dataclass
class COPChangeOrder:
    co_number: str
    status: COPStatus
    total_cost: float
    approvals: List[COPApproval] = field(default_factory=list)
    approved_date: Optional[date] = None
    approved_by: str = ""


class ChangeOrderProcessorLite:
    """Mirrors SKILL.md approve_change_order (no status check)."""

    def __init__(self, original_contract: float):
        self.original_contract = original_contract
        self.change_orders: Dict[str, COPChangeOrder] = {}

    def create_draft(self, co_number: str, total_cost: float) -> COPChangeOrder:
        co = COPChangeOrder(co_number=co_number, status=COPStatus.DRAFT, total_cost=total_cost)
        self.change_orders[co_number] = co
        return co

    def submit_for_review(self, co_number: str):
        co = self.change_orders[co_number]
        if co.status != COPStatus.DRAFT:
            raise ValueError("Can only submit draft change orders")
        co.status = COPStatus.PENDING_REVIEW

    def submit_for_approval(self, co_number: str, reviewer: str, comments: str = ""):
        co = self.change_orders[co_number]
        if co.status != COPStatus.PENDING_REVIEW:
            raise ValueError("Must be in review status")
        co.approvals.append(
            COPApproval(reviewer, "Reviewer", "reviewed", datetime.now(), comments)
        )
        co.status = COPStatus.PENDING_APPROVAL

    def approve_change_order(self, co_number: str, approver: str, approver_role: str, comments: str = ""):
        # BUG: no check that status == PENDING_APPROVAL
        co = self.change_orders[co_number]
        co.approvals.append(
            COPApproval(approver, approver_role, "approved", datetime.now(), comments)
        )
        co.status = COPStatus.APPROVED
        co.approved_date = date.today()
        co.approved_by = approver

    def get_summary(self):
        total_approved = sum(
            co.total_cost for co in self.change_orders.values() if co.status == COPStatus.APPROVED
        )
        return {
            "approved_changes": total_approved,
            "current_contract": self.original_contract + total_approved,
        }


def poc1():
    p = ChangeOrderProcessorLite(1_000_000)
    co = p.create_draft("CO-001", 500_000)
    assert co.status == COPStatus.DRAFT
    p.approve_change_order("CO-001", "attacker", "Owner", "skipped review")
    s = p.get_summary()
    assert co.status == COPStatus.APPROVED
    assert s["approved_changes"] == 500_000
    assert s["current_contract"] == 1_500_000
    print("PoC1 PASS: DRAFT CO approved; contract +$500k without review gates")


# ---------------------------------------------------------------------------
# 2) change-order-manager approve from DRAFT + uncapped amount → execute
# ---------------------------------------------------------------------------
class COMStatus(Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    EXECUTED = "executed"


@dataclass
class COMChangeOrder:
    id: str
    status: COMStatus = COMStatus.DRAFT
    proposed_amount: float = 0.0
    approved_amount: float = 0.0


class ChangeOrderManagerLite:
    def __init__(self, original_contract: float):
        self.original_contract = original_contract
        self.change_orders: Dict[str, COMChangeOrder] = {}

    def create_draft(self, co_id: str, proposed: float) -> COMChangeOrder:
        co = COMChangeOrder(id=co_id, proposed_amount=proposed)
        self.change_orders[co_id] = co
        return co

    def approve_change_order(self, co_id: str, approved_amount: float):
        # BUG: no status gate; approved_amount uncapped vs proposed
        co = self.change_orders[co_id]
        co.status = COMStatus.APPROVED
        co.approved_amount = approved_amount

    def execute_change_order(self, co_id: str):
        co = self.change_orders[co_id]
        if co.status != COMStatus.APPROVED:
            raise ValueError("Change order must be approved before execution")
        co.status = COMStatus.EXECUTED

    def get_summary(self):
        total_approved = sum(
            co.approved_amount
            for co in self.change_orders.values()
            if co.status in [COMStatus.APPROVED, COMStatus.EXECUTED]
        )
        return {
            "total_approved": total_approved,
            "revised_contract": self.original_contract + total_approved,
        }


def poc2():
    m = ChangeOrderManagerLite(10_000_000)
    co = m.create_draft("CO-X", 50_000)
    m.approve_change_order("CO-X", 2_000_000)  # 40× proposed, from DRAFT
    m.execute_change_order("CO-X")
    s = m.get_summary()
    assert co.status == COMStatus.EXECUTED
    assert s["total_approved"] == 2_000_000
    assert s["revised_contract"] == 12_000_000
    print("PoC2 PASS: DRAFT→APPROVED→EXECUTED at $2M (proposed $50k)")


# ---------------------------------------------------------------------------
# 3) retention-tracker release without enforcing conditions
# ---------------------------------------------------------------------------
class ReleaseMilestone(Enum):
    SUBSTANTIAL_COMPLETION = "substantial_completion"


class RetentionStatus(Enum):
    HELD = "held"
    RELEASED = "released"
    PARTIAL_RELEASE = "partial_release"


@dataclass
class RetentionRelease:
    id: str
    amount: float
    approved_by: str
    lien_waivers_received: bool = False
    consent_of_surety: bool = False
    conditions_met: List[str] = field(default_factory=list)


@dataclass
class SubcontractorRetention:
    subcontractor_id: str
    balance_held: float
    total_released: float = 0.0
    releases: List[RetentionRelease] = field(default_factory=list)
    status: RetentionStatus = RetentionStatus.HELD


def release_retention(sub: SubcontractorRetention, amount: float, approved_by: str,
                      lien_waivers: bool = False, consent_of_surety: bool = False):
    # BUG: records flags but never requires them True; never calls check_release_conditions
    if amount > sub.balance_held:
        amount = sub.balance_held
    release = RetentionRelease(
        id=f"REL-{len(sub.releases)+1}",
        amount=amount,
        approved_by=approved_by,
        lien_waivers_received=lien_waivers,
        consent_of_surety=consent_of_surety,
    )
    sub.releases.append(release)
    sub.total_released += amount
    sub.balance_held -= amount
    if sub.balance_held <= 0:
        sub.status = RetentionStatus.RELEASED
    return release


def check_release_conditions(sub: SubcontractorRetention) -> Dict:
    conditions = {
        "punch_list_complete": False,
        "final_lien_waiver": False,
        "consent_of_surety": False,
        "as_builts_submitted": False,
        "warranty_documents": False,
        "training_complete": False,
        "closeout_docs": False,
    }
    if sub.releases:
        last = sub.releases[-1]
        conditions["final_lien_waiver"] = last.lien_waivers_received
        conditions["consent_of_surety"] = last.consent_of_surety
    missing = [k for k, v in conditions.items() if not v]
    return {"missing_conditions": missing, "ready_for_release": len(missing) == 0}


def poc3():
    sub = SubcontractorRetention("SUB-001", balance_held=100_000)
    pre = check_release_conditions(sub)
    assert pre["ready_for_release"] is False
    # Release anyway with lien_waivers=False
    release = release_retention(sub, 100_000, "attacker", lien_waivers=False)
    assert release.lien_waivers_received is False
    assert sub.balance_held == 0
    assert sub.status == RetentionStatus.RELEASED
    post = check_release_conditions(sub)
    assert post["ready_for_release"] is False  # still missing conditions
    print("PoC3 PASS: $100k retention released while ready_for_release=False")


# ---------------------------------------------------------------------------
# 4) lien-waiver RECEIVED treated as verified
# ---------------------------------------------------------------------------
class WaiverStatus(Enum):
    REQUESTED = "requested"
    RECEIVED = "received"
    VERIFIED = "verified"


class WaiverType(Enum):
    CONDITIONAL_PROGRESS = "conditional_progress"


@dataclass
class LienWaiver:
    id: str
    status: WaiverStatus
    waiver_type: WaiverType = WaiverType.CONDITIONAL_PROGRESS


@dataclass
class PayApp:
    amount_approved: float
    waivers_complete: bool = False


def check_pay_app_waivers(pay_app: PayApp, waivers: List[LienWaiver]):
    pay_app.waivers_complete = all(
        w.status in [WaiverStatus.RECEIVED, WaiverStatus.VERIFIED] for w in waivers
    )


def can_release_payment(pay_app: PayApp, waivers: List[LienWaiver]) -> Dict:
    progress = [w for w in waivers if w.waiver_type == WaiverType.CONDITIONAL_PROGRESS]
    if not progress:
        return {"can_release": False, "reason": "No conditional waiver received"}
    for w in progress:
        if w.status not in [WaiverStatus.RECEIVED, WaiverStatus.VERIFIED]:
            return {"can_release": False, "reason": f"Waiver {w.id} not verified"}
    return {
        "can_release": True,
        "reason": "All waivers verified",  # lies: RECEIVED counts
        "amount": pay_app.amount_approved,
    }


def poc4():
    pay_app = PayApp(amount_approved=90_000)
    waivers = [LienWaiver("LW-1", WaiverStatus.RECEIVED)]  # never verified
    check_pay_app_waivers(pay_app, waivers)
    result = can_release_payment(pay_app, waivers)
    assert pay_app.waivers_complete is True
    assert result["can_release"] is True
    assert result["reason"] == "All waivers verified"
    assert result["amount"] == 90_000
    print("PoC4 PASS: RECEIVED-only waiver unlocks can_release=$90k")


# ---------------------------------------------------------------------------
# 5) pay-app approve from DRAFT + uncapped amount
# ---------------------------------------------------------------------------
class PayAppStatus(Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    PAID = "paid"


@dataclass
class PaymentApplication:
    status: PayAppStatus = PayAppStatus.DRAFT
    net_amount_due: float = 0.0
    approved_amount: float = 0.0
    paid_amount: float = 0.0


def approve_pay_app(pay_app: PaymentApplication, approved_amount: float = None):
    # BUG: no status check; approved_amount not capped to net_amount_due
    pay_app.status = PayAppStatus.APPROVED
    pay_app.approved_amount = approved_amount if approved_amount else pay_app.net_amount_due


def record_payment(pay_app: PaymentApplication, paid_amount: float):
    # BUG: does not require APPROVED
    pay_app.paid_amount = paid_amount
    if paid_amount >= pay_app.approved_amount:
        pay_app.status = PayAppStatus.PAID


def poc5():
    pay = PaymentApplication(net_amount_due=100_000)
    assert pay.status == PayAppStatus.DRAFT
    approve_pay_app(pay, approved_amount=5_000_000)
    assert pay.status == PayAppStatus.APPROVED
    assert pay.approved_amount == 5_000_000
    record_payment(pay, 5_000_000)
    assert pay.status == PayAppStatus.PAID
    print("PoC5 PASS: DRAFT pay app approved/paid at $5M (net due $100k)")


# ---------------------------------------------------------------------------
# 6) subcontractor payment without approve/waiver
# ---------------------------------------------------------------------------
class PaymentStatus(Enum):
    INVOICED = "invoiced"
    APPROVED = "approved"
    PAID = "paid"


@dataclass
class SubPayment:
    payment_id: str
    amount: float
    status: PaymentStatus = PaymentStatus.INVOICED
    lien_waiver: Optional[object] = None
    check_number: str = ""


def record_sub_payment(payment: SubPayment, check_number: str):
    # BUG: no require APPROVED; no require lien_waiver
    payment.status = PaymentStatus.PAID
    payment.check_number = check_number


def poc6():
    pmt = SubPayment("PAY-00001", amount=45_000)
    assert pmt.status == PaymentStatus.INVOICED
    assert pmt.lien_waiver is None
    record_sub_payment(pmt, "CHK-999")
    assert pmt.status == PaymentStatus.PAID
    print("PoC6 PASS: $45k marked PAID from INVOICED with no waiver")


if __name__ == "__main__":
    poc1()
    poc2()
    poc3()
    poc4()
    poc5()
    poc6()
    print("\nALL 6 PoCs PASSED")
