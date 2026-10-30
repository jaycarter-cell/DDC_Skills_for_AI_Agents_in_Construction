#!/usr/bin/env python3
"""PoC: bim-cost-estimation-cwicr _convert_units fails open to 1.0 (HIGH)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WorkItem:
    cwicr_code: str
    description: str
    unit: str
    unit_price: float
    labor_cost: float = 0.0
    material_cost: float = 0.0
    equipment_cost: float = 0.0
    productivity: float = 1.0
    currency: str = "USD"
    confidence: float = 0.9


def convert_units(value: float, from_unit: str, to_unit: str) -> float:
    """Mirror of BIMCostEstimator._convert_units in SKILL.md."""
    conversions = {
        ("m³", "m³"): 1.0,
        ("m²", "m²"): 1.0,
        ("m", "m"): 1.0,
        ("ft³", "m³"): 0.0283168,
        ("ft²", "m²"): 0.092903,
        ("ft", "m"): 0.3048,
    }
    key = (from_unit.lower(), to_unit.lower())
    factor = conversions.get(key, 1.0)
    return value * factor


def estimate_line(quantity: float, quantity_unit: str, match: WorkItem) -> float:
    adjusted = convert_units(quantity, quantity_unit, match.unit)
    return adjusted * match.unit_price


def main() -> None:
    pipe = WorkItem("P-PIPE", "Pipe install", "m", 65.0)
    honest = estimate_line(12.0, "m", pipe)
    mm_export = estimate_line(12000.0, "mm", pipe)  # Revit length in mm
    assert honest == 780.0, honest
    assert mm_export == 780_000.0, mm_export
    assert mm_export / honest == 1000.0

    # estimate_from_qto always passes quantity_unit="m³"; incompatible CWICR unit → 1.0
    wall = WorkItem("W-BRICK", "Brick wall", "m²", 85.0)
    forced_m3 = estimate_line(500.0, "m³", wall)  # should refuse m³↔m²
    honest_m2 = estimate_line(500.0, "m²", wall)
    assert forced_m3 == honest_m2 == 42_500.0

    # Control: known pair still converts
    sf = convert_units(1000.0, "ft²", "m²")
    assert abs(sf - 92.903) < 1e-6, sf

    print("PASS bim-cost unit fail-open: 12m@$65=$780; 12000mm@$65=$780000 (1000x)")
    print("PASS incompatible m³→m² accepted at 1.0; ft²→m² still converts")


if __name__ == "__main__":
    main()
