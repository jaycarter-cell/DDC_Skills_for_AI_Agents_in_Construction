#!/usr/bin/env python3
"""PoC for 5_DDC_Innovative remaining-logic hunt 2026-10-01."""
from __future__ import annotations

import json
import statistics
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple


PASSED = 0
FAILED = 0


def check(name: str, cond: bool, detail: str = ""):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f"PASS {name}" + (f" — {detail}" if detail else ""))
    else:
        FAILED += 1
        print(f"FAIL {name}" + (f" — {detail}" if detail else ""))


# --- INV-01 site-logistics storage non-persist ---
class ZoneType(Enum):
    STORAGE = "storage"
    WORK = "work"


@dataclass
class SiteZone:
    zone_id: str
    zone_type: ZoneType
    position: Tuple[float, float]
    capacity: float
    current_usage: float = 0
    restrictions: List[str] = field(default_factory=list)


class SiteLogisticsModel:
    def __init__(self):
        self.zones: Dict[str, SiteZone] = {}

    def add_zone(self, zone: SiteZone):
        self.zones[zone.zone_id] = zone

    def calculate_distance(self, p1, p2):
        return ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5


class StorageOptimizer:
    def __init__(self, site: SiteLogisticsModel):
        self.site = site

    def allocate_storage(self, materials: List[Dict]) -> Dict[str, str]:
        storage_zones = {
            zid: zone for zid, zone in self.site.zones.items()
            if zone.zone_type == ZoneType.STORAGE
        }
        allocations = {}
        zone_usage = {zid: zone.current_usage for zid, zone in storage_zones.items()}
        for material in materials:
            best_zone = None
            best_score = -float("inf")
            for zone_id, zone in storage_zones.items():
                remaining = zone.capacity - zone_usage[zone_id]
                if remaining < material["quantity"]:
                    score = -float("inf")
                else:
                    score = 0
                    dest = self.site.zones.get(material["destination_zone"])
                    if dest:
                        score += 100 / (1 + self.site.calculate_distance(zone.position, dest.position))
                    score += (remaining / zone.capacity) * 20
                if score > best_score:
                    best_score = score
                    best_zone = zone_id
            if best_zone:
                allocations[material["material_id"]] = best_zone
                zone_usage[best_zone] += material["quantity"]
                # BUG: never writes zone.current_usage
        return allocations

    def get_storage_utilization(self):
        report = {}
        for zone_id, zone in self.site.zones.items():
            if zone.zone_type != ZoneType.STORAGE:
                continue
            util = zone.current_usage / zone.capacity * 100 if zone.capacity > 0 else 0
            report[zone_id] = {
                "used": zone.current_usage,
                "utilization_pct": util,
                "status": "critical" if util > 90 else "normal" if util < 70 else "high",
            }
        return report


def poc_inv01():
    site = SiteLogisticsModel()
    site.add_zone(SiteZone("LAYDOWN", ZoneType.STORAGE, (0, 0), capacity=100))
    site.add_zone(SiteZone("WORK-A", ZoneType.WORK, (50, 0), capacity=0))
    opt = StorageOptimizer(site)
    for mid in ("M1", "M2", "M3"):
        alloc = opt.allocate_storage([{
            "material_id": mid,
            "material_type": "steel",
            "quantity": 100,
            "destination_zone": "WORK-A",
            "arrival_date": "2026-01-01",
        }])
        assert mid in alloc
    u = opt.get_storage_utilization()["LAYDOWN"]
    check("INV-01 storage non-persist", u["used"] == 0 and u["utilization_pct"] == 0,
          f"300 TON assigned; util={u}")


# --- INV-02 sensor SUSPECT alert bypass ---
class DataQuality(Enum):
    GOOD = "good"
    SUSPECT = "suspect"


class AlertSeverity(Enum):
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Sensor:
    id: str
    name: str
    sensor_type: str
    unit: str
    location: str
    thresholds: Dict


@dataclass
class SensorReading:
    sensor_id: str
    sensor_type: str
    timestamp: datetime
    value: float
    unit: str
    quality: DataQuality
    location: str


@dataclass
class Alert:
    id: str
    severity: AlertSeverity
    value: float


