#!/usr/bin/env python3
"""PoCs for DDC Skills Book/Toolkit remaining hunt (2026-10-05)."""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

PASSED = 0
FAILED = 0


def check(name: str, cond: bool, detail: str = ""):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f"PASS: {name}" + (f" — {detail}" if detail else ""))
    else:
        FAILED += 1
        print(f"FAIL: {name}" + (f" — {detail}" if detail else ""))


# ---------------------------------------------------------------------------
# FINDING 1: payment-application-generator forge CO + uncapped SOV progress
# ---------------------------------------------------------------------------
@dataclass
class SOVItem:
    item_number: str
    description: str
    scheduled_value: float
    work_completed_previous: float
    work_completed_current: float
    materials_stored_previous: float
    materials_stored_current: float
    total_completed_previous: float

    @property
    def total_completed_current(self) -> float:
        return (
            self.work_completed_previous
            + self.work_completed_current
            + self.materials_stored_previous
            + self.materials_stored_current
        )


@dataclass
class PaymentApplication:
    application_number: int
    period_from: date
    period_to: date
    project_name: str
    contractor: str
    owner: str
    contract_sum: float
    change_orders_amount: float
    retainage_percent: float
    items: List[SOVItem] = field(default_factory=list)

    @property
    def total_contract_sum(self) -> float:
        return self.contract_sum + self.change_orders_amount

    @property
    def total_completed_to_date(self) -> float:
        return sum(i.total_completed_current for i in self.items)

    @property
    def retainage_amount(self) -> float:
        return self.total_completed_to_date * self.retainage_percent

    @property
    def total_earned_less_retainage(self) -> float:
        return self.total_completed_to_date - self.retainage_amount


class PaymentApplicationGenerator:
    DEFAULT_RETAINAGE = 0.10

    def __init__(
        self,
        project_name: str,
        contractor: str,
        owner: str,
        original_contract: float,
        retainage: float = None,
    ):
        self.project_name = project_name
        self.contractor = contractor
        self.owner = owner
        self.original_contract = original_contract
        self.retainage_percent = retainage or self.DEFAULT_RETAINAGE
        self.sov_items: Dict[str, SOVItem] = {}
        self.applications: List[PaymentApplication] = []
        self.change_orders_total: float = 0

    def setup_sov(self, items: List[Dict[str, Any]]):
        for item in items:
            self.sov_items[item["number"]] = SOVItem(
                item["number"], item["description"], item["value"], 0, 0, 0, 0, 0
            )

    def add_change_order(self, amount: float, description: str, item_number: str = None):
        self.change_orders_total += amount
        if item_number and item_number in self.sov_items:
            self.sov_items[item_number].scheduled_value += amount
        else:
            new_number = f"CO-{len([i for i in self.sov_items if 'CO' in i]) + 1:02d}"
            self.sov_items[new_number] = SOVItem(
                new_number, f"Change Order: {description}", amount, 0, 0, 0, 0, 0
            )

    def create_application(
        self, period_from: date, period_to: date, progress: Dict[str, Dict[str, float]]
    ) -> PaymentApplication:
        app_number = len(self.applications) + 1
        items_copy = []
        for item_num, sov in self.sov_items.items():
            updated = SOVItem(
                sov.item_number,
                sov.description,
                sov.scheduled_value,
                sov.total_completed_current - sov.materials_stored_current,
                0,
                sov.materials_stored_current,
                0,
                sov.total_completed_current,
            )
            if item_num in progress:
                prog = progress[item_num]
                if "work" in prog:
                    updated.work_completed_current = prog["work"]
                if "materials" in prog:
                    updated.materials_stored_current = prog["materials"]
            items_copy.append(updated)
            self.sov_items[item_num] = SOVItem(
                updated.item_number,
                updated.description,
                updated.scheduled_value,
                updated.work_completed_previous + updated.work_completed_current,
                0,
                updated.materials_stored_previous + updated.materials_stored_current,
                0,
                updated.total_completed_current,
            )
        application = PaymentApplication(
            app_number,
            period_from,
            period_to,
            self.project_name,
            self.contractor,
            self.owner,
            self.original_contract,
            self.change_orders_total,
            self.retainage_percent,
            items_copy,
        )
        self.applications.append(application)
        return application

    def calculate_payment_due(self, application: PaymentApplication) -> Dict[str, float]:
        previous_payments = sum(
            app.total_earned_less_retainage for app in self.applications[:-1]
        )
        return {
            "current_payment_due": application.total_earned_less_retainage
            - previous_payments,
            "total_completed_to_date": application.total_completed_to_date,
            "total_contract_sum": application.total_contract_sum,
        }


