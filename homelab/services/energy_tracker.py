"""
Energy tracker – aggregates gas (rtlamr) + hydro (HydroQC) consumption
and publishes a simple daily summary.
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table

from homelab.config import settings
from homelab.services.ha_client import HAClient
from homelab.services.mqtt_monitor import GasMeterWatcher

console = Console()
DATA_DIR = Path.home() / ".homelab" / "energy"


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class GasReading:
    meter_id: int
    consumption_m3: float
    timestamp: str  # ISO-8601


@dataclass
class HydroSnapshot:
    total_kwh: Optional[float]
    bill_to_date: Optional[str]
    timestamp: str


@dataclass
class DailySummary:
    day: str                              # YYYY-MM-DD
    gas_readings: list[GasReading] = field(default_factory=list)
    hydro: Optional[HydroSnapshot] = None

    def save(self, directory: Path = DATA_DIR) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self.day}.json"
        path.write_text(json.dumps(asdict(self), indent=2, default=str))
        return path

    @classmethod
    def load(cls, day: str, directory: Path = DATA_DIR) -> Optional["DailySummary"]:
        path = directory / f"{day}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        obj = cls(day=data["day"])
        obj.gas_readings = [GasReading(**r) for r in data.get("gas_readings", [])]
        h = data.get("hydro")
        if h:
            obj.hydro = HydroSnapshot(**h)
        return obj

    def print_report(self) -> None:
        t = Table(title=f"Energy summary — {self.day}", show_header=True)
        t.add_column("Source", style="cyan")
        t.add_column("Value")
        t.add_column("Unit")

        if self.gas_readings:
            latest = self.gas_readings[-1]
            t.add_row("Gas (latest)", str(latest.consumption_m3), "m³")
            t.add_row("Gas readings", str(len(self.gas_readings)), "count")

        if self.hydro:
            t.add_row("Electricity total", str(self.hydro.total_kwh or "?"), "kWh")
            t.add_row("Hydro bill to date", str(self.hydro.bill_to_date or "?"), "")

        console.print(t)


# ── Tracker class ─────────────────────────────────────────────────────────────

class EnergyTracker:
    """
    Runs both a GasMeterWatcher (MQTT) and periodic HA REST polls
    to build a local daily energy summary.

    Usage::

        tracker = EnergyTracker()
        tracker.start()          # non-blocking; writes ~/.homelab/energy/YYYY-MM-DD.json
        tracker.snapshot()       # take a one-shot hydro reading right now
        tracker.report()         # pretty-print today's summary
    """

    def __init__(self):
        self._ha = HAClient()
        self._watcher = GasMeterWatcher()
        self._today = date.today().isoformat()
        self._summary = DailySummary.load(self._today) or DailySummary(day=self._today)

    # ── Gas (via MQTT) ────────────────────────────────────────────────────────

    def _on_gas(self, topic: str, payload: str) -> None:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return
        reading = GasReading(
            meter_id=int(data.get("ID", 0)),
            consumption_m3=float(data.get("Consumption", 0)),
            timestamp=datetime.now().isoformat(),
        )
        self._summary.gas_readings.append(reading)
        self._summary.save()
        console.print(
            f"[yellow]⛽ Gas[/yellow] {reading.consumption_m3} m³  "
            f"@ {reading.timestamp[:19]}"
        )

    # ── Hydro (via HA REST) ───────────────────────────────────────────────────

    def snapshot(self) -> Optional[HydroSnapshot]:
        """Pull current HydroQC values from HA and store them."""
        hydro = self._ha.get_hydro_consumption()
        snap = HydroSnapshot(
            total_kwh=_safe_float(hydro.get("total", {}).get("state")),
            bill_to_date=str(hydro.get("bill_to_date", {}).get("state", "")),
            timestamp=datetime.now().isoformat(),
        )
        self._summary.hydro = snap
        self._summary.save()
        return snap

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self, block: bool = False) -> "EnergyTracker":
        """Start MQTT gas watcher (background thread) and take a hydro snapshot."""
        self._watcher._handle = self._on_gas   # type: ignore[method-assign]
        self._watcher.start(block=False)
        self.snapshot()
        if block:
            import time
            console.print("[dim]Energy tracker running. Ctrl-C to stop.[/dim]")
            try:
                while True:
                    time.sleep(60)
                    self.snapshot()
            except KeyboardInterrupt:
                pass
        return self

    def report(self) -> DailySummary:
        self._summary.print_report()
        return self._summary

    def history(self, days: int = 7) -> list[DailySummary]:
        """Load and return the last N daily summaries."""
        from datetime import timedelta
        today = date.today()
        results = []
        for i in range(days):
            d = (today - timedelta(days=i)).isoformat()
            s = DailySummary.load(d)
            if s:
                results.append(s)
        return results


def _safe_float(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
