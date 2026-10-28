"""
homelab CLI  –  81 Logan, Saint-Lambert
========================================
Install:   pip install -e .
Run:       homelab --help
"""

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="homelab",
    help="🏠  Raspberry Pi 5 homelab management — 81 Logan",
    add_completion=False,
)
console = Console()

# ── Sub-apps ──────────────────────────────────────────────────────────────────

mqtt_app   = typer.Typer(help="MQTT broker commands")
energy_app = typer.Typer(help="Energy tracking (gas + hydro)")
ha_app     = typer.Typer(help="Home Assistant commands")
rtl_app    = typer.Typer(help="RTL-SDR diagnostics")

app.add_typer(mqtt_app,   name="mqtt")
app.add_typer(energy_app, name="energy")
app.add_typer(ha_app,     name="ha")
app.add_typer(rtl_app,    name="rtl")


# ── homelab status ────────────────────────────────────────────────────────────

@app.command()
def status():
    """Show the current status of all homelab services."""
    from homelab.config import settings
    from homelab.services.ha_client import HAClient

    t = Table(title="Homelab status — 81 Logan", show_header=True)
    t.add_column("Service", style="cyan", no_wrap=True)
    t.add_column("Address / entity")
    t.add_column("Status")

    # MQTT
    import socket
    def tcp_ok(host: str, port: int) -> bool:
        try:
            with socket.create_connection((host, port), timeout=2):
                return True
        except OSError:
            return False

    mqtt_ok = tcp_ok(settings.mqtt.host, settings.mqtt.port)
    t.add_row(
        "Mosquitto MQTT",
        f"{settings.mqtt.host}:{settings.mqtt.port}",
        "[green]✓ reachable[/green]" if mqtt_ok else "[red]✗ unreachable[/red]",
    )

    # Home Assistant
    ha = HAClient()
    ha_ok = ha.ping()
    t.add_row(
        "Home Assistant",
        settings.ha.base_url,
        "[green]✓ online[/green]" if ha_ok else "[red]✗ offline[/red]",
    )

    # Mini-splits (via HA)
    if ha_ok:
        splits = ha.get_mini_split_status()
        for room, info in splits.items():
            if "error" in info:
                state = f"[red]{info['error'][:40]}[/red]"
            else:
                state = (
                    f"mode={info['hvac_mode']}  "
                    f"temp={info['current_temperature']}°C  "
                    f"humidity={info['humidity_pct']}%"
                )
            t.add_row(f"Mini-split ({room})", settings.mini_splits.chambre_ip if room == "chambre" else settings.mini_splits.cuisine_ip, state)

    console.print(t)


# ── homelab mqtt monitor ──────────────────────────────────────────────────────

@mqtt_app.command("monitor")
def mqtt_monitor(
    topic: list[str] = typer.Option([], "--topic", "-t", help="Extra topic filter"),
):
    """Live MQTT message stream (Ctrl-C to stop)."""
    from homelab.services.mqtt_monitor import listen, WATCHED_TOPICS

    topics = list(topic) or WATCHED_TOPICS
    console.print(f"[bold]Listening on {len(topics)} topic(s)…[/bold]  Ctrl-C to stop\n")
    listen(topics=topics, block=True)


# ── homelab mqtt gas-watch ────────────────────────────────────────────────────

@mqtt_app.command("gas-watch")
def mqtt_gas_watch():
    """Watch for Énergir gas meter readings (SCM+, meter 1279204985)."""
    from homelab.services.mqtt_monitor import GasMeterWatcher
    import time

    watcher = GasMeterWatcher().start(block=False)
    console.print("[bold yellow]Watching for gas meter readings…[/bold yellow]  Ctrl-C to stop\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        console.print(f"\nReceived {len(watcher.readings)} reading(s).")
        if watcher.latest:
            console.print(f"Latest: {watcher.latest}")


# ── homelab energy report ─────────────────────────────────────────────────────

@energy_app.command("report")
def energy_report(
    days: int = typer.Option(7, "--days", "-d", help="How many days of history to show"),
):
    """Print energy consumption summary (gas + hydro)."""
    from homelab.services.energy_tracker import EnergyTracker, DailySummary

    tracker = EnergyTracker()
    history = tracker.history(days)
    if not history:
        console.print("[dim]No saved energy data. Run `homelab energy track` first.[/dim]")
        return
    for summary in history:
        summary.print_report()


@energy_app.command("track")
def energy_track(
    block: bool = typer.Option(True, help="Keep running (Ctrl-C to stop)"),
):
    """Start real-time energy tracker (gas via MQTT + hydro via HA REST)."""
    from homelab.services.energy_tracker import EnergyTracker

    tracker = EnergyTracker()
    tracker.start(block=block)


# ── homelab ha status ─────────────────────────────────────────────────────────

@ha_app.command("status")
def ha_status():
    """Show mini-split and HydroQC sensor states from Home Assistant."""
    from homelab.services.ha_client import HAClient

    ha = HAClient()
    if not ha.ping():
        console.print("[red]Home Assistant is unreachable.[/red]")
        raise typer.Exit(1)

    # Mini-splits
    splits = ha.get_mini_split_status()
    t = Table(title="Mini-splits", show_header=True)
    t.add_column("Room", style="cyan")
    t.add_column("Mode")
    t.add_column("Set temp")
    t.add_column("Current temp")
    t.add_column("Humidity")
    for room, info in splits.items():
        if "error" in info:
            t.add_row(room, f"[red]{info['error'][:50]}[/red]", "", "", "")
        else:
            t.add_row(
                room,
                info["hvac_mode"],
                str(info["temperature"]),
                str(info["current_temperature"]),
                f"{info['humidity_pct']}%" if info["humidity_pct"] else "?",
            )
    console.print(t)

    # HydroQC
    hydro = ha.get_hydro_consumption()
    t2 = Table(title="HydroQC", show_header=True)
    t2.add_column("Sensor", style="cyan")
    t2.add_column("Value")
    for k, v in hydro.items():
        if "error" in v:
            t2.add_row(k, f"[red]{v['error'][:50]}[/red]")
        else:
            t2.add_row(k, f"{v['state']} {v.get('unit', '')}")
    console.print(t2)


# ── homelab rtl diag ──────────────────────────────────────────────────────────

@rtl_app.command("diag")
def rtl_diag(
    container: str = typer.Option("rtlamr", "--container", "-c"),
    tail:      int  = typer.Option(500,     "--tail",      "-n", help="Log lines to scan"),
    log_file:  str  = typer.Option("",      "--file",      "-f", help="Parse a saved log file instead"),
):
    """Analyse rtlamr container logs for known issues."""
    from homelab.services.rtlsdr_diag import run_diag, analyse_log_file

    if log_file:
        analyse_log_file(log_file, container)
    else:
        run_diag(container, tail)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    app()


if __name__ == "__main__":
    main()