def poc_payapp_forge_overbill():
    g = PaymentApplicationGenerator("Tower", "ABC", "Owner", 1_000_000, 0.10)
    g.setup_sov([{"number": "001", "description": "Concrete", "value": 500_000}])
    g.add_change_order(2_000_000, "Phantom unapproved CO")
    app = g.create_application(
        date(2026, 1, 1),
        date(2026, 1, 31),
        {"001": {"work": 3_000_000}, "CO-01": {"work": 2_000_000}},
    )
    pay = g.calculate_payment_due(app)
    check(
        "payapp forge CO + overbill",
        pay["current_payment_due"] >= 4_500_000
        and pay["total_contract_sum"] == 3_000_000
        and pay["total_completed_to_date"] == 5_000_000,
        f"due={pay['current_payment_due']}, contract={pay['total_contract_sum']}, "
        f"completed={pay['total_completed_to_date']}",
    )


# ---------------------------------------------------------------------------
# FINDING 2: toolkit cash-flow-forecaster negative retention
# ---------------------------------------------------------------------------
class PaymentTerms(Enum):
    NET_30 = 30


class CashFlowType(Enum):
    INFLOW = "inflow"
    OUTFLOW = "outflow"


@dataclass
class CostItem:
    item_id: str
    description: str
    total_amount: float
    start_date: date
    end_date: date
    payment_terms: PaymentTerms
    distribution: str
    retention_percent: float
    category: str = ""


@dataclass
class PaymentSchedule:
    payment_id: str
    item_id: str
    description: str
    amount: float
    due_date: date
    payment_type: CashFlowType
    is_retention: bool = False


class CashFlowForecaster:
    def __init__(self, project_start: date, project_end: date):
        self.project_start = project_start
        self.project_end = project_end
        self.revenue_items: List[CostItem] = []
        self.payments: List[PaymentSchedule] = []
        self._payment_counter = 0

    def add_revenue_item(
        self,
        item_id: str,
        description: str,
        total_amount: float,
        start_date: date,
        end_date: date,
        retention: float = 0.10,
    ):
        self.revenue_items.append(
            CostItem(
                item_id,
                description,
                total_amount,
                start_date,
                end_date,
                PaymentTerms.NET_30,
                "linear",
                retention,
            )
        )

    def _distribute_amount(self, total, start, end, distribution, periods):
        return [total / periods] * periods

    def _generate_item_payments(self, item: CostItem, flow_type: CashFlowType):
        months = (
            (item.end_date.year - item.start_date.year) * 12
            + (item.end_date.month - item.start_date.month)
            + 1
        )
        periods = max(1, months)
        net_amount = item.total_amount * (1 - item.retention_percent)
        amounts = self._distribute_amount(
            net_amount, item.start_date, item.end_date, item.distribution, periods
        )
        current_date = item.start_date
        for i, amount in enumerate(amounts):
            due_date = current_date + timedelta(days=item.payment_terms.value)
            self._payment_counter += 1
            self.payments.append(
                PaymentSchedule(
                    f"PAY-{self._payment_counter}",
                    item.item_id,
                    f"{item.description} - Period {i+1}",
                    amount,
                    due_date,
                    flow_type,
                )
            )
            if current_date.month == 12:
                current_date = date(current_date.year + 1, 1, min(current_date.day, 28))
            else:
                current_date = date(
                    current_date.year, current_date.month + 1, min(current_date.day, 28)
                )
        if item.retention_percent > 0:
            retention_amount = item.total_amount * item.retention_percent
            self._payment_counter += 1
            self.payments.append(
                PaymentSchedule(
                    f"PAY-{self._payment_counter}",
                    item.item_id,
                    f"{item.description} - Retention Release",
                    retention_amount,
                    self.project_end + timedelta(days=60),
                    flow_type,
                    True,
                )
            )

    def generate(self):
        self.payments = []
        for item in self.revenue_items:
            self._generate_item_payments(item, CashFlowType.INFLOW)
        return self.payments