class Aggregator:
    def __init__(self):
        self.sensors = {}
        self.readings = []
        self.alerts = []

    def get_recent_readings(self, sensor_id, minutes=5):
        cutoff = datetime.now() - timedelta(minutes=minutes)
        return [r for r in self.readings if r.sensor_id == sensor_id and r.timestamp > cutoff]

    def _validate_reading(self, sensor, value):
        t = sensor.thresholds
        if "min" in t and value < t["min"]:
            return DataQuality.SUSPECT
        if "max" in t and value > t["max"]:
            return DataQuality.SUSPECT
        recent = self.get_recent_readings(sensor.id)
        if len(recent) >= 3:
            avg = statistics.mean([r.value for r in recent])
            if abs(value - avg) > avg * 0.5:
                return DataQuality.SUSPECT
        return DataQuality.GOOD

    def _check_thresholds(self, sensor, reading):
        t = sensor.thresholds
        if "critical" in t and reading.value >= t["critical"]:
            self.alerts.append(Alert("A", AlertSeverity.CRITICAL, reading.value))
        elif "warning" in t and reading.value >= t["warning"]:
            self.alerts.append(Alert("A", AlertSeverity.WARNING, reading.value))

    def ingest_reading(self, sensor_id, value):
        sensor = self.sensors[sensor_id]
        quality = self._validate_reading(sensor, value)
        reading = SensorReading(sensor_id, sensor.sensor_type, datetime.now(), value,
                                sensor.unit, quality, sensor.location)
        self.readings.append(reading)
        if quality == DataQuality.GOOD:
            self._check_thresholds(sensor, reading)
        return reading


def poc_inv02():
    agg = Aggregator()
    agg.sensors["GAS1"] = Sensor("GAS1", "CO", "gas", "ppm", "tunnel",
                                 {"min": 0, "max": 100, "warning": 25, "critical": 50})
    r = agg.ingest_reading("GAS1", 500)
    check("INV-02 SUSPECT skips alerts", r.quality == DataQuality.SUSPECT and len(agg.alerts) == 0,
          f"quality={r.quality} alerts={len(agg.alerts)}")


# --- INV-03 env warning suppresses exceedance ---
class ParameterType(Enum):
    NOISE = "noise"


class AlertType(Enum):
    THRESHOLD_WARNING = "threshold_warning"
    THRESHOLD_EXCEEDANCE = "threshold_exceedance"


@dataclass
class RegulatoryLimit:
    parameter: ParameterType
    limit_value: float
    unit: str
    averaging_period_hours: float
    regulation: str
    description: str


@dataclass
class EnvironmentalAlert:
    id: str
    alert_type: AlertType
    parameter: ParameterType
    station_id: str
    timestamp: datetime
    value: float
    threshold: float
    message: str
    resolved: bool = False


class EnvMonitor:
    REGULATORY_LIMITS = {
        ParameterType.NOISE: [RegulatoryLimit(ParameterType.NOISE, 85, "dBA", 0.0, "OSHA", "instant")],
    }

    def __init__(self):
        self.stations = {"S1": True}
        self.readings = []
        self.alerts: List[EnvironmentalAlert] = []
        self.custom_limits = {}

    def record_reading(self, station_id, parameter, value):
        self.readings.append(value)
        self._check_limits(station_id, parameter, value)

    def _check_limits(self, station_id, parameter, value):
        limits = list(self.REGULATORY_LIMITS.get(parameter, []))
        for limit in limits:
            if value >= limit.limit_value:
                self._create_alert(station_id, parameter, value, limit)
            elif value >= limit.limit_value * 0.8:
                self._create_alert(station_id, parameter, value, limit, is_warning=True)

    def _create_alert(self, station_id, parameter, value, limit, is_warning=False):
        recent = [a for a in self.alerts
                  if a.station_id == station_id and a.parameter == parameter
                  and not a.resolved
                  and (datetime.now() - a.timestamp).total_seconds() < 3600]
        if recent:
            return
        at = AlertType.THRESHOLD_WARNING if is_warning else AlertType.THRESHOLD_EXCEEDANCE
        self.alerts.append(EnvironmentalAlert(
            id=f"E{len(self.alerts)}", alert_type=at, parameter=parameter,
            station_id=station_id, timestamp=datetime.now(), value=value,
            threshold=limit.limit_value, message="x"))


def poc_inv03():
    m = EnvMonitor()
    m.record_reading("S1", ParameterType.NOISE, 70)
    m.record_reading("S1", ParameterType.NOISE, 120)
    check("INV-03 warning suppresses exceedance",
          len(m.alerts) == 1 and m.alerts[0].alert_type == AlertType.THRESHOLD_WARNING
          and m.alerts[0].value == 70,
          f"alerts={[ (a.alert_type.value, a.value) for a in m.alerts ]}")


# --- INV-04 capacity phantom FTE ---
class ResourceRole(Enum):
    PROJECT_MANAGER = "project_manager"
    SUPERINTENDENT = "superintendent"
    ESTIMATOR = "estimator"
    ENGINEER = "engineer"
    FOREMAN = "foreman"
    SKILLED_TRADE = "skilled_trade"


class ProjectPhase(Enum):
    CONSTRUCTION = "construction"


@dataclass
class StaffMember:
    id: str
    name: str
    role: ResourceRole
    capacity: float = 1.0
    availability_date: datetime = None


