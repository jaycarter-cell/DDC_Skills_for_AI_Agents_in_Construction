#!/usr/bin/env python3
"""PoC: Book/Innovative/Curated leftover skills hunt 2026-10-06.

Validates:
  BK-L01 csv-handler split_csv path traversal via group_column
  BK-L02 resource-leveler negative units hide overallocation
  BK-L03 cashflow-forecaster neg retainage understates financing (lifetime cancel)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
import os
import tempfile
import sys


def poc_csv_path_traversal() -> None:
    """BK-L01: mirrors ConstructionCSVHandler.split_csv path join."""
    tmpdir = tempfile.mkdtemp(prefix="poc_csv_")
    outdir = Path(tmpdir) / "split_out"
    outdir.mkdir()

    def split_csv(values, group_column, output_dir):
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        files = []
        for value in values:
            filename = f"{group_column}_{value}.csv"
            filepath = output_path / filename
            with open(filepath, "w") as f:
                f.write(f"{group_column},v\n{value},1\n")
            files.append(filepath)
        return files

    # Absolute group_column → pathlib replaces base
    abs_col = "/tmp/DDC_CSV_BK_L01_ABS"
    split_csv(["row1"], abs_col, str(outdir))
    abs_file = Path("/tmp/DDC_CSV_BK_L01_ABS_row1.csv")
    assert abs_file.exists(), "absolute group_column write failed"
    abs_file.unlink()

    # Relative ../ escapes output_dir
    split_csv(["x"], "../ESCAPED_BK_L01", str(outdir))
    escaped = Path(tmpdir) / "ESCAPED_BK_L01_x.csv"
    assert escaped.exists(), f"relative escape missing: {escaped}"
    assert not str(escaped.resolve()).startswith(str(outdir.resolve()))
    print("PASS BK-L01 csv-handler split_csv path traversal (absolute + ../)")


def poc_resource_leveler_neg_units() -> None:
    """BK-L02: mirrors calculate_resource_usage += units without bounds."""

    @dataclass
    class Resource:
        id: str
        max_units: float

    @dataclass
    class ResourceAssignment:
        resource_id: str
        units: float
        start_date: date
        end_date: date

    resource = Resource("crane", 1.0)
    assignments = [
        ResourceAssignment("crane", 2.0, date(2024, 1, 1), date(2024, 1, 10)),
        ResourceAssignment("crane", -2.0, date(2024, 1, 1), date(2024, 1, 10)),
    ]
    day = date(2024, 1, 5)
    usage = sum(
        a.units
        for a in assignments
        if a.resource_id == resource.id and a.start_date <= day <= a.end_date
    )
    assert usage == 0.0
    assert not (usage > resource.max_units)
    print("PASS BK-L02 resource-leveler negative units hide overallocation")


def poc_cashflow_lifetime_cancel_financing() -> None:
    """BK-L03: mirrors set_payment_terms + generate_billing_schedule financing metrics."""
    S_CURVE = [0.05, 0.10, 0.15, 0.20, 0.20, 0.15, 0.10, 0.05]

    def financing_required(retainage_rate: float) -> tuple[float, float]:
        contract_value = 5_000_000.0
        estimated_cost = 4_200_000.0
        start = datetime(2024, 1, 1)
        months = 12
        end = start + timedelta(days=months * 30)
        income = []
        for month in range(months):
            curve_idx = min(int(month / months * len(S_CURVE)), len(S_CURVE) - 1)
            adj = months / len(S_CURVE)
            billing = contract_value * S_CURVE[curve_idx] / adj
            net = billing - billing * retainage_rate
            pay = start + timedelta(days=(month + 1) * 30 + 45)
            income.append((pay, net))
        income.append((end + timedelta(days=30 + 45), contract_value * retainage_rate))

        costs = []
        for month in range(months):
            curve_idx = min(int(month / months * len(S_CURVE)), len(S_CURVE) - 1)
            adj = months / len(S_CURVE)
            amount = estimated_cost * S_CURVE[curve_idx] / adj
            paid = start + timedelta(days=month * 30 + 30)
            costs.append((paid, amount))

        current = start
        balance = 100_000.0
        peak = 0.0
        while current < end + timedelta(days=90):
            pe = current + timedelta(days=30)
            exp = sum(a for d, a in costs if current <= d < pe)
            inc = sum(a for d, a in income if current <= d < pe)
            balance = balance + inc - exp
            if balance < peak:
                peak = balance
            current = pe
        fin = abs(peak) if peak < 0 else 0.0
        lifetime = sum(a for _, a in income)
        return fin, lifetime

    fin_base, life_base = financing_required(0.10)
    fin_atk, life_atk = financing_required(-0.10)
    assert abs(life_base - life_atk) < 1.0, "lifetime should cancel"
    assert fin_atk < fin_base
    assert fin_base - fin_atk > 200_000
    print(
        f"PASS BK-L03 cashflow financing understatement "
        f"(base=${fin_base:,.0f} atk=${fin_atk:,.0f} lifetime=${life_base:,.0f})"
    )


def main() -> int:
    poc_csv_path_traversal()
    poc_resource_leveler_neg_units()
    poc_cashflow_lifetime_cancel_financing()
    print("SUMMARY: 3/3 findings PoC groups passed (4 asserts)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