def poc_cashflow_neg_retention():
    start, end = date(2026, 1, 1), date(2026, 4, 30)
    # baseline
    base = CashFlowForecaster(start, end)
    base.add_revenue_item("DRAW", "Owner Draws", 1_000_000, start, end, retention=0.10)
    base_total = sum(p.amount for p in base.generate())
    # attack
    atk = CashFlowForecaster(start, end)
    atk.add_revenue_item("DRAW", "Owner Draws", 1_000_000, start, end, retention=-0.50)
    pays = atk.generate()
    atk_total = sum(p.amount for p in pays)
    has_release = any(p.is_retention for p in pays)
    check(
        "cashflow neg retention permanent inflate",
        base_total == 1_000_000 and atk_total == 1_500_000 and not has_release,
        f"base={base_total}, attack={atk_total}, release={has_release}",
    )


# ---------------------------------------------------------------------------
# FINDING 3: curated budget-variance revise + contingency
# ---------------------------------------------------------------------------
class CostCategory(Enum):
    LABOR = "labor"
    OTHER = "other"


@dataclass
class CostCode:
    code: str
    description: str
    category: CostCategory
    original_budget: float
    revised_budget: float = 0.0
    committed: float = 0.0
    actual: float = 0.0
    forecast: float = 0.0
    percent_complete: float = 0.0

    @property
    def budget(self) -> float:
        return self.revised_budget if self.revised_budget else self.original_budget

    @property
    def variance(self) -> float:
        return self.budget - self.actual


class BudgetVarianceAnalyzer:
    def __init__(self, project_name: str, original_budget: float):
        self.project_name = project_name
        self.original_budget = original_budget
        self.cost_codes: Dict[str, CostCode] = {}
        self.contingency_used = 0.0

    def add_cost_code(self, code, description, category, budget):
        cc = CostCode(code, description, category, budget, budget, forecast=budget)
        self.cost_codes[code] = cc
        return cc

    def revise_budget(self, code: str, new_budget: float, reason: str = ""):
        cost_code = self.cost_codes[code]
        cost_code.revised_budget = new_budget
        cost_code.forecast = new_budget
        return cost_code

    def use_contingency(self, amount: float, target_code: str, reason: str = ""):
        self.contingency_used += amount
        if target_code in self.cost_codes:
            self.cost_codes[target_code].revised_budget += amount
        return self.contingency_used


def poc_budget_revise_contingency():
    bv = BudgetVarianceAnalyzer("Tower", 1_000_000)
    bv.add_cost_code("03", "Concrete", CostCategory.LABOR, 200_000)
    bv.cost_codes["03"].actual = 350_000
    before = bv.cost_codes["03"].variance
    bv.revise_budget("03", 400_000, "hide overrun")
    after = bv.cost_codes["03"].variance
    bv.use_contingency(5_000_000, "03", "phantom")
    check(
        "budget revise hides overrun",
        before == -150_000 and after == 50_000,
        f"before={before}, after={after}",
    )
    check(
        "budget contingency unbounded",
        bv.contingency_used == 5_000_000
        and bv.cost_codes["03"].revised_budget == 5_400_000,
        f"used={bv.contingency_used}, revised={bv.cost_codes['03'].revised_budget}",
    )


# ---------------------------------------------------------------------------
# FINDING 4: bim-cost project_name path traversal write
# ---------------------------------------------------------------------------
def poc_bimcost_path_traversal():
    out = tempfile.mkdtemp(prefix="est_out_")
    outside = tempfile.mkdtemp(prefix="outside_")
    rel = os.path.relpath(outside, out)
    project_name = f"{rel}/pwned"
    excel_path = f"{out}/{project_name}_Estimate.xlsx"
    Path(excel_path).parent.mkdir(parents=True, exist_ok=True)
    Path(excel_path).write_text("pwn")
    resolved = Path(excel_path).resolve()
    escaped = not str(resolved).startswith(str(Path(out).resolve()) + os.sep)
    check(
        "bim-cost project_name path traversal write",
        escaped and resolved.exists() and resolved.parent == Path(outside).resolve(),
        f"resolved={resolved}",
    )


if __name__ == "__main__":
    poc_payapp_forge_overbill()
    poc_cashflow_neg_retention()
    poc_budget_revise_contingency()
    poc_bimcost_path_traversal()
    print(f"\nResult: {PASSED} passed, {FAILED} failed")
    raise SystemExit(0 if FAILED == 0 else 1)
