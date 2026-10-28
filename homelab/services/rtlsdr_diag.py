"""
RTL-SDR diagnostics – parses Docker logs from the rtlamr container
and surfaces known issues (e.g. "not keeping up with rtl_tcp").
"""

import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime

from rich.console import Console
from rich.table import Table

console = Console()

# ── Known error patterns ────────────────────────────────────────────────────

_PATTERNS = {
    "not_keeping_up": re.compile(r"not keeping up with rtl_tcp", re.IGNORECASE),
    "mqtt_unreachable": re.compile(r"(Network is unreachable|Errno 101)", re.IGNORECASE),
    "rtl_not_found":   re.compile(r"(No supported devices|RTL.*not found)", re.IGNORECASE),
    "scm_decoded":     re.compile(r"SCM\+.*Consumption", re.IGNORECASE),
    "mqtt_connected":  re.compile(r"Connected to MQTT broker", re.IGNORECASE),
}

KNOWN_FIXES = {
    "not_keeping_up": (
        "Pi ARM64 cannot decode 4 protocols simultaneously at 2.048 MSps. "
        "Fix: set filterid=1279204985 and msgtype=scm+ in config.yml "
        "so only your meter's SCM+ frames are decoded."
    ),
    "mqtt_unreachable": (
        "Transient network event (Pi reboot or router blip). "
        "rtlamr2mqtt retries every 5 s; usually self-heals. "
        "If persistent, check that Mosquitto is running: "
        "  docker ps | grep mosquitto"
    ),
    "rtl_not_found": (
        "RTL-SDR dongle not detected by the container. "
        "Ensure --device /dev/bus/usb is passed in docker run / compose, "
        "and that no other process (rtl_tcp, SDR#) holds the device."
    ),
}


# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class DiagResult:
    container: str
    lines_scanned: int
    issues: dict[str, list[str]] = field(default_factory=dict)  # pattern → matching lines
    info:   dict[str, list[str]] = field(default_factory=dict)  # good signals

    @property
    def healthy(self) -> bool:
        return not self.issues

    def print_report(self) -> None:
        console.rule(f"[bold]RTL-SDR Diagnostics — {self.container}[/bold]")
        console.print(f"Lines scanned: {self.lines_scanned}\n")

        if self.info:
            t = Table(title="✅ Good signals", show_header=False, box=None)
            for key, lines in self.info.items():
                t.add_row(f"[green]{key}[/green]", f"{len(lines)} occurrences")
            console.print(t)

        if not self.issues:
            console.print("\n[bold green]No known issues detected.[/bold green]")
            return

        for key, lines in self.issues.items():
            console.print(f"\n[bold red]⚠ {key}[/bold red] ({len(lines)} occurrences)")
            for line in lines[:3]:          # show at most 3 examples
                console.print(f"  [dim]{line.strip()}[/dim]")
            if key in KNOWN_FIXES:
                console.print(f"  [yellow]Fix:[/yellow] {KNOWN_FIXES[key]}")


# ── Main functions ────────────────────────────────────────────────────────────

def fetch_logs(container: str = "rtlamr", tail: int = 500) -> list[str]:
    """Fetch recent Docker logs from the container (runs on the Pi via SSH or locally)."""
    try:
        result = subprocess.run(
            ["docker", "logs", container, "--tail", str(tail)],
            capture_output=True,
            text=True,
            timeout=15,
        )
        output = result.stdout + result.stderr   # docker logs writes to stderr
        return output.splitlines()
    except FileNotFoundError:
        console.print("[red]docker CLI not found. Run this on the Raspberry Pi.[/red]")
        return []
    except subprocess.TimeoutExpired:
        console.print("[red]Timed out fetching Docker logs.[/red]")
        return []


def analyse_lines(lines: list[str], container: str = "rtlamr") -> DiagResult:
    """Scan log lines against known patterns and return a DiagResult."""
    result = DiagResult(container=container, lines_scanned=len(lines))

    for line in lines:
        for key, pattern in _PATTERNS.items():
            if pattern.search(line):
                bucket = "info" if key in ("scm_decoded", "mqtt_connected") else "issues"
                store = result.info if bucket == "info" else result.issues
                store.setdefault(key, []).append(line)

    return result


def run_diag(container: str = "rtlamr", tail: int = 500) -> DiagResult:
    """Full diagnostic: fetch logs, analyse, print report."""
    lines = fetch_logs(container, tail)
    result = analyse_lines(lines, container)
    result.print_report()
    return result


def analyse_log_file(path: str, container: str = "rtlamr") -> DiagResult:
    """Analyse a saved log file instead of live Docker logs."""
    with open(path) as f:
        lines = f.readlines()
    result = analyse_lines(lines, container)
    result.print_report()
    return result