class CapacityPlanner:
    STAFFING_RATIOS = {
        ResourceRole.PROJECT_MANAGER: 50_000_000,
        ResourceRole.SUPERINTENDENT: 25_000_000,
        ResourceRole.ESTIMATOR: 100_000_000,
        ResourceRole.ENGINEER: 40_000_000,
        ResourceRole.FOREMAN: 10_000_000,
        ResourceRole.SKILLED_TRADE: 2_000_000,
    }
    PHASE_FACTORS = {
        ProjectPhase.CONSTRUCTION: {
            "pro": 1.0, "sup": 1.0, "est": 0.2, "eng": 0.8, "for": 1.0, "ski": 1.0
        }
    }

    def __init__(self):
        self.staff = {}
        self.projects = {}

    def add_staff(self, id, name, role, capacity=1.0):
        self.staff[id] = StaffMember(id, name, role, capacity, datetime.now())

    def _calculate_resource_needs(self, value, phase):
        needs = {}
        for role, ratio in self.STAFFING_RATIOS.items():
            base = value / ratio
            phase_key = role.value.split("_")[0][:3]
            factor = self.PHASE_FACTORS[phase].get(phase_key, 1.0)
            needs[role] = base * factor
        return needs

    def get_capacity_at_date(self, target_date):
        capacity = {role: 0.0 for role in ResourceRole}
        for m in self.staff.values():
            if m.availability_date <= target_date:
                capacity[m.role] += m.capacity
        return capacity

    def calculate_demand(self, target_date):
        return {role: 0.0 for role in ResourceRole}

    def can_pursue_project(self, value, start_date, duration_months):
        needs = self._calculate_resource_needs(value, ProjectPhase.CONSTRUCTION)
        end_date = start_date + timedelta(days=duration_months * 30)
        can_staff = True
        bottlenecks = []
        current = start_date
        while current <= end_date:
            capacity = self.get_capacity_at_date(current)
            demand = self.calculate_demand(current)
            for role, need in needs.items():
                available = capacity.get(role, 0) - demand.get(role, 0)
                if need > available:
                    can_staff = False
                    bottlenecks.append(role)
            current += timedelta(days=30)
        rec = "GO - Sufficient capacity" if can_staff else "CAUTION"
        return {"can_staff": can_staff, "recommendation": rec, "bottlenecks": bottlenecks}


def poc_inv04():
    honest = CapacityPlanner()
    honest.add_staff("1", "Alice", ResourceRole.PROJECT_MANAGER, 1.0)
    honest.add_staff("2", "Bob", ResourceRole.SUPERINTENDENT, 1.0)
    h = honest.can_pursue_project(100_000_000, datetime.now(), 12)
    attack = CapacityPlanner()
    for i, role in enumerate(ResourceRole):
        attack.add_staff(str(i), "Ghost", role, 500.0)
    a = attack.can_pursue_project(100_000_000, datetime.now(), 12)
    check("INV-04 phantom FTE GO",
          (not h["can_staff"]) and a["can_staff"] and "GO" in a["recommendation"],
          f"honest={h['recommendation']} attack={a['recommendation']}")


# --- INV-05 enterprise risk p=0 ---
class RiskLevel(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class ProjectRisk:
    probability: float
    impact: float
    score: float = 0.0
    level: RiskLevel = RiskLevel.MEDIUM

    def __post_init__(self):
        self.score = self.probability * self.impact
        if self.score > 5_000_000:
            self.level = RiskLevel.CRITICAL
        elif self.score > 1_000_000:
            self.level = RiskLevel.HIGH
        elif self.score > 250_000:
            self.level = RiskLevel.MEDIUM
        else:
            self.level = RiskLevel.LOW


def poc_inv05():
    honest = ProjectRisk(0.8, 10_000_000)
    attack = ProjectRisk(0.0, 10_000_000)
    check("INV-05 probability=0 hides CRITICAL",
          honest.level == RiskLevel.CRITICAL and attack.level == RiskLevel.LOW and attack.score == 0,
          f"honest={honest.level} attack={attack.level}")


# --- INV-06 drone flight_id path traversal ---
def poc_inv06(tmp: Path):
    output_dir = tmp / "drone_out"
    output_dir.mkdir(parents=True, exist_ok=True)
    flight_id = f"../escaped_{datetime.now().strftime('%H%M%S')}"
    report_path = str(output_dir / f"{flight_id}_report.json")
    with open(report_path, "w") as f:
        json.dump({"flight_id": flight_id}, f)
    written = Path(report_path).resolve()
    escaped = tmp / f"escaped_{flight_id.split('_')[-1]}_report.json"
    # Path join with ../ places file in tmp, not under drone_out
    check("INV-06 flight_id path traversal write",
          written.parent == tmp.resolve() and written.exists() and not str(written).startswith(str(output_dir.resolve())),
          f"wrote={written}")


def main():
    tmp = Path("/tmp/poc_innovative_remaining_2026_10_01")
    tmp.mkdir(parents=True, exist_ok=True)
    poc_inv01()
    poc_inv02()
    poc_inv03()
    poc_inv04()
    poc_inv05()
    poc_inv06(tmp)
    print(f"\n{PASSED} passed, {FAILED} failed")
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
